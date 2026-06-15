"""Command-line interface for PDF2Muse."""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from . import __version__
from .core import PDF2MusePipeline
from .degrade import degrade_directory
from .evaluation import EvaluationManifestError, run_evaluation
from .oemer_utils import download_checkpoints

# Initialize Typer app
app = typer.Typer(
    name="pdf2muse",
    help=(
        "Convert PDF sheet music to MusicXML and MuseScore formats.\n\n"
        "Common convert options:\n"
        "-o, --output DIR       Directory to save output files\n"
        "--no-deskew            Disable image deskewing\n"
        "--use-tf               Use TensorFlow instead of ONNX Runtime\n"
        "--save-cache           Save model predictions for future use\n"
        "--musescore-path PATH  Path to the MuseScore executable\n"
        "--first-page INTEGER   First page to convert (1-indexed)\n"
        "--last-page INTEGER    Last page to convert (1-indexed)\n"
        "evaluate               Run an experimental local OMR evaluation\n"
        "degrade                Create deterministic degraded image variants\n"
        "--verbose              Enable verbose logging\n\n"
        "Run `pdf2muse convert --help` for the full conversion reference."
    ),
    add_completion=False,
)

console = Console()


def configure_windows_stdio() -> None:
    """Use UTF-8 for stdout/stderr on Windows to avoid encoding errors."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    configure_windows_stdio()
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
    musescore_path: Optional[Path] = typer.Option(
        None,
        "--musescore-path",
        help="Path to the MuseScore executable (e.g. MuseScore4.exe)",
    ),
    first_page: Optional[int] = typer.Option(
        None,
        "--first-page",
        help="First page of the PDF to convert (1-indexed)",
    ),
    last_page: Optional[int] = typer.Option(
        None,
        "--last-page",
        help="Last page of the PDF to convert (1-indexed)",
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
        pdf2muse convert sheet_music.pdf -o ./output --first-page 1 --last-page 2
    """
    setup_logging(verbose)

    try:
        pipeline = PDF2MusePipeline(
            pdf_path=str(pdf_path),
            output_dir=str(output_dir),
            deskew=deskew,
            use_tf=use_tf,
            save_cache=save_cache,
            musescore_path=str(musescore_path) if musescore_path else None,
            first_page=first_page,
            last_page=last_page,
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
def evaluate(
    manifest: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a local evaluation manifest JSON file",
    ),
    output_dir: Path = typer.Option(
        "evaluation-output",
        "--output",
        "-o",
        help="Directory to save evaluation reports and per-sample outputs",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum number of manifest samples to evaluate",
    ),
    first_page: Optional[int] = typer.Option(
        None,
        "--first-page",
        help="Override first page for PDF samples (1-indexed)",
    ),
    last_page: Optional[int] = typer.Option(
        None,
        "--last-page",
        help="Override last page for PDF samples (1-indexed)",
    ),
    use_musicdiff: bool = typer.Option(
        True,
        "--musicdiff/--no-musicdiff",
        help="Enable or disable optional musicdiff/OMR-NED comparison",
    ),
):
    """
    Run an experimental OMR evaluation from a local manifest.

    The manifest points to local PDFs and ground-truth MusicXML files. Dataset
    downloads are intentionally handled outside this command.
    """
    try:
        summary = run_evaluation(
            manifest_path=manifest,
            output_dir=output_dir,
            limit=limit,
            first_page=first_page,
            last_page=last_page,
            use_musicdiff=use_musicdiff,
        )
        console.print(
            "[green][OK][/green] Evaluation complete: "
            f"{summary.completed_samples}/{summary.total_samples} completed, "
            f"{summary.failed_samples} failed"
        )
        console.print(f"Reports written to: {output_dir}")
    except EvaluationManifestError as e:
        console.print(f"[red]Manifest error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
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
    musescore_path: Optional[Path] = typer.Option(
        None,
        "--musescore-path",
        help="Default path to the MuseScore executable",
    ),
):
    """
    Launch the Gradio web interface for PDF2Muse.

    This starts a web server with an interactive interface for converting
    PDF files to MusicXML and MuseScore formats.

    Example:
        pdf2muse ui --port 8080
    """
    configure_windows_stdio()
    try:
        from .ui import create_interface

        interface = create_interface(
            default_musescore=str(musescore_path) if musescore_path else None,
        )
        interface.launch(
            server_port=port,
            share=share,
            show_error=True,
        )

    except ImportError:
        console.print("[red]Error:[/red] Gradio is not installed")
        console.print("Install it with: pip install 'pdf2muse[ui]' or pip install gradio")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def degrade(
    input_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Directory containing source score images",
    ),
    output_dir: Path = typer.Argument(
        ...,
        file_okay=False,
        dir_okay=True,
        help="Directory where degraded images and metadata will be written",
    ),
    profile: str = typer.Option(
        "scan-noise",
        "--profile",
        help="Degradation profile: scan-noise, blur, low-contrast, or shadow",
    ),
    seed: int = typer.Option(
        0,
        "--seed",
        help="Deterministic seed for repeatable degradation",
    ),
):
    """
    Create deterministic degraded image variants for OMR experiments.

    Ground-truth notation should stay linked externally through manifests; this
    command only writes transformed images and degradation metadata.
    """
    try:
        metadata = degrade_directory(
            input_dir=input_dir,
            output_dir=output_dir,
            profile=profile,
            seed=seed,
        )
        console.print(
            "[green][OK][/green] Degraded "
            f"{len(metadata.files)} images with profile '{profile}'"
        )
        console.print(f"Output written to: {output_dir}")
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
        console.print("\n[green][OK][/green] Download complete!")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
