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
) -> Tuple[str, Optional[str]]:
    """
    Convert a PDF to MusicXML and MuseScore format.

    Args:
        pdf_file: Uploaded PDF file
        deskew: Whether to perform deskewing
        use_tf: Use TensorFlow instead of ONNX

    Returns:
        Tuple of (status message, path to MuseScore file)
    """
    if pdf_file is None:
        return "❌ Please upload a PDF file", None

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
            )

            musescore_file = pipeline.run()

            # Copy the output file to a permanent location for download
            # (Gradio needs a persistent path)
            import shutil
            output_file = Path(tempfile.gettempdir()) / f"pdf2muse_{musescore_file.name}"
            shutil.copy(musescore_file, output_file)

            return (
                f"✅ Conversion complete! Generated MuseScore file: {musescore_file.name}",
                str(output_file),
            )

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return f"❌ Error: {e}", None

    except Exception as e:
        logger.error(f"Conversion error: {e}", exc_info=True)
        return f"❌ Error during conversion: {str(e)}", None


def create_interface() -> gr.Blocks:
    """
    Create and return the Gradio interface.

    Returns:
        Gradio Blocks interface
    """
    with gr.Blocks(
        title="PDF2Muse - Sheet Music Converter",
        theme=gr.themes.Soft(),
    ) as interface:
        gr.Markdown(
            """
            # 🎶 PDF2Muse
            
            Convert PDF sheet music to **MusicXML** and **MuseScore** formats using 
            optical music recognition (OMR).
            
            ### How to use:
            1. Upload a PDF file containing sheet music
            2. Configure options (optional)
            3. Click "Convert" and wait for processing
            4. Download the generated MuseScore (.mscx) file
            
            ---
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                pdf_input = gr.File(
                    label="📄 Upload PDF Sheet Music",
                    file_types=[".pdf"],
                    type="filepath",
                )

                with gr.Accordion("⚙️ Advanced Options", open=False):
                    deskew_checkbox = gr.Checkbox(
                        label="Enable Deskewing",
                        value=True,
                        info="Automatically correct skewed images",
                    )

                    use_tf_checkbox = gr.Checkbox(
                        label="Use TensorFlow",
                        value=False,
                        info="Use TensorFlow instead of ONNX Runtime (slower but may be more accurate)",
                    )

                convert_button = gr.Button(
                    "🎵 Convert to MusicXML",
                    variant="primary",
                    size="lg",
                )

            with gr.Column(scale=1):
                status_output = gr.Textbox(
                    label="Status",
                    lines=3,
                    interactive=False,
                )

                mscx_output = gr.File(
                    label="📥 Download MuseScore File",
                )

        gr.Markdown(
            """
            ---
            
            ### About
            
            PDF2Muse uses the [oemer](https://github.com/BreezeWhite/oemer) optical music 
            recognition library to transcribe sheet music from PDF files.
            
            **Note:** The quality of the output depends on the quality and clarity of the 
            input PDF. Best results are achieved with:
            - High-resolution scans (300 DPI or higher)
            - Clear, uncluttered sheet music
            - Standard Western music notation
            
            ### Supported Formats
            
            - **Input:** PDF files
            - **Output:** MusicXML (.musicxml), MuseScore (.mscx)
            """
        )

        # Wire up the event handler
        convert_button.click(
            fn=convert_pdf,
            inputs=[pdf_input, deskew_checkbox, use_tf_checkbox],
            outputs=[status_output, mscx_output],
        )

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch()
