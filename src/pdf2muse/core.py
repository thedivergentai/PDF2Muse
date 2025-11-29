"""Core processing pipeline for PDF2Muse."""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from pdf2image import convert_from_path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .musicxml import join_musicxml_files, convert_to_musescore_format
from .oemer_utils import ensure_checkpoints

logger = logging.getLogger(__name__)
console = Console()


class PDF2MusePipeline:
    """Main pipeline for converting PDF sheet music to MusicXML and MuseScore formats."""

    def __init__(
        self,
        pdf_path: str,
        output_dir: str = "output",
        deskew: bool = True,
        use_tf: bool = False,
        save_cache: bool = False,
    ):
        """
        Initialize the PDF2Muse pipeline.

        Args:
            pdf_path: Path to the input PDF file
            output_dir: Directory to save output files
            deskew: Whether to perform deskewing (default: True)
            use_tf: Use TensorFlow for model inference (default: False, uses ONNX)
            save_cache: Save model predictions for future use (default: False)
        """
        self.pdf_path = Path(pdf_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.deskew = deskew
        self.use_tf = use_tf
        self.save_cache = save_cache

        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def pdf_to_png(self, output_dir: Path) -> list[Path]:
        """
        Convert PDF pages to PNG images.

        Args:
            output_dir: Directory to save PNG images

        Returns:
            List of paths to generated PNG files
        """
        logger.info(f"Converting PDF to PNG images: {self.pdf_path}")
        console.print(f"[cyan]Converting PDF to images...[/cyan]")

        try:
            images = convert_from_path(str(self.pdf_path))
            png_files = []

            for i, image in enumerate(images):
                png_path = output_dir / f"page_{i:03d}.png"
                image.save(str(png_path), "PNG")
                png_files.append(png_path)
                logger.debug(f"Saved page {i} to {png_path}")

            console.print(f"[green]✓[/green] Converted {len(png_files)} pages to images")
            return png_files

        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise RuntimeError(f"Failed to convert PDF to images: {e}") from e

    def process_image_with_oemer(
        self, image_path: Path, musicxml_dir: Path
    ) -> Optional[Path]:
        """
        Process a single image with oemer to extract MusicXML.

        Args:
            image_path: Path to the PNG image
            musicxml_dir: Directory to save MusicXML output

        Returns:
            Path to generated MusicXML file, or None if processing failed
        """
        logger.info(f"Processing {image_path.name} with oemer")

        command = ["oemer", str(image_path)]
        
        if not self.deskew:
            command.append("--without-deskew")
        if self.use_tf:
            command.append("--use-tf")
        if self.save_cache:
            command.append("--save-cache")

        try:
            # Run oemer and capture output
            result = subprocess.run(
                command,
                cwd=str(musicxml_dir),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(result.stdout)

            # Find the generated MusicXML file
            # oemer typically creates a file with the same base name as the input
            expected_musicxml = musicxml_dir / f"{image_path.stem}.musicxml"
            
            # Look for any .musicxml file in the directory
            musicxml_files = list(musicxml_dir.glob("*.musicxml"))
            
            if musicxml_files:
                # Move the file to have the correct name
                actual_file = musicxml_files[-1]  # Get the most recent one
                if actual_file != expected_musicxml:
                    actual_file.rename(expected_musicxml)
                return expected_musicxml
            else:
                logger.warning(f"No MusicXML file generated for {image_path.name}")
                return None

        except subprocess.CalledProcessError as e:
            logger.error(f"Error processing {image_path.name}: {e.stderr}")
            console.print(f"[yellow]⚠[/yellow] Failed to process {image_path.name}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing {image_path.name}: {e}")
            return None

    def run(self) -> Path:
        """
        Execute the full PDF to MusicXML/MuseScore conversion pipeline.

        Returns:
            Path to the final MuseScore (.mscx) file
        """
        console.print(f"\n[bold cyan]PDF2Muse Pipeline[/bold cyan]")
        console.print(f"Input: {self.pdf_path}")
        console.print(f"Output: {self.output_dir}\n")

        # Ensure oemer checkpoints are available
        console.print("[cyan]Checking oemer model checkpoints...[/cyan]")
        ensure_checkpoints()
        console.print("[green]✓[/green] Checkpoints ready\n")

        # Create temporary directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_dir = temp_path / "images"
            musicxml_dir = temp_path / "musicxml"
            image_dir.mkdir()
            musicxml_dir.mkdir()

            # Step 1: Convert PDF to PNG images
            png_files = self.pdf_to_png(image_dir)

            # Step 2: Process each image with oemer
            console.print(f"[cyan]Processing {len(png_files)} pages with oemer...[/cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing pages...", total=len(png_files))
                
                musicxml_files = []
                for png_file in png_files:
                    progress.update(task, description=f"Processing {png_file.name}...")
                    musicxml_file = self.process_image_with_oemer(png_file, musicxml_dir)
                    if musicxml_file:
                        musicxml_files.append(musicxml_file)
                    progress.advance(task)

            console.print(f"[green]✓[/green] Processed {len(musicxml_files)} pages successfully\n")

            if not musicxml_files:
                raise RuntimeError("No MusicXML files were generated")

            # Step 3: Join MusicXML files
            console.print("[cyan]Joining MusicXML files...[/cyan]")
            combined_musicxml = self.output_dir / "combined.musicxml"
            join_musicxml_files(musicxml_dir, combined_musicxml)
            console.print(f"[green]✓[/green] Created combined MusicXML\n")

            # Step 4: Convert to MuseScore format
            console.print("[cyan]Converting to MuseScore format...[/cyan]")
            musescore_file = self.output_dir / "combined.mscx"
            convert_to_musescore_format(combined_musicxml, musescore_file)
            console.print(f"[green]✓[/green] Created MuseScore file\n")

        console.print(f"[bold green]✨ Conversion complete![/bold green]")
        console.print(f"Output files:")
        console.print(f"  • MusicXML: {combined_musicxml}")
        console.print(f"  • MuseScore: {musescore_file}\n")

        return musescore_file
