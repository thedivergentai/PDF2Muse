"""Command-line interface for PDF2Muse."""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from . import __version__
from .core import PDF2MusePipeline
from .oemer_utils import download_checkpoints

# Initialize Typer app
app = typer.Typer(
    name="pdf2muse",
    help="Convert PDF sheet music to MusicXML and MuseScore formats",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        console.print(f"pdf2muse version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
):
    """PDF2Muse - Convert PDF sheet music to MusicXML and MuseScore formats."""
    pass


@app.command()
def convert(
    pdf_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the PDF file to convert",
    ),
    output_dir: Path = typer.Option(
        "output",
        "--output",
        "-o",
        help="Directory to save output files",
    ),
    deskew: bool = typer.Option(
        True,
        "--deskew/--no-deskew",
        help="Enable or disable image deskewing",
    ),
    use_tf: bool = typer.Option(
        False,
        "--use-tf",
        help="Use TensorFlow instead of ONNX Runtime",
    ),
    save_cache: bool = typer.Option(
        False,
        "--save-cache",
        help="Save model predictions for future use",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
):
    """
    Convert a PDF sheet music file to MusicXML and MuseScore formats.

    This command processes a PDF file containing sheet music and converts it
    to machine-readable MusicXML and MuseScore (.mscx) formats using optical
    music recognition (OMR).

    Example:
        pdf2muse convert sheet_music.pdf -o ./output
    """
    setup_logging(verbose)

    try:
        pipeline = PDF2MusePipeline(
            pdf_path=str(pdf_path),
            output_dir=str(output_dir),
            deskew=deskew,
            use_tf=use_tf,
            save_cache=save_cache,
        )
        pipeline.run()

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


@app.command()
def ui(
    share: bool = typer.Option(
        False,
        "--share",
        help="Create a public shareable link",
    ),
    port: int = typer.Option(
        7860,
        "--port",
        "-p",
        help="Port to run the server on",
    ),
):
    """
    Launch the Gradio web interface for PDF2Muse.

    This starts a web server with an interactive interface for converting
    PDF files to MusicXML and MuseScore formats.

    Example:
        pdf2muse ui --port 8080
    """
    try:
        from .ui import create_interface
        
        interface = create_interface()
        interface.launch(
            server_port=port,
            share=share,
            show_error=True,
        )

    except ImportError as e:
        console.print(f"[red]Error:[/red] Gradio is not installed")
        console.print("Install it with: pip install 'pdf2muse[gradio]' or pip install gradio")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def download_models(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-download even if checkpoints exist",
    ),
):
    """
    Download oemer model checkpoints.

    This command downloads the pre-trained machine learning models required
    for optical music recognition. The models are downloaded automatically
    when needed, but you can use this command to pre-download them.

    Example:
        pdf2muse download-models
    """
    try:
        console.print("[cyan]Downloading oemer model checkpoints...[/cyan]\n")
        download_checkpoints(force=force)
        console.print("\n[green]✓[/green] Download complete!")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
