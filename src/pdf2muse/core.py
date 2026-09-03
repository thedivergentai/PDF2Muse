"""Core processing pipeline for PDF2Muse."""

import json
import logging
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .adapters import OmrOptions, create_adapter, resolve_backend_config
from .header_lock import VALID_HEADER_MODES, lock_musicxml_header
from .musicxml import (
    join_musicxml_files,
    convert_to_musescore_format,
    analyze_musicxml_structure,
    validate_musicxml_file,
)
from ._oemer_common import _OEMER_PROFILE_PIXELS
from .oemer_utils import ensure_checkpoints, resolve_oemer_device

logger = logging.getLogger(__name__)
console = Console()

ProgressCallback = Callable[[float, str], None]


class PDF2MusePipeline:
    """Main pipeline for converting PDF sheet music to MusicXML and MuseScore formats."""

    def __init__(
        self,
        pdf_path: str,
        output_dir: str = "output",
        deskew: bool = True,
        use_tf: bool = False,
        save_cache: bool = False,
        musescore_path: Optional[str] = None,
        first_page: Optional[int] = None,
        last_page: Optional[int] = None,
        strict_musicxml: bool = False,
        model_backend: str = "oemer-stock",
        checkpoint_dir: Optional[str] = None,
        render_dpi: int = 360,
        oemer_timeout_seconds: int = 900,
        oemer_device: str = "auto",
        oemer_quality_profile: str = "quality",
        oemer_retries: bool = True,
        keep_page_artifacts: bool = False,
        quality_report: bool = True,
        header_lock_mode: str = "preserve",
    ):
        """
        Initialize the PDF2Muse pipeline.

        Args:
            pdf_path: Path to the input PDF file
            output_dir: Directory to save output files
            deskew: Whether to perform deskewing (default: True)
            use_tf: Use TensorFlow for model inference (default: False, uses ONNX)
            save_cache: Save model predictions for future use (default: False)
            musescore_path: Path to the MuseScore executable (default: None)
            first_page: First page of the PDF to convert (1-indexed, default: None)
            last_page: Last page of the PDF to convert (1-indexed, default: None)
            render_dpi: PDF render resolution for OMR input images
            oemer_timeout_seconds: Maximum seconds to allow one oemer page process
            oemer_device: ONNX path: auto (cuda when available), cpu, or cuda
            oemer_quality_profile: oemer input resize profile: fast, balanced, or quality
            oemer_retries: Retry known post-processing failures with alternate attempts
            keep_page_artifacts: Preserve rendered pages and per-attempt stdout/stderr
            quality_report: Include structural MusicXML quality details in reports
            header_lock_mode: ``preserve`` keeps mid-score key/time/tempo; ``lock``
                majority-votes and forces a single header (OMR cleanup for simple scores)
        """
        self.pdf_path = Path(pdf_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.deskew = deskew
        self.use_tf = use_tf
        self.save_cache = save_cache
        self.musescore_path = Path(musescore_path).resolve() if musescore_path else None
        self.first_page = first_page
        self.last_page = last_page
        self.strict_musicxml = strict_musicxml
        if render_dpi <= 0:
            raise ValueError("render_dpi must be greater than 0")
        self.render_dpi = render_dpi
        if oemer_timeout_seconds <= 0:
            raise ValueError("oemer_timeout_seconds must be greater than 0")
        self.oemer_timeout_seconds = oemer_timeout_seconds
        self.oemer_device = resolve_oemer_device(oemer_device)
        if oemer_quality_profile not in _OEMER_PROFILE_PIXELS:
            raise ValueError("oemer_quality_profile must be 'fast', 'balanced', or 'quality'")
        self.oemer_quality_profile = oemer_quality_profile
        self.oemer_retries = oemer_retries
        self.keep_page_artifacts = keep_page_artifacts
        self.quality_report = quality_report
        if header_lock_mode not in VALID_HEADER_MODES:
            raise ValueError(
                f"header_lock_mode must be one of {sorted(VALID_HEADER_MODES)}"
            )
        self.header_lock_mode = header_lock_mode
        self._page_attempts: dict[str, list[dict]] = {}
        self.conversion_report: dict = {}
        self.model_backend = resolve_backend_config(
            model_backend,
            checkpoint_dir=checkpoint_dir,
        )
        self._adapter = create_adapter(
            self.model_backend,
            oemer_retries=oemer_retries,
            quality_report=quality_report,
            keep_page_artifacts=keep_page_artifacts,
            artifact_root=self.output_dir / "pages",
        )

        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def pdf_to_png(self, output_dir: Path) -> list[Path]:
        """
        Convert PDF pages to PNG images using pypdfium2.

        Args:
            output_dir: Directory to save PNG images

        Returns:
            List of paths to generated PNG files
        """
        import pypdfium2 as pdfium

        logger.info(f"Converting PDF to PNG images: {self.pdf_path}")
        console.print("[cyan]Converting PDF to images...[/cyan]")

        try:
            pdf = pdfium.PdfDocument(str(self.pdf_path))
            png_files = []

            # Calculate range of pages to convert (0-indexed for pdfium, 1-indexed user options)
            start_idx = (self.first_page - 1) if self.first_page else 0
            end_idx = self.last_page if self.last_page else len(pdf)

            # Bound checks
            start_idx = max(0, min(start_idx, len(pdf)))
            end_idx = max(start_idx, min(end_idx, len(pdf)))

            try:
                for i in range(start_idx, end_idx):
                    page = pdf[i]
                    bitmap = None
                    try:
                        bitmap = page.render(scale=self.render_dpi / 72)
                        pil_image = bitmap.to_pil()
                        png_path = output_dir / f"page_{i:03d}.png"
                        pil_image.save(str(png_path), "PNG")
                        png_files.append(png_path)
                        logger.debug(f"Saved page {i} to {png_path}")
                    finally:
                        if bitmap is not None:
                            bitmap.close()
                        close_page = getattr(page, "close", None)
                        if callable(close_page):
                            close_page()
            finally:
                pdf.close()

            console.print(f"[green][OK][/green] Converted {len(png_files)} pages to images")
            return png_files

        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise RuntimeError(f"Failed to convert PDF to images: {e}") from e

    def _omr_options(self) -> OmrOptions:
        return OmrOptions(
            deskew=self.deskew,
            use_tf=self.use_tf,
            device=self.oemer_device,
            quality_profile=self.oemer_quality_profile,
            timeout_seconds=self.oemer_timeout_seconds,
            save_cache=self.save_cache,
            checkpoint_dir=self.model_backend.checkpoint_dir,
        )

    def process_image_with_oemer(
        self, image_path: Path, musicxml_dir: Path
    ) -> tuple[Optional[Path], Optional[str]]:
        """
        Process a single image with the active OMR adapter.

        Returns:
            Tuple of (path to MusicXML in musicxml_dir, error message if failed)
        """
        logger.info(f"Processing {image_path.name} with {self.model_backend.name}")
        result = self._adapter.recognize_page(
            image_path,
            musicxml_dir,
            self._omr_options(),
        )
        self._page_attempts[image_path.stem] = result.attempts
        if result.musicxml_path:
            return result.musicxml_path, None
        console.print(f"[yellow][WARN][/yellow] Failed to process {image_path.name}")
        return None, result.error

    def run(self, progress_callback: Optional[ProgressCallback] = None) -> Path:
        """
        Execute the full PDF to MusicXML/MuseScore conversion pipeline.

        Args:
            progress_callback: Optional ``(fraction, description)`` updates for UIs.

        Returns:
            Path to the final output file (MuseScore .mscx or MusicXML .musicxml fallback)
        """
        def notify(fraction: float, description: str) -> None:
            if progress_callback is not None:
                progress_callback(fraction, description)

        console.print("\n[bold cyan]PDF2Muse Pipeline[/bold cyan]")
        console.print(f"Input: {self.pdf_path}")
        console.print(f"Output: {self.output_dir}\n")
        report = {
            "input": str(self.pdf_path),
            "output_dir": str(self.output_dir),
            "strict_musicxml": self.strict_musicxml,
            "render_dpi": self.render_dpi,
            "oemer_timeout_seconds": self.oemer_timeout_seconds,
            "oemer_device": self.oemer_device,
            "oemer_quality_profile": self.oemer_quality_profile,
            "oemer_retries": self.oemer_retries,
            "keep_page_artifacts": self.keep_page_artifacts,
            "quality_report_enabled": self.quality_report,
            "header_lock_mode": self.header_lock_mode,
            "model_backend": {
                "name": self.model_backend.name,
                "kind": self.model_backend.kind,
                "checkpoint_dir": (
                    str(self.model_backend.checkpoint_dir)
                    if self.model_backend.checkpoint_dir
                    else None
                ),
                "experimental": self.model_backend.experimental,
            },
            "pages": [],
            "join": {},
            "flags": [],
            "final_musicxml": {"status": "not_run", "error": None},
            "musescore": {"status": "not_run", "error": None},
        }

        if self.model_backend.kind == "oemer":
            console.print("[cyan]Checking oemer model checkpoints...[/cyan]")
            notify(0.04, "Checking model checkpoints")
            ensure_checkpoints(
                checkpoint_dir=self.model_backend.checkpoint_dir,
                download_missing=not self.model_backend.experimental,
            )
            console.print("[green][OK][/green] Checkpoints ready\n")
            notify(0.08, "Checkpoints ready")
        else:
            console.print(
                f"[cyan]Skipping oemer checkpoints for backend "
                f"{self.model_backend.name}[/cyan]\n"
            )
            notify(0.08, f"Using {self.model_backend.name} backend")

        # Manual cleanup: Windows TemporaryDirectory teardown can raise Errno 22 and
        # mask the real conversion error or cascade into empty dirs for later samples.
        temp_dir_obj = tempfile.TemporaryDirectory()
        try:
            temp_path = Path(temp_dir_obj.name)
            image_dir = temp_path / "images"
            musicxml_dir = temp_path / "musicxml"
            image_dir.mkdir()
            musicxml_dir.mkdir()
            page_output_dir = self.output_dir / "pages"
            page_output_dir.mkdir(parents=True, exist_ok=True)

            png_files = self.pdf_to_png(image_dir)
            notify(0.15, f"Rendered {len(png_files)} page(s)")

            max_workers = min(4, max(1, (os.cpu_count() or 2) // 2))
            # One warm CUDA worker (or one GPU-bound subprocess) at a time.
            if self.oemer_device == "cuda" or os.environ.get("PDF2MUSE_OEMER_WORKER") == "1":
                max_workers = 1
            logger.info(f"Running concurrent OMR pipeline with max_workers={max_workers}")
            if max_workers == 1:
                console.print(
                    f"[cyan]Processing {len(png_files)} pages with oemer "
                    f"(serial; device={self.oemer_device})...[/cyan]"
                )
            else:
                console.print(
                    f"[cyan]Processing {len(png_files)} pages with oemer (concurrently)...[/cyan]"
                )

            page_errors: list[str] = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing pages...", total=len(png_files))

                results: list[Optional[Path]] = [None] * len(png_files)
                futures = {}

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for i, png_file in enumerate(png_files):
                        future = executor.submit(
                            self.process_image_with_oemer, png_file, musicxml_dir
                        )
                        futures[future] = (i, png_file.name)

                    for future in as_completed(futures):
                        idx, filename = futures[future]
                        try:
                            musicxml_file, err = future.result()
                            if musicxml_file:
                                results[idx] = musicxml_file
                                if self.keep_page_artifacts:
                                    durable_dir = page_output_dir / musicxml_file.stem
                                    durable_dir.mkdir(parents=True, exist_ok=True)
                                    durable_musicxml = durable_dir / musicxml_file.name
                                else:
                                    durable_musicxml = page_output_dir / musicxml_file.name
                                shutil.copy2(musicxml_file, durable_musicxml)
                                page_report = {
                                    "page": filename,
                                    "status": "completed",
                                    "musicxml_path": str(durable_musicxml),
                                    "error": None,
                                    "attempts": self._page_attempts.get(Path(filename).stem, []),
                                }
                                if self.quality_report:
                                    page_report["structure"] = asdict(
                                        analyze_musicxml_structure(durable_musicxml)
                                    )
                                report["pages"].append(page_report)
                                progress.update(task, description=f"Completed {filename}")
                                notify(
                                    0.2 + 0.55 * (sum(1 for r in results if r is not None) / len(png_files)),
                                    f"OMR {filename}",
                                )
                            else:
                                if err:
                                    page_errors.append(err)
                                report["pages"].append(
                                    {
                                        "page": filename,
                                        "status": "failed",
                                        "musicxml_path": None,
                                        "error": err,
                                        "attempts": self._page_attempts.get(
                                            Path(filename).stem, []
                                        ),
                                    }
                                )
                                progress.update(task, description=f"Failed {filename}")
                        except Exception as e:
                            page_errors.append(f"{filename}: {e}")
                            report["pages"].append(
                                {
                                    "page": filename,
                                    "status": "failed",
                                    "musicxml_path": None,
                                    "error": str(e),
                                    "attempts": self._page_attempts.get(Path(filename).stem, []),
                                }
                            )
                            logger.error(f"Error processing page {filename}: {e}")
                            progress.update(task, description=f"Failed {filename}")
                        progress.advance(task)

                musicxml_files = [res for res in results if res is not None]

            console.print(
                f"[green][OK][/green] Processed {len(musicxml_files)} pages successfully\n"
            )

            if not musicxml_files:
                detail = "\n".join(page_errors) if page_errors else "Unknown error"
                _write_conversion_report(self.output_dir / "conversion_report.json", report)
                raise RuntimeError(f"No MusicXML files were generated.\n{detail}")

            console.print("[cyan]Joining MusicXML files...[/cyan]")
            notify(0.82, "Joining MusicXML")
            combined_musicxml = self.output_dir / "combined.musicxml"
            try:
                join_report = join_musicxml_files(
                    musicxml_dir,
                    combined_musicxml,
                    strict=self.strict_musicxml,
                )
            except Exception as e:
                report["join"] = {
                    "status": "failed",
                    "error": str(e),
                    "failure_class": "join_failed",
                    "files_seen": len(musicxml_files),
                    "files_joined": 0,
                    "files_skipped": 0,
                    "skipped_files": [],
                    "warnings": [],
                    "engine": None,
                }
                report["final_musicxml"] = {
                    "status": "missing",
                    "path": str(combined_musicxml),
                    "error": str(e),
                }
                _write_conversion_report(self.output_dir / "conversion_report.json", report)
                raise
            report["join"] = _join_report_to_dict(join_report, len(musicxml_files))
            files_joined = getattr(join_report, "files_joined", 0)
            if not isinstance(files_joined, int):
                files_joined = 0
            if files_joined <= 0:
                report["join"]["status"] = "failed"
                report["join"]["failure_class"] = "join_empty"
                report["final_musicxml"] = {
                    "status": "missing",
                    "path": str(combined_musicxml),
                    "error": "No MusicXML files were joined",
                }
                _write_conversion_report(self.output_dir / "conversion_report.json", report)
                raise RuntimeError("Combined MusicXML join produced no pages")

            if not combined_musicxml.exists():
                final_validation = None
                report["final_musicxml"] = {
                    "status": "missing",
                    "path": str(combined_musicxml),
                    "error": "Combined MusicXML file was not written",
                }
            else:
                header_report = lock_musicxml_header(
                    combined_musicxml,
                    mode=self.header_lock_mode,
                )
                report["header_lock"] = asdict(header_report)
                if header_report.changed:
                    if header_report.mode == "preserve":
                        message = (
                            f"Segment respell: {header_report.notes_respelled} notes "
                            "in active keys"
                        )
                        console.print(f"[cyan]Header normalize:[/cyan] {message}\n")
                        report["flags"].append(
                            {"kind": "header_lock", "message": message}
                        )
                    else:
                        console.print(
                            f"[cyan]Header lock:[/cyan] "
                            f"{', '.join(header_report.actions)}\n"
                        )
                        if header_report.fifths is not None:
                            report["flags"].append(
                                {
                                    "kind": "header_lock",
                                    "message": (
                                        f"Locked key fifths={header_report.fifths}, "
                                        f"time={header_report.beats}/"
                                        f"{header_report.beat_type}, "
                                        f"tempo={header_report.tempo}"
                                    ),
                                }
                            )
                final_validation = validate_musicxml_file(combined_musicxml)
                report["final_musicxml"] = {
                    "status": "ok" if final_validation.ok else "failed",
                    "path": str(combined_musicxml),
                    "error": final_validation.error,
                }
                if self.quality_report:
                    report["final_musicxml"]["structure"] = asdict(
                        analyze_musicxml_structure(combined_musicxml)
                    )

            combined_ok = (
                combined_musicxml.exists()
                and final_validation is not None
                and final_validation.ok
            )
            if not combined_ok:
                _write_conversion_report(self.output_dir / "conversion_report.json", report)
                error = (
                    final_validation.error
                    if final_validation is not None
                    else "Combined MusicXML file was not written"
                )
                if self.strict_musicxml:
                    raise RuntimeError(f"Combined MusicXML is invalid: {error}")
                console.print(f"[yellow][WARN][/yellow] Combined MusicXML invalid: {error}\n")
                result_file = musicxml_files[0] if musicxml_files else combined_musicxml
            else:
                console.print("[green][OK][/green] Created combined MusicXML\n")
                result_file = combined_musicxml

                console.print("[cyan]Converting to MuseScore format...[/cyan]")
                notify(0.92, "MuseScore export")
                musescore_file = self.output_dir / "combined.mscx"

                try:
                    convert_to_musescore_format(
                        combined_musicxml,
                        musescore_file,
                        musescore_path=self.musescore_path,
                    )
                    if not musescore_file.exists() or musescore_file.stat().st_size <= 0:
                        raise RuntimeError(
                            f"MuseScore did not write a non-empty file: {musescore_file}"
                        )
                    console.print("[green][OK][/green] Created MuseScore file\n")
                    report["musescore"] = {
                        "status": "completed",
                        "path": str(musescore_file),
                        "import_export_ok": True,
                        "error": None,
                    }
                    result_file = musescore_file
                except Exception as e:
                    console.print(f"[yellow][WARN][/yellow] MuseScore conversion skipped: {e}")
                    console.print("[cyan]Falling back to using MusicXML file directly.[/cyan]\n")
                    report["musescore"] = {
                        "status": "skipped",
                        "path": None,
                        "import_export_ok": False,
                        "error": str(e),
                    }
                    result_file = combined_musicxml
        finally:
            try:
                temp_dir_obj.cleanup()
            except OSError as cleanup_exc:
                logger.warning(
                    "TemporaryDirectory cleanup failed (ignored): %s", cleanup_exc
                )

        _write_conversion_report(self.output_dir / "conversion_report.json", report)
        self.conversion_report = report
        notify(1.0, "Complete")
        console.print("[bold green]Conversion complete![/bold green]")
        console.print(
            "Quality status: "
            f"MusicXML {report['final_musicxml']['status']}; "
            "review generated notation before use."
        )
        console.print("Output files:")
        console.print(f"  - Primary Result: {result_file}\n")
        console.print(f"  - Conversion Report: {self.output_dir / 'conversion_report.json'}\n")

        return result_file


def _write_conversion_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _decode_subprocess_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _subprocess_output_snippet(stdout: object, stderr: object, max_length: int = 800) -> str:
    parts = []
    for value in (stderr, stdout):
        text = _decode_subprocess_output(value)
        text = text.strip()
        if text:
            parts.append(text)
    snippet = "\n".join(parts)
    if len(snippet) > max_length:
        return snippet[:max_length] + "..."
    return snippet


def _join_report_to_dict(join_report: object, default_seen: int) -> dict:
    def int_field(name: str, default: int) -> int:
        value = getattr(join_report, name, default)
        return value if isinstance(value, int) else default

    def list_field(name: str) -> list[str]:
        value = getattr(join_report, name, [])
        return value if isinstance(value, list) else []

    engine = getattr(join_report, "engine", None)
    return {
        "status": "ok",
        "files_seen": int_field("files_seen", default_seen),
        "files_joined": int_field("files_joined", default_seen),
        "files_skipped": int_field("files_skipped", 0),
        "skipped_files": list_field("skipped_files"),
        "warnings": list_field("warnings"),
        "engine": engine if isinstance(engine, str) else None,
        "failure_class": getattr(join_report, "failure_class", None),
    }
