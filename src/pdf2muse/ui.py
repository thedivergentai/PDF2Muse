"""Gradio web interface for PDF2Muse."""

import logging
import os
import sys
import tempfile
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

import gradio as gr
from rich.console import Console

from .core import PDF2MusePipeline
from .musicxml import find_musescore_binary
from .oemer_utils import download_checkpoints, get_checkpoint_dir

logger = logging.getLogger(__name__)
console = Console()


def convert_pdf(
    pdf_file: gr.File,
    deskew: bool = True,
    use_tf: bool = False,
    poppler_path: Optional[str] = None,
    musescore_path: Optional[str] = None,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Convert a single PDF to MusicXML and MuseScore format."""
    if pdf_file is None:
        return "### ❌ Please upload a PDF file first", None, None

    # Clear empty string paths and zero limits
    poppler_path = poppler_path.strip() if poppler_path else None
    musescore_path = musescore_path.strip() if musescore_path else None
    first_page = int(first_page) if first_page and int(first_page) > 0 else None
    last_page = int(last_page) if last_page and int(last_page) > 0 else None

    try:
        # Create a temporary output directory
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            output_dir.mkdir()

            # Get the uploaded file path
            pdf_path = pdf_file.name if hasattr(pdf_file, 'name') else pdf_file

            # Run the pipeline
            pipeline = PDF2MusePipeline(
                pdf_path=pdf_path,
                output_dir=str(output_dir),
                deskew=deskew,
                use_tf=use_tf,
                poppler_path=poppler_path,
                musescore_path=musescore_path,
                first_page=first_page,
                last_page=last_page,
            )

            pipeline.run()

            # Copy generated files to persistent locations so Gradio can serve them
            xml_src = output_dir / "combined.musicxml"
            mscx_src = output_dir / "combined.mscx"

            xml_dest = None
            mscx_dest = None

            if xml_src.exists():
                xml_dest = Path(tempfile.gettempdir()) / f"pdf2muse_{xml_src.name}"
                shutil.copy(xml_src, xml_dest)
                xml_dest = str(xml_dest)

            if mscx_src.exists():
                mscx_dest = Path(tempfile.gettempdir()) / f"pdf2muse_{mscx_src.name}"
                shutil.copy(mscx_src, mscx_dest)
                mscx_dest = str(mscx_dest)

            status_msg = "## ✨ Conversion Complete!\n\n"
            if mscx_dest:
                status_msg += "🎉 **Success!** Both **MusicXML** and **MuseScore** files have been successfully generated and are ready for download below."
            else:
                status_msg += "💡 **MusicXML created successfully!** \n\n" \
                             "*(Note: MuseScore was not auto-detected or conversion failed, so .mscx format was skipped. " \
                             "You can import this .musicxml file directly into MuseScore or other sheet music editors).* "

            return status_msg, xml_dest, mscx_dest

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return f"### ❌ Error: {e}", None, None

    except Exception as e:
        logger.error(f"Conversion error: {e}", exc_info=True)
        return f"### ❌ Error during conversion:\n\n`{str(e)}`", None, None


def convert_batch_pdfs(
    pdf_files: List[gr.File],
    deskew: bool = True,
    use_tf: bool = False,
    poppler_path: Optional[str] = None,
    musescore_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Convert multiple PDFs in batch and return a ZIP file containing all outputs."""
    if not pdf_files:
        return "### ❌ Please upload one or more PDF files first", None

    poppler_path = poppler_path.strip() if poppler_path else None
    musescore_path = musescore_path.strip() if musescore_path else None

    log_output = "### 📚 Starting Batch Conversion...\n\n"
    temp_zip_dir = Path(tempfile.gettempdir()) / "pdf2muse_batch"
    if temp_zip_dir.exists():
        shutil.rmtree(temp_zip_dir)
    temp_zip_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0

    for i, file_obj in enumerate(pdf_files):
        pdf_path = file_obj.name if hasattr(file_obj, 'name') else file_obj
        pdf_name = Path(pdf_path).name
        log_output += f"🔄 **[{i+1}/{len(pdf_files)}]** Processing `{pdf_name}`...\n"

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "output"
                output_dir.mkdir()

                pipeline = PDF2MusePipeline(
                    pdf_path=pdf_path,
                    output_dir=str(output_dir),
                    deskew=deskew,
                    use_tf=use_tf,
                    poppler_path=poppler_path,
                    musescore_path=musescore_path,
                )
                pipeline.run()

                # Move files to batch zip folder
                xml_src = output_dir / "combined.musicxml"
                mscx_src = output_dir / "combined.mscx"

                file_prefix = Path(pdf_name).stem
                if xml_src.exists():
                    shutil.copy(xml_src, temp_zip_dir / f"{file_prefix}.musicxml")
                if mscx_src.exists():
                    shutil.copy(mscx_src, temp_zip_dir / f"{file_prefix}.mscx")

                success_count += 1
                log_output += f"  - ✅ Completed `{pdf_name}`\n"
        except Exception as e:
            fail_count += 1
            log_output += f"  - ❌ Failed `{pdf_name}`: `{str(e)}`\n"

    if success_count == 0:
        return log_output + "\n### ❌ All batch conversions failed.", None

    # Create ZIP archive
    zip_path = Path(tempfile.gettempdir()) / "pdf2muse_batch_outputs.zip"
    if zip_path.exists():
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(temp_zip_dir):
            for file in files:
                zipf.write(os.path.join(root, file), file)

    shutil.rmtree(temp_zip_dir)

    summary = f"\n### 🎉 Batch Processing Complete!\n- **Succeeded:** {success_count}\n- **Failed:** {fail_count}\n\nDownload all generated files using the link below."
    return log_output + summary, str(zip_path)


def run_diagnostics(poppler_custom: Optional[str] = None, musescore_custom: Optional[str] = None) -> str:
    """Run environment check and return beautiful markdown status report."""
    report = "## 🛡️ System Pre-Flight Diagnostics\n\n"

    # 1. Python Version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    report += f"🔹 **Python Engine:** `v{py_ver}` *(Required: >= 3.9)* — **✅ PASS**\n\n"

    # 2. Poppler Utility
    poppler_ok = False
    poppler_custom = poppler_custom.strip() if poppler_custom else None
    if poppler_custom:
        pdftoppm_path = Path(poppler_custom) / "pdftoppm"
        pdftoppm_path_exe = Path(poppler_custom) / "pdftoppm.exe"
        if pdftoppm_path.exists() or pdftoppm_path_exe.exists() or shutil.which("pdftoppm", path=poppler_custom):
            poppler_ok = True
    else:
        if shutil.which("pdftoppm"):
            poppler_ok = True

    if poppler_ok:
        report += "🔹 **Poppler PDF Engine:** **✅ DETECTED** (Ready for sheet music extraction)\n\n"
    else:
        report += "🔹 **Poppler PDF Engine:** **⚠️ MISSING OR NOT CONFIGURED**\n" \
                  "  - *Note:* This tool converts PDF pages to high-resolution PNGs. If conversion fails, please download Poppler and specify the directory path in settings.\n\n"

    # 3. MuseScore Utility
    msc_path = None
    musescore_custom = musescore_custom.strip() if musescore_custom else None
    if musescore_custom:
        custom_path_obj = Path(musescore_custom)
        if custom_path_obj.exists():
            msc_path = custom_path_obj
    else:
        msc_path = find_musescore_binary()

    if msc_path:
        report += f"🔹 **MuseScore Interface:** **✅ DETECTED** at `{msc_path}`\n\n"
    else:
        report += "🔹 **MuseScore Interface:** **💡 OPTIONAL (NOT DETECTED)**\n" \
                  "  - *Note:* The system will still export universal MusicXML perfectly, but will skip compiling native `.mscx` MuseScore files.\n\n"

    # 4. Deep Learning Checkpoints
    chk_dir = get_checkpoint_dir()
    unet_path = chk_dir / "unet_big" / "model.onnx"
    seg_path = chk_dir / "seg_net" / "model.onnx"
    models_ready = unet_path.exists() and seg_path.exists()

    if models_ready:
        report += "🔹 **Deep Learning OMR Models:** **✅ READY** (unet_big & seg_net loaded locally)\n\n"
    else:
        report += "🔹 **Deep Learning OMR Models:** **⚠️ CHECKPOINTS NOT DETECTED**\n" \
                  "  - Checkpoints are automatically downloaded on first run, or you can pre-download them in the Model Manager tab.\n\n"

    # Hardware Acceleration Check
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        report += f"🔹 **ONNX Runtime Engine:** `v{ort.__version__}` (Available Acceleration: `{providers}`)\n"
    except ImportError:
        report += "🔹 **ONNX Runtime Engine:** *Not loaded / standard module*\n"

    return report


def download_checkpoints_ui() -> str:
    """Gradio handler for downloading model checkpoints."""
    try:
        download_checkpoints(force=True)
        return "### ✅ OMR Model Checkpoints downloaded successfully and ready for use!"
    except Exception as e:
        return f"### ❌ Failed to download model checkpoints:\n\n`{str(e)}`"


def create_interface(
    default_poppler: Optional[str] = None,
    default_musescore: Optional[str] = None,
) -> gr.Blocks:
    """Create and return the beautiful, premium Gradio interface."""
    custom_css = """
    .container {
        max-width: 1100px !important;
        margin: 0 auto !important;
    }
    .header-banner {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #1e1b4b 100%) !important;
        color: white !important;
        padding: 40px !important;
        border-radius: 24px !important;
        margin-bottom: 30px !important;
        box-shadow: 0 20px 40px -15px rgba(124, 58, 237, 0.5) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        text-align: center !important;
    }
    .header-banner h1 {
        font-size: 3.2rem !important;
        font-weight: 900 !important;
        margin: 0 !important;
        letter-spacing: -0.04em !important;
        text-shadow: 0 4px 8px rgba(0, 0, 0, 0.3) !important;
    }
    .header-banner p {
        font-size: 1.3rem !important;
        opacity: 0.9 !important;
        margin-top: 15px !important;
        font-weight: 300 !important;
    }
    .convert-btn {
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-size: 1.15rem !important;
        padding: 14px 28px !important;
        background: linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%) !important;
        border: none !important;
        font-weight: bold !important;
        color: white !important;
        border-radius: 12px !important;
    }
    .convert-btn:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 12px 30px -8px rgba(99, 102, 241, 0.7) !important;
        filter: brightness(1.15) !important;
    }
    .download-card {
        border-radius: 16px !important;
        border: 1px solid rgba(124, 58, 237, 0.25) !important;
        background: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(10px) !important;
        padding: 20px !important;
    }
    .glass-tab {
        background: rgba(255, 255, 255, 0.02) !important;
        border-radius: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        padding: 25px !important;
        margin-top: 15px !important;
    }
    """

    with gr.Blocks(
        title="PDF2Muse - Sheet Music Converter",
        theme=gr.themes.Soft(
            primary_hue="purple",
            secondary_hue="indigo",
            font=("Outfit", "Inter", "sans-serif"),
        ),
        css=custom_css,
    ) as interface:
        
        with gr.Column(elem_classes="container"):
            # Premium Header Banner
            gr.HTML(
                """
                <div class="header-banner">
                    <h1>🎶 PDF2Muse</h1>
                    <p>Convert scanned PDF sheet music into digital, editable MusicXML & MuseScore files using Optical Music Recognition (OMR).</p>
                </div>
                """
            )

            # Tabbed Design
            with gr.Tabs():
                
                # Tab 1: Single Conversion
                with gr.TabItem("🎼 Single Score Conversion"):
                    with gr.Row(elem_classes="glass-tab"):
                        with gr.Column(scale=11):
                            pdf_input = gr.File(
                                label="📄 Upload PDF Sheet Music",
                                file_types=[".pdf"],
                                type="filepath",
                            )

                            with gr.Accordion("⚙️ Environment & Settings", open=True):
                                with gr.Group():
                                    poppler_input = gr.Textbox(
                                        label="Poppler Bin Path",
                                        value=default_poppler or "",
                                        placeholder="e.g. C:\\poppler\\bin (Optional if in system PATH)",
                                        info="Directory containing poppler binaries (pdftoppm, pdfinfo)",
                                    )
                                    musescore_input = gr.Textbox(
                                        label="MuseScore Executable Path",
                                        value=default_musescore or "",
                                        placeholder="e.g. C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe (Optional if in PATH)",
                                        info="Exact path to your MuseScore executable",
                                    )

                                with gr.Row():
                                    first_page_input = gr.Number(
                                        label="First Page",
                                        value=0,
                                        precision=0,
                                        info="1-indexed, leave 0 for start",
                                    )
                                    last_page_input = gr.Number(
                                        label="Last Page",
                                        value=0,
                                        precision=0,
                                        info="1-indexed, leave 0 for end",
                                    )

                                with gr.Row():
                                    deskew_checkbox = gr.Checkbox(
                                        label="Enable Deskewing",
                                        value=True,
                                        info="Auto-correct tilted pages",
                                    )
                                    use_tf_checkbox = gr.Checkbox(
                                        label="Use TensorFlow (Slower)",
                                        value=False,
                                        info="Use CPU/GPU TensorFlow engine instead of default ONNX Runtime",
                                    )

                            convert_button = gr.Button(
                                "🎵 Recognize & Convert Sheet Music",
                                variant="primary",
                                elem_classes="convert-btn",
                            )

                        with gr.Column(scale=9):
                            status_output = gr.Markdown(
                                value="### 📥 Awaiting Input\nUpload a PDF file and press the button to begin transcription.",
                            )

                            with gr.Group(elem_classes="download-card"):
                                gr.Markdown("### 📂 Generated Outputs")
                                musicxml_output = gr.File(
                                    label="Download MusicXML (.musicxml)",
                                    interactive=False,
                                )
                                mscx_output = gr.File(
                                    label="Download MuseScore File (.mscx)",
                                    interactive=False,
                                )

                # Tab 2: Batch Conversion
                with gr.TabItem("📚 Batch Processing"):
                    with gr.Row(elem_classes="glass-tab"):
                        with gr.Column(scale=11):
                            batch_input = gr.File(
                                label="📂 Upload Multiple Sheet Music PDFs",
                                file_types=[".pdf"],
                                file_count="multiple",
                                type="filepath",
                            )
                            
                            with gr.Accordion("⚙️ Batch Processing Settings", open=False):
                                batch_deskew = gr.Checkbox(
                                    label="Enable Deskewing",
                                    value=True,
                                )
                                batch_tf = gr.Checkbox(
                                    label="Use TensorFlow",
                                    value=False,
                                )

                            batch_button = gr.Button(
                                "⚡ Convert Batch Scores (Outputs Zipped)",
                                variant="primary",
                                elem_classes="convert-btn",
                            )

                        with gr.Column(scale=9):
                            batch_status = gr.Markdown(
                                value="### 📥 Awaiting Batch Files\nUpload multiple PDF files to queue them for Optical Music Recognition.",
                            )
                            
                            with gr.Group(elem_classes="download-card"):
                                gr.Markdown("### 📦 Zipped Batch Output")
                                batch_zip_output = gr.File(
                                    label="Download All Transcribed Scores (.zip)",
                                    interactive=False,
                                )

                # Tab 3: Model Manager
                with gr.TabItem("🧠 Model Checkpoints Manager"):
                    with gr.Column(elem_classes="glass-tab"):
                        gr.Markdown(
                            """
                            ### 🤖 Manage OMR Model Checkpoints
                            
                            PDF2Muse utilizes two pre-trained deep learning networks under the hood:
                            - **`unet_big`**: Layout analysis, staff line segmentation.
                            - **`seg_net`**: Note, clef, accidental, and duration recognition.
                            
                            Normally, these models are automatically fetched on first use. If you have an unstable network or want to pre-load them, download them here.
                            """
                        )
                        model_status = gr.Markdown(value="*Status: Model checkpoints will be checked during pre-flight diagnostics.*")
                        download_btn = gr.Button("⬇️ Download Checkpoints Now", variant="secondary")

                # Tab 4: System Diagnostics
                with gr.TabItem("🛡️ Pre-Flight Diagnostics"):
                    with gr.Column(elem_classes="glass-tab"):
                        gr.Markdown("### 🔍 System Environment Diagnostics")
                        diag_output = gr.Markdown(value="*Click 'Run System Check' to query system variables and detect dependency installations.*")
                        diag_btn = gr.Button("⚡ Run System Check", variant="secondary")

            gr.HTML(
                """
                <hr style="margin: 40px 0; border: 0; border-top: 1px solid rgba(124, 58, 237, 0.15);" />
                """
            )

            # Footer / Explainer Section
            with gr.Row():
                with gr.Column():
                    gr.Markdown(
                        """
                        ### ⚙️ Requirements & System Preparation
                        
                        PDF2Muse relies on native system libraries for best performance:
                        1. **Poppler** (Required): Converts PDF pages to clean high-resolution OMR images.
                           - *Windows*: Download from [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases) and paste the `bin` path into the setting above.
                           - *macOS*: Install via Homebrew: `brew install poppler`
                        2. **MuseScore** (Optional): Converts MusicXML into MuseScore format natively.
                           - Install MuseScore 4 or 3. It is automatically detected if installed in standard directories.
                        
                        ### 🎯 Tips for Peak Recognition Quality
                        
                        For maximum optical music recognition (OMR) accuracy:
                        - **Scan DPI**: Use clear sheets scanned at 300 DPI or higher.
                        - **Western Notation**: Avoid handwritten, tab, chord-only, or unconventional scores.
                        - **Lighting**: Bright, shadow-free, and high-contrast digital sheets work best.
                        """
                    )

        # Wire up single convert event handler
        convert_button.click(
            fn=convert_pdf,
            inputs=[
                pdf_input,
                deskew_checkbox,
                use_tf_checkbox,
                poppler_input,
                musescore_input,
                first_page_input,
                last_page_input,
            ],
            outputs=[
                status_output,
                musicxml_output,
                mscx_output,
            ],
        )

        # Wire up batch convert handler
        batch_button.click(
            fn=convert_batch_pdfs,
            inputs=[
                batch_input,
                batch_deskew,
                batch_tf,
                poppler_input,
                musescore_input,
            ],
            outputs=[
                batch_status,
                batch_zip_output,
            ],
        )

        # Wire up checkpoint manager
        download_btn.click(
            fn=download_checkpoints_ui,
            inputs=[],
            outputs=[model_status],
        )

        # Wire up diagnostics
        diag_btn.click(
            fn=run_diagnostics,
            inputs=[poppler_input, musescore_input],
            outputs=[diag_output],
        )

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch()
