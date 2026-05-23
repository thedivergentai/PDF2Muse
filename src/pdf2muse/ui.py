"""Gradio web interface for PDF2Muse."""

import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import gradio as gr
from rich.console import Console

from .core import PDF2MusePipeline

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
    """
    Convert a PDF to MusicXML and MuseScore format.

    Args:
        pdf_file: Uploaded PDF file
        deskew: Whether to perform deskewing
        use_tf: Use TensorFlow instead of ONNX
        poppler_path: Path to custom Poppler directory
        musescore_path: Path to custom MuseScore directory
        first_page: First page to convert (1-indexed)
        last_page: Last page to convert (1-indexed)

    Returns:
        Tuple of (status message in markdown, path to MusicXML file, path to MuseScore file)
    """
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
            import shutil
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


def create_interface(
    default_poppler: Optional[str] = None,
    default_musescore: Optional[str] = None,
) -> gr.Blocks:
    """
    Create and return the premium Gradio interface.

    Args:
        default_poppler: Optional initial value for poppler path
        default_musescore: Optional initial value for musescore path

    Returns:
        Gradio Blocks interface
    """
    custom_css = """
    .container {
        max-width: 1050px !important;
        margin: 0 auto !important;
    }
    .header-banner {
        background: linear-gradient(135deg, #581c87 0%, #1e1b4b 100%) !important;
        color: white !important;
        padding: 35px !important;
        border-radius: 20px !important;
        margin-bottom: 25px !important;
        box-shadow: 0 10px 25px -5px rgba(88, 28, 135, 0.4) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    .header-banner h1 {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        margin: 0 !important;
        letter-spacing: -0.03em !important;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3) !important;
    }
    .header-banner p {
        font-size: 1.2rem !important;
        opacity: 0.85 !important;
        margin-top: 12px !important;
    }
    .convert-btn {
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-size: 1.1rem !important;
        padding: 12px 24px !important;
        background: linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%) !important;
        border: none !important;
    }
    .convert-btn:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 25px -8px rgba(99, 102, 241, 0.6) !important;
        filter: brightness(1.1) !important;
    }
    .download-card {
        border-radius: 12px !important;
        border: 1px solid rgba(124, 58, 237, 0.2) !important;
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
        
        with gr.Div(elem_classes="container"):
            # Glassmorphism Top Banner
            gr.HTML(
                """
                <div class="header-banner">
                    <h1>🎶 PDF2Muse</h1>
                    <p>Convert scanned PDF sheet music into standard <strong>MusicXML</strong> and <strong>MuseScore</strong> files using Optical Music Recognition (OMR).</p>
                </div>
                """
            )

            with gr.Row():
                # Input Column
                with gr.Column(scale=11):
                    pdf_input = gr.File(
                        label="📄 Upload PDF Sheet Music",
                        file_types=[".pdf"],
                        type="filepath",
                    )

                    with gr.Accordion("⚙️ Environment & Recognition Settings", open=True):
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
                                placeholder="e.g. C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe (Optional if in system PATH)",
                                info="Exact path to your MuseScore executable to enable high-quality .mscx export",
                            )

                        with gr.Row():
                            first_page_input = gr.Number(
                                label="First Page to Convert",
                                value=0,
                                precision=0,
                                info="1-indexed, leave 0 for PDF start",
                            )
                            last_page_input = gr.Number(
                                label="Last Page to Convert",
                                value=0,
                                precision=0,
                                info="1-indexed, leave 0 for PDF end",
                            )

                        with gr.Row():
                            deskew_checkbox = gr.Checkbox(
                                label="Enable Deskewing",
                                value=True,
                                info="Automatically correct tilted pages before scanning",
                            )
                            use_tf_checkbox = gr.Checkbox(
                                label="Use TensorFlow (Slower)",
                                value=False,
                                info="Use TensorFlow inference instead of ONNX (requires CPU/GPU setup)",
                            )

                    convert_button = gr.Button(
                        "🎵 Recognize & Convert Sheet Music",
                        variant="primary",
                        size="lg",
                        elem_classes="convert-btn",
                    )

                # Output Column
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

        # Wire up event handler
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

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch()
