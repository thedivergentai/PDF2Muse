"""Gradio web interface for PDF2Muse."""

import json
import logging
import os
import sys
import tempfile
import zipfile
import shutil
from pathlib import Path
from typing import Callable, Generator, List, Optional, Tuple

import gradio as gr
from rich.console import Console

from .adapters import adapter_healthchecks
from .cli import configure_windows_stdio
from .core import PDF2MusePipeline
from .musicxml import find_musescore_binary
from .oemer_utils import download_checkpoints, get_checkpoint_dir
from .quality_scorecard import format_quality_scorecard, load_benchmark_summary
from .review import build_score_review_html, playback_events_from_musicxml

configure_windows_stdio()

logger = logging.getLogger(__name__)
console = Console()

ConvertSingleYield = Tuple[str, Optional[str], Optional[str], dict, dict, str]
ConvertBatchYield = Tuple[str, Optional[str], dict, dict]
ProgressCallback = Callable[[float, str], None]

_DOWNLOAD_SKELETON_ACTIVE = (
    '<div class="download-skeleton is-active" role="status" aria-live="polite" '
    'aria-label="Generating output files">'
    '<div class="skeleton-line skeleton-line--wide"></div>'
    '<div class="skeleton-line skeleton-line--medium"></div>'
    '<div class="skeleton-line skeleton-line--narrow"></div>'
    "</div>"
)

_DOWNLOAD_SKELETON_IDLE = '<div class="download-skeleton" aria-hidden="true"></div>'


def _btn_busy() -> dict:
    return gr.update(interactive=False, elem_classes=["convert-btn", "is-busy"])


def _btn_ready() -> dict:
    return gr.update(interactive=True, elem_classes=["convert-btn"])


def _md_loading(title: str, detail: str) -> str:
    return (
        f"### {title}\n\n"
        f"{detail}\n\n"
        "*OMR can take several minutes per page on CPU. Keep this tab open.*"
    )


def _md_success(has_mscx: bool, scorecard: str = "") -> str:
    review_note = (
        "\n\n**Review required:** OMR output is a draft. Open the MusicXML or "
        "MuseScore file in notation software and check notes, rhythms, voices, "
        "and layout before using it."
    )
    scorecard_block = f"\n\n{scorecard}" if scorecard else ""
    if has_mscx:
        return (
            "### Conversion complete\n\n"
            "Both **MusicXML** and **MuseScore** files are ready for download below."
            f"{scorecard_block}{review_note}"
        )
    return (
        "### Conversion complete\n\n"
        "**MusicXML** is ready below. MuseScore was not detected or `.mscx` export was "
        "skipped—you can import the MusicXML into MuseScore or another notation editor."
        f"{scorecard_block}{review_note}"
    )


def _pipeline_kwargs(
    pdf_path: str,
    output_dir: str,
    *,
    deskew: bool,
    use_tf: bool,
    musescore_path: Optional[str],
    first_page: Optional[int],
    last_page: Optional[int],
    render_dpi: int,
    oemer_device: str,
    oemer_quality_profile: str,
    model_backend: str,
    oemer_retries: bool,
) -> dict:
    return {
        "pdf_path": pdf_path,
        "output_dir": output_dir,
        "deskew": deskew,
        "use_tf": use_tf,
        "musescore_path": musescore_path,
        "first_page": first_page,
        "last_page": last_page,
        "render_dpi": render_dpi,
        "oemer_device": oemer_device,
        "oemer_quality_profile": oemer_quality_profile,
        "model_backend": model_backend,
        "oemer_retries": oemer_retries,
        "quality_report": True,
    }


def _run_pipeline_with_progress(
    pipeline: PDF2MusePipeline,
    progress: Optional[gr.Progress],
    status_builder: Callable[[str], str],
) -> Generator[str, None, None]:
    """Run pipeline.run and yield markdown status updates."""

    last_message = ""

    def on_progress(fraction: float, description: str) -> None:
        nonlocal last_message
        last_message = description
        if progress is not None:
            try:
                progress(fraction, desc=description)
            except Exception:
                pass

    yield status_builder(_md_loading("Preparing", "Starting conversion pipeline…"))

    import threading

    error_holder: list[Exception] = []
    result_holder: list[Path] = []

    def worker() -> None:
        try:
            result_holder.append(pipeline.run(progress_callback=on_progress))
        except Exception as exc:
            error_holder.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while thread.is_alive():
        if last_message:
            yield status_builder(_md_loading("Running", last_message))
        thread.join(timeout=0.5)

    if error_holder:
        raise error_holder[0]
    if not result_holder:
        raise RuntimeError("Pipeline did not return a result")


def _status_from_report(report: dict) -> str:
    scorecard = format_quality_scorecard(report)
    benchmark = load_benchmark_summary()
    if benchmark:
        return f"{scorecard}\n\n_Latest multi-tier benchmark:_ {benchmark}"
    return scorecard


def _format_conversion_error(exc: Exception) -> str:
    """Build a user-facing markdown error message."""
    msg = str(exc).strip()
    if "\n" in msg or len(msg) > 120:
        return f"### Error during conversion\n\n**Details:**\n\n```\n{msg}\n```"
    return f"### Error during conversion\n\n`{msg}`"


def _review_html_idle() -> str:
    return (
        '<p class="empty-download-hint">A side-by-side original page and recognized '
        "draft will appear here after conversion.</p>"
    )


def _png_data_uri(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    import base64

    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else "image/png"
    return f"data:{mime};base64,{payload}"


def _build_review_panel(output_dir: Path) -> str:
    xml_src = output_dir / "combined.musicxml"
    if not xml_src.exists():
        return _review_html_idle()
    text = xml_src.read_text(encoding="utf-8")
    preview = None
    pages = output_dir / "pages"
    if pages.exists():
        pngs = sorted(pages.glob("*.png"))
        if pngs:
            preview = _png_data_uri(pngs[0])
    return build_score_review_html(
        text,
        page_image_data_uri=preview,
        playback_events=playback_events_from_musicxml(text),
    )


def _uploaded_file_path(file_obj: object) -> str:
    """Return a real server-side path for Gradio uploads.

    Gradio 5/6 FileData.name is the original filename, not a filesystem path.
    Only return a value that exists on disk.
    """
    candidates: list[object] = []
    if isinstance(file_obj, (str, Path)):
        candidates.append(file_obj)
    else:
        for attr in ("path", "name"):
            value = getattr(file_obj, attr, None)
            if value:
                candidates.append(value)

    for value in candidates:
        if not isinstance(value, (str, Path)):
            continue
        text = str(value).strip()
        if not text:
            continue
        path = Path(text)
        if path.exists():
            return str(path)

    raise FileNotFoundError(
        "PDF upload did not include a readable temp path. "
        "If this is Gradio, use FileData.path rather than the original filename."
    )


def convert_pdf(
    pdf_file: gr.File,
    deskew: bool = True,
    use_tf: bool = False,
    musescore_path: Optional[str] = None,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    render_dpi: int = 360,
    oemer_device: str = "auto",
    oemer_quality_profile: str = "quality",
    model_backend: str = "auto",
    preview_first_page: bool = False,
    progress: gr.Progress = gr.Progress(track_tqdm=False),
) -> Generator[ConvertSingleYield, None, None]:
    """Convert a single PDF to MusicXML and MuseScore format with live progress."""
    idle_review = _review_html_idle()
    if pdf_file is None:
        yield (
            "### Please upload a PDF file first\n\n"
            "Choose a scanned sheet-music PDF, then run conversion.",
            None,
            None,
            _DOWNLOAD_SKELETON_IDLE,
            _btn_ready(),
            idle_review,
        )
        return

    musescore_path = musescore_path.strip() if musescore_path else None
    first_page = int(first_page) if first_page and int(first_page) > 0 else None
    last_page = int(last_page) if last_page and int(last_page) > 0 else None
    if preview_first_page:
        first_page = 1
        last_page = 1
        oemer_quality_profile = "fast"
        render_dpi = min(int(render_dpi or 360), 220)

    yield (
        _md_loading("Preparing", "Starting conversion pipeline…"),
        None,
        None,
        _DOWNLOAD_SKELETON_ACTIVE,
        _btn_busy(),
        idle_review,
    )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = _uploaded_file_path(pdf_file)

            pipeline = PDF2MusePipeline(
                **_pipeline_kwargs(
                    pdf_path,
                    str(output_dir),
                    deskew=deskew,
                    use_tf=use_tf,
                    musescore_path=musescore_path,
                    first_page=first_page,
                    last_page=last_page,
                    render_dpi=int(render_dpi),
                    oemer_device=oemer_device,
                    oemer_quality_profile=oemer_quality_profile,
                    model_backend=model_backend,
                    oemer_retries=True,
                )
            )

            for status_msg in _run_pipeline_with_progress(pipeline, progress, lambda s: s):
                yield (
                    status_msg,
                    None,
                    None,
                    _DOWNLOAD_SKELETON_ACTIVE,
                    _btn_busy(),
                    idle_review,
                )

            progress(0.98, desc="Finalizing downloads")

            xml_src = output_dir / "combined.musicxml"
            mscx_src = output_dir / "combined.mscx"
            xml_dest: Optional[str] = None
            mscx_dest: Optional[str] = None

            if xml_src.exists():
                dest = Path(tempfile.gettempdir()) / f"pdf2muse_{xml_src.name}"
                shutil.copy(xml_src, dest)
                xml_dest = str(dest)

            if mscx_src.exists():
                dest = Path(tempfile.gettempdir()) / f"pdf2muse_{mscx_src.name}"
                shutil.copy(mscx_src, dest)
                mscx_dest = str(dest)

            progress(1.0, desc="Complete")
            scorecard = _status_from_report(pipeline.conversion_report)
            yield (
                _md_success(mscx_dest is not None, scorecard),
                xml_dest,
                mscx_dest,
                _DOWNLOAD_SKELETON_IDLE,
                _btn_ready(),
                _build_review_panel(output_dir),
            )

    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        yield (
            f"### Error: file not found\n\n`{e}`\n\n"
            "Check that the upload completed and try again.",
            None,
            None,
            _DOWNLOAD_SKELETON_IDLE,
            _btn_ready(),
            _review_html_idle(),
        )

    except Exception as e:
        logger.error("Conversion error: %s", e, exc_info=True)
        yield (
            _format_conversion_error(e),
            None,
            None,
            _DOWNLOAD_SKELETON_IDLE,
            _btn_ready(),
            _review_html_idle(),
        )


def convert_batch_pdfs(
    pdf_files: List[gr.File],
    deskew: bool = True,
    use_tf: bool = False,
    musescore_path: Optional[str] = None,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    render_dpi: int = 360,
    oemer_device: str = "auto",
    oemer_quality_profile: str = "quality",
    model_backend: str = "auto",
    progress: gr.Progress = gr.Progress(track_tqdm=False),
) -> Generator[ConvertBatchYield, None, None]:
    """Convert multiple PDFs in batch with live progress; returns a ZIP of outputs."""
    if not pdf_files:
        yield (
            "### Please upload one or more PDF files first\n\n"
            "Add multiple PDFs to the batch queue, then start conversion.",
            None,
            _DOWNLOAD_SKELETON_IDLE,
            _btn_ready(),
        )
        return

    musescore_path = musescore_path.strip() if musescore_path else None
    first_page = int(first_page) if first_page and int(first_page) > 0 else None
    last_page = int(last_page) if last_page and int(last_page) > 0 else None

    total_files = len(pdf_files)
    log_output = "### Starting batch conversion\n\n"
    temp_zip_dir = Path(tempfile.gettempdir()) / "pdf2muse_batch"
    if temp_zip_dir.exists():
        shutil.rmtree(temp_zip_dir)
    temp_zip_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0

    yield (
        log_output + _md_loading("Preparing batch", f"Queued **{total_files}** files…"),
        None,
        _DOWNLOAD_SKELETON_ACTIVE,
        _btn_busy(),
    )

    for i, file_obj in enumerate(pdf_files):
        pdf_path = _uploaded_file_path(file_obj)
        pdf_name = Path(pdf_path).name
        file_frac = i / total_files
        progress(file_frac, desc=f"Batch {i + 1}/{total_files}")

        log_output += f"\n**[{i + 1}/{total_files}]** Processing `{pdf_name}`…\n"
        yield (
            log_output + _md_loading("Processing file", f"Working on `{pdf_name}`…"),
            None,
            _DOWNLOAD_SKELETON_ACTIVE,
            _btn_busy(),
        )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "output"
                output_dir.mkdir(parents=True, exist_ok=True)

                pipeline = PDF2MusePipeline(
                    **_pipeline_kwargs(
                        pdf_path,
                        str(output_dir),
                        deskew=deskew,
                        use_tf=use_tf,
                        musescore_path=musescore_path,
                        first_page=first_page,
                        last_page=last_page,
                        render_dpi=int(render_dpi),
                        oemer_device=oemer_device,
                        oemer_quality_profile=oemer_quality_profile,
                        model_backend=model_backend,
                        oemer_retries=True,
                    )
                )

                def _batch_status(message: str) -> str:
                    return log_output + message

                for step_status in _run_pipeline_with_progress(
                    pipeline, progress, _batch_status
                ):
                    yield (
                        step_status,
                        None,
                        _DOWNLOAD_SKELETON_ACTIVE,
                        _btn_busy(),
                    )

                xml_src = output_dir / "combined.musicxml"
                mscx_src = output_dir / "combined.mscx"
                file_prefix = Path(pdf_name).stem
                if xml_src.exists():
                    shutil.copy(xml_src, temp_zip_dir / f"{file_prefix}.musicxml")
                if mscx_src.exists():
                    shutil.copy(mscx_src, temp_zip_dir / f"{file_prefix}.mscx")

                success_count += 1
                log_output += f"- Completed `{pdf_name}`\n"

        except Exception as e:
            fail_count += 1
            err = str(e).strip()
            if "\n" in err:
                log_output += f"- Failed `{pdf_name}`:\n```\n{err}\n```\n"
            else:
                log_output += f"- Failed `{pdf_name}`: `{err}`\n"

        yield (
            log_output,
            None,
            _DOWNLOAD_SKELETON_ACTIVE,
            _btn_busy(),
        )

    if success_count == 0:
        yield (
            log_output + "\n### All batch conversions failed\n\n"
            "Review errors above, fix inputs, and try again.",
            None,
            _DOWNLOAD_SKELETON_IDLE,
            _btn_ready(),
        )
        return

    progress(0.95, desc="Creating ZIP archive")
    zip_path = Path(tempfile.gettempdir()) / "pdf2muse_batch_outputs.zip"
    if zip_path.exists():
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(temp_zip_dir):
            for file in files:
                zipf.write(os.path.join(root, file), file)

    shutil.rmtree(temp_zip_dir)
    progress(1.0, desc="Batch complete")

    summary = (
        f"\n### Batch processing complete\n"
        f"- **Succeeded:** {success_count}\n"
        f"- **Failed:** {fail_count}\n\n"
        "Download all generated files using the link below."
    )
    yield (
        log_output + summary,
        str(zip_path),
        _DOWNLOAD_SKELETON_IDLE,
        _btn_ready(),
    )


def run_diagnostics(musescore_custom: Optional[str] = None) -> str:
    """Run environment check and return markdown status report."""
    report = (
        "## System environment diagnostics\n\n"
        "These checks confirm **dependencies and checkpoints**, not transcription quality. "
        "A PASS here does not mean the MusicXML is musically correct.\n\n"
    )

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    report += f"- **Python Engine:** `v{py_ver}` *(Required: >= 3.9)* — **[PASS]**\n\n"

    try:
        import pypdfium2 as pdfium  # noqa: F401

        report += (
            f"- **PDF Rendering (pypdfium2):** **[OK]** "
            f"(built-in; no Poppler required)\n\n"
        )
    except ImportError:
        report += (
            "- **PDF Rendering (pypdfium2):** **[MISSING]**\n"
            "  - Reinstall PDF2Muse; pypdfium2 is required for PDF-to-image conversion.\n\n"
        )

    msc_path = None
    musescore_custom = musescore_custom.strip() if musescore_custom else None
    if musescore_custom:
        custom_path_obj = Path(musescore_custom)
        if custom_path_obj.exists():
            msc_path = custom_path_obj
    else:
        msc_path = find_musescore_binary()

    if msc_path:
        report += f"- **MuseScore Interface:** **[DETECTED]** at `{msc_path}`\n\n"
    else:
        report += (
            "- **MuseScore Interface:** **OPTIONAL (NOT DETECTED)**\n"
            "  - MusicXML export still works; native `.mscx` export is skipped without MuseScore.\n\n"
        )

    chk_dir = get_checkpoint_dir()
    unet_path = chk_dir / "unet_big" / "model.onnx"
    seg_path = chk_dir / "seg_net" / "model.onnx"
    models_ready = unet_path.exists() and seg_path.exists()

    if models_ready:
        report += "- **Deep Learning OMR Models:** **[READY]** (unet_big & seg_net loaded locally)\n\n"
    else:
        report += (
            "- **Deep Learning OMR Models:** **[CHECKPOINTS NOT DETECTED]**\n"
            "  - Checkpoints download on first run, or use the Model Manager tab.\n\n"
        )

    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        report += (
            f"- **ONNX Runtime Engine:** `v{ort.__version__}` "
            f"(Available Acceleration: `{providers}`)\n\n"
        )
    except ImportError:
        report += "- **ONNX Runtime Engine:** *Not loaded / standard module*\n\n"

    report += "### OMR backend readiness\n\n"
    for status in adapter_healthchecks():
        flag = "**[READY]**" if status.available else "**[UNAVAILABLE]**"
        report += f"- **{status.name}:** {flag} — {status.message}\n"
    report += "\n*Diagnostics confirm environment setup, not transcription accuracy.*\n"

    return report


def download_checkpoints_ui() -> str:
    """Gradio handler for downloading model checkpoints."""
    try:
        download_checkpoints(force=True)
        return (
            "### OMR model checkpoints downloaded\n\n"
            "Checkpoints are ready. Run Pre-Flight Diagnostics to confirm."
        )
    except Exception as e:
        return f"### Failed to download model checkpoints\n\n`{str(e)}`"


def create_interface(
    default_musescore: Optional[str] = None,
) -> gr.Blocks:
    """Create and return the Gradio interface."""
    custom_css = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
        --space-1: 8px;
        --space-2: 16px;
        --space-3: 24px;
        --space-4: 32px;
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 16px;
        --color-primary: #EA580C;
        --color-on-primary: #FFFFFF;
        --color-secondary: #F97316;
        --color-accent: #2563EB;
        --color-bg: #1C1917;
        --color-surface: #292524;
        --color-surface-elevated: #44403C;
        --color-border: rgba(255, 255, 255, 0.1);
        --color-text: #FAFAF9;
        --color-text-muted: #D6D3D1;
        --color-text-subtle: #A8A29E;
        --color-success: #22C55E;
        --color-destructive: #DC2626;
        --color-ring: #EA580C;
        --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.35);
        --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.4);
        --motion-fast: 150ms;
        --motion-base: 250ms;
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
            scroll-behavior: auto !important;
        }
        .download-skeleton .skeleton-line {
            animation: none !important;
            opacity: 0.35;
        }
    }

    body, .gradio-container {
        font-family: var(--font-sans) !important;
        font-size: 16px !important;
        line-height: 1.5 !important;
        background-color: var(--color-bg) !important;
        background-image:
            radial-gradient(circle at 12% 8%, rgba(234, 88, 12, 0.12) 0%, transparent 42%),
            radial-gradient(circle at 88% 92%, rgba(37, 99, 235, 0.08) 0%, transparent 45%) !important;
        color: var(--color-text) !important;
        overflow-x: hidden !important;
    }

    .container {
        max-width: 1120px !important;
        width: 100% !important;
        margin: 0 auto !important;
        padding: var(--space-2) !important;
        box-sizing: border-box !important;
    }

    .inline-icon {
        width: 1.1em;
        height: 1.1em;
        vertical-align: -0.15em;
        margin-right: 0.35em;
        display: inline-block;
    }

    .header-banner {
        background: linear-gradient(135deg, rgba(41, 37, 36, 0.95) 0%, rgba(28, 25, 23, 0.98) 100%) !important;
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-lg) !important;
        padding: var(--space-4) var(--space-3) !important;
        margin-bottom: var(--space-3) !important;
        box-shadow: var(--shadow-md) !important;
        text-align: center;
    }

    .header-content {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        flex-wrap: wrap;
    }

    .header-logo {
        width: 40px;
        height: 40px;
        color: var(--color-primary);
        flex-shrink: 0;
    }

    .header-banner h1 {
        font-family: var(--font-sans) !important;
        font-size: clamp(1.75rem, 4vw, 2.5rem) !important;
        font-weight: 700 !important;
        margin: 0 !important;
        color: var(--color-text) !important;
        letter-spacing: -0.02em !important;
    }

    .header-banner p {
        font-size: 1rem !important;
        color: var(--color-text-muted) !important;
        max-width: 42rem !important;
        margin: var(--space-2) auto 0 !important;
    }

    .block, .gr-box, .accordion, .glass-tab {
        background: rgba(41, 37, 36, 0.72) !important;
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-md) !important;
        box-shadow: var(--shadow-sm) !important;
        padding: var(--space-3) !important;
    }

    .tabs button, button[role="tab"] {
        font-weight: 500 !important;
        min-height: 44px !important;
        padding: 10px 16px !important;
        color: var(--color-text-muted) !important;
    }

    .tabs button.selected, button[role="tab"][aria-selected="true"] {
        color: var(--color-text) !important;
        border-color: var(--color-primary) !important;
    }

    input[type="text"], input[type="number"], textarea, select {
        background: var(--color-bg) !important;
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--color-text) !important;
        font-size: 16px !important;
        min-height: 44px !important;
        transition: border-color var(--motion-fast) ease, box-shadow var(--motion-fast) ease !important;
    }

    input[type="text"]:focus-visible, input[type="number"]:focus-visible,
    textarea:focus-visible, select:focus-visible,
    button:focus-visible, .gr-button:focus-visible {
        outline: 2px solid var(--color-ring) !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 0 4px rgba(234, 88, 12, 0.25) !important;
    }

    label, .gr-form > label span {
        color: var(--color-text-muted) !important;
        font-size: 0.9375rem !important;
    }

    .convert-btn, button.convert-btn {
        font-family: var(--font-sans) !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        min-height: 48px !important;
        padding: 12px 24px !important;
        border-radius: var(--radius-sm) !important;
        background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%) !important;
        color: var(--color-on-primary) !important;
        border: none !important;
        box-shadow: var(--shadow-sm) !important;
        transition: transform var(--motion-fast) ease, box-shadow var(--motion-base) ease, opacity var(--motion-fast) ease !important;
        cursor: pointer !important;
    }

    .convert-btn:hover:not(:disabled):not(.is-busy) {
        transform: translateY(-1px);
        box-shadow: 0 10px 24px rgba(234, 88, 12, 0.35) !important;
    }

    .convert-btn.is-busy, .convert-btn:disabled {
        opacity: 0.55 !important;
        cursor: not-allowed !important;
        transform: none !important;
        pointer-events: none !important;
    }

    .download-card {
        padding: var(--space-3) !important;
        background: rgba(28, 25, 23, 0.65) !important;
        border: 1px solid var(--color-border) !important;
        border-radius: var(--radius-md) !important;
        position: relative;
    }

    .download-skeleton {
        display: none;
        margin-bottom: var(--space-2);
        padding: var(--space-2);
        border-radius: var(--radius-sm);
        background: rgba(28, 25, 23, 0.5);
        border: 1px dashed var(--color-border);
    }

    .download-skeleton.is-active {
        display: block;
    }

    .skeleton-line {
        height: 12px;
        border-radius: 6px;
        margin-bottom: 10px;
        background: linear-gradient(
            90deg,
            rgba(68, 64, 60, 0.35) 0%,
            rgba(120, 113, 108, 0.45) 50%,
            rgba(68, 64, 60, 0.35) 100%
        );
        background-size: 200% 100%;
        animation: shimmer 1.4s ease-in-out infinite;
    }

    .skeleton-line--wide { width: 92%; }
    .skeleton-line--medium { width: 72%; }
    .skeleton-line--narrow { width: 48%; margin-bottom: 0; }

    @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }

    .empty-download-hint {
        color: var(--color-text-subtle);
        font-size: 0.9375rem;
        margin: 0 0 var(--space-2) 0;
    }

    .divider {
        margin: var(--space-4) 0;
        border: 0;
        border-top: 1px solid var(--color-border);
    }

    .requirement-card, .tip-card {
        padding: var(--space-3);
        border-radius: var(--radius-md);
        border: 1px solid var(--color-border);
        background: rgba(41, 37, 36, 0.55);
    }

    .requirement-card { border-left: 4px solid var(--color-accent); }
    .tip-card { border-left: 4px solid var(--color-success); }

    .requirement-card h3, .tip-card h3 {
        margin-top: 0;
        color: var(--color-text);
        font-size: 1.0625rem;
        font-weight: 600;
    }

    .requirement-card p, .tip-card p,
    .requirement-card li, .tip-card li {
        color: var(--color-text-muted);
        font-size: 0.9375rem;
        line-height: 1.6;
    }

    .prose h3, .markdown h3, .md h3 {
        color: var(--color-text) !important;
    }

    .prose p, .markdown p, .md p, .prose li, .markdown li {
        color: var(--color-text-muted) !important;
    }

    @media (max-width: 768px) {
        .container { padding: var(--space-1) !important; }
        .block, .gr-box, .accordion, .glass-tab { padding: var(--space-2) !important; }
        .header-banner { padding: var(--space-3) var(--space-2) !important; }
    }
    """

    interface = gr.Blocks(title="PDF2Muse - Sheet Music Converter")
    interface.css = custom_css

    with interface:
        with gr.Column(elem_classes="container"):
            gr.HTML(
                f"""
                <div class="header-banner">
                    <div class="header-content">
                        <svg class="header-logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
                             fill="none" stroke="currentColor" stroke-width="2.5"
                             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M9 18V5l12-2v13"></path>
                            <circle cx="6" cy="18" r="3"></circle>
                            <circle cx="18" cy="16" r="3"></circle>
                        </svg>
                        <h1>PDF2Muse</h1>
                    </div>
                    <p>Draft. Review before performance or teaching. Experimental optical music recognition — generated MusicXML is not a finished score.</p>
                </div>
                """
            )

            with gr.Tabs():
                with gr.TabItem("Single Score Conversion"):
                    with gr.Row(elem_classes="glass-tab"):
                        with gr.Column(scale=11):
                            pdf_input = gr.File(
                                label="Upload PDF Sheet Music",
                                file_types=[".pdf"],
                                type="filepath",
                            )

                            with gr.Accordion("Environment & Settings", open=True):
                                musescore_input = gr.Textbox(
                                    label="MuseScore Executable Path",
                                    value=default_musescore or "",
                                    placeholder="e.g. C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe",
                                    info="Optional if MuseScore is on PATH",
                                )
                                with gr.Row():
                                    first_page_input = gr.Number(
                                        label="First Page",
                                        value=0,
                                        precision=0,
                                        info="1-indexed; 0 = start",
                                    )
                                    last_page_input = gr.Number(
                                        label="Last Page",
                                        value=0,
                                        precision=0,
                                        info="1-indexed; 0 = end",
                                    )
                                with gr.Row():
                                    deskew_checkbox = gr.Checkbox(
                                        label="Enable Deskewing",
                                        value=True,
                                        info="Auto-correct tilted scans",
                                    )
                                    use_tf_checkbox = gr.Checkbox(
                                        label="Use TensorFlow (Slower)",
                                        value=False,
                                        info="ONNX Runtime is the default",
                                    )
                                preview_checkbox = gr.Checkbox(
                                    label="Preview first page (fast)",
                                    value=False,
                                    info="Recognize page 1 with the fast profile, then run a full export when you like the draft",
                                )
                                with gr.Row():
                                    render_dpi_input = gr.Number(
                                        label="Render DPI",
                                        value=360,
                                        precision=0,
                                        info="Locked quality default is 360 DPI",
                                    )
                                    quality_profile_input = gr.Dropdown(
                                        label="OMR quality profile",
                                        choices=["fast", "balanced", "quality"],
                                        value="quality",
                                    )
                                with gr.Row():
                                    device_input = gr.Dropdown(
                                        label="OMR device",
                                        choices=["auto", "cpu", "cuda"],
                                        value="auto",
                                        info="auto uses CUDA when onnxruntime-gpu CUDA EP is available",
                                    )
                                    backend_input = gr.Dropdown(
                                        label="Model backend",
                                        choices=[
                                            "auto",
                                            "oemer-stock",
                                            "oemer-custom",
                                            "legato-experimental",
                                        ],
                                        value="auto",
                                    )

                            convert_button = gr.Button(
                                "Recognize & Convert Sheet Music",
                                variant="primary",
                                elem_classes="convert-btn",
                            )

                        with gr.Column(scale=9):
                            status_output = gr.Markdown(
                                value=(
                                    "### Awaiting input\n\n"
                                    "Upload a PDF, adjust settings if needed, then start conversion."
                                ),
                            )
                            with gr.Group(elem_classes="download-card"):
                                download_skeleton = gr.HTML(
                                    value=_DOWNLOAD_SKELETON_IDLE,
                                )
                                gr.HTML(
                                    '<p class="empty-download-hint">'
                                    "Outputs appear here after a successful conversion."
                                    "</p>"
                                )
                                gr.Markdown("### Generated outputs")
                                musicxml_output = gr.File(
                                    label="Download MusicXML (.musicxml)",
                                    interactive=False,
                                )
                                mscx_output = gr.File(
                                    label="Download MuseScore File (.mscx)",
                                    interactive=False,
                                )
                                gr.Markdown("### Score review")
                                review_output = gr.HTML(value=_review_html_idle())

                with gr.TabItem("Batch Processing"):
                    with gr.Row(elem_classes="glass-tab"):
                        with gr.Column(scale=11):
                            batch_input = gr.File(
                                label="Upload Multiple Sheet Music PDFs",
                                file_types=[".pdf"],
                                file_count="multiple",
                                type="filepath",
                            )
                            with gr.Accordion("Batch Processing Settings", open=False):
                                with gr.Row():
                                    batch_first_page = gr.Number(
                                        label="First Page",
                                        value=0,
                                        precision=0,
                                    )
                                    batch_last_page = gr.Number(
                                        label="Last Page",
                                        value=0,
                                        precision=0,
                                    )
                                batch_deskew = gr.Checkbox(
                                    label="Enable Deskewing",
                                    value=True,
                                )
                                batch_tf = gr.Checkbox(
                                    label="Use TensorFlow",
                                    value=False,
                                )
                                batch_musescore_input = gr.Textbox(
                                    label="MuseScore Executable Path",
                                    value=default_musescore or "",
                                )

                            batch_button = gr.Button(
                                "Convert Batch Scores (Outputs Zipped)",
                                variant="primary",
                                elem_classes="convert-btn",
                            )

                        with gr.Column(scale=9):
                            batch_status = gr.Markdown(
                                value=(
                                    "### Awaiting batch files\n\n"
                                    "Upload multiple PDFs to queue them for conversion."
                                ),
                            )
                            with gr.Group(elem_classes="download-card"):
                                batch_download_skeleton = gr.HTML(
                                    value=_DOWNLOAD_SKELETON_IDLE,
                                )
                                gr.HTML(
                                    '<p class="empty-download-hint">'
                                    "A ZIP archive will appear here when the batch finishes."
                                    "</p>"
                                )
                                gr.Markdown("### Zipped batch output")
                                batch_zip_output = gr.File(
                                    label="Download All Transcribed Scores (.zip)",
                                    interactive=False,
                                )

                with gr.TabItem("Model Checkpoints Manager"):
                    with gr.Column(elem_classes="glass-tab"):
                        gr.Markdown(
                            """
                            ### Manage OMR model checkpoints

                            PDF2Muse uses two pre-trained networks:
                            - **`unet_big`**: layout and staff segmentation
                            - **`seg_net`**: notes, clefs, and rhythm symbols

                            Models usually download on first run; use this tab to pre-fetch them on slow networks.
                            """
                        )
                        model_status = gr.Markdown(
                            value="*Checkpoints are verified in Pre-Flight Diagnostics.*"
                        )
                        download_btn = gr.Button("Download Checkpoints Now", variant="secondary")

                with gr.TabItem("Pre-Flight Diagnostics"):
                    with gr.Column(elem_classes="glass-tab"):
                        gr.Markdown("### System environment diagnostics")
                        diag_output = gr.Markdown(
                            value="*Click **Run System Check** to inspect dependencies.*"
                        )
                        diag_btn = gr.Button("Run System Check", variant="secondary")

            gr.HTML('<hr class="divider" />')

            with gr.Row():
                with gr.Column(scale=1):
                    gr.HTML(
                        """
                        <div class="requirement-card">
                            <h3>System preparation</h3>
                            <p>PDF2Muse uses these components for best results:</p>
                            <ul>
                                <li><strong>PDF rendering</strong>: Built-in via pypdfium2 (no Poppler).</li>
                                <li><strong>MuseScore</strong>: Optional; exports native `.mscx` from MusicXML.</li>
                            </ul>
                        </div>
                        """
                    )
                with gr.Column(scale=1):
                    gr.HTML(
                        """
                        <div class="tip-card">
                            <h3>Input tips for better drafts</h3>
                            <p>For the best chance of usable results:</p>
                            <ul>
                                <li>Use <strong>Preview first page (fast)</strong> before a full export.</li>
                                <li>Clean typeset PDFs work better than photos of books.</li>
                                <li>Avoid handwritten, tab-only, or chord-chart layouts.</li>
                                <li>Open MusicXML in MuseScore 3 or 4 to edit; treat output as a draft.</li>
                            </ul>
                        </div>
                        """
                    )

        convert_button.click(
            fn=convert_pdf,
            inputs=[
                pdf_input,
                deskew_checkbox,
                use_tf_checkbox,
                musescore_input,
                first_page_input,
                last_page_input,
                render_dpi_input,
                device_input,
                quality_profile_input,
                backend_input,
                preview_checkbox,
            ],
            outputs=[
                status_output,
                musicxml_output,
                mscx_output,
                download_skeleton,
                convert_button,
                review_output,
            ],
            show_progress="full",
        )

        batch_button.click(
            fn=convert_batch_pdfs,
            inputs=[
                batch_input,
                batch_deskew,
                batch_tf,
                batch_musescore_input,
                batch_first_page,
                batch_last_page,
            ],
            outputs=[
                batch_status,
                batch_zip_output,
                batch_download_skeleton,
                batch_button,
            ],
            show_progress="full",
        )

        download_btn.click(
            fn=download_checkpoints_ui,
            inputs=[],
            outputs=[model_status],
        )

        diag_btn.click(
            fn=run_diagnostics,
            inputs=[musescore_input],
            outputs=[diag_output],
        )

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch()
