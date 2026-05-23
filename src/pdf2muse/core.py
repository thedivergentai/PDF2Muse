"""Core processing pipeline for PDF2Muse."""

import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        poppler_path: Optional[str] = None,
        musescore_path: Optional[str] = None,
        first_page: Optional[int] = None,
        last_page: Optional[int] = None,
    ):
        """
        Initialize the PDF2Muse pipeline.

        Args:
            pdf_path: Path to the input PDF file
            output_dir: Directory to save output files
            deskew: Whether to perform deskewing (default: True)
            use_tf: Use TensorFlow for model inference (default: False, uses ONNX)
            save_cache: Save model predictions for future use (default: False)
            poppler_path: Path to the poppler bin directory (default: None)
            musescore_path: Path to the MuseScore executable (default: None)
            first_page: First page of the PDF to convert (1-indexed, default: None)
            last_page: Last page of the PDF to convert (1-indexed, default: None)
        """
        self.pdf_path = Path(pdf_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.deskew = deskew
        self.use_tf = use_tf
        self.save_cache = save_cache
        self.poppler_path = Path(poppler_path).resolve() if poppler_path else None
        self.musescore_path = Path(musescore_path).resolve() if musescore_path else None
        self.first_page = first_page
        self.last_page = last_page

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
        console.print("[cyan]Converting PDF to images...[/cyan]")

        try:
            convert_args = {}
            if self.poppler_path:
                convert_args["poppler_path"] = str(self.poppler_path)
            if self.first_page:
                convert_args["first_page"] = self.first_page
            if self.last_page:
                convert_args["last_page"] = self.last_page
            
            images = convert_from_path(str(self.pdf_path), **convert_args)
            png_files = []

            for i, image in enumerate(images):
                page_num = self.first_page + i if self.first_page else i
                png_path = output_dir / f"page_{page_num:03d}.png"
                image.save(str(png_path), "PNG")
                png_files.append(png_path)
                logger.debug(f"Saved page {page_num} to {png_path}")

            console.print(f"[green][OK][/green] Converted {len(png_files)} pages to images")
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

        # Invoke oemer via sys.executable, ignoring unpickling warnings, to ensure it runs in the active virtual environment
        command = [sys.executable, "-W", "ignore", "-m", "oemer.ete", str(image_path)]
        
        if not self.deskew:
            command.append("--without-deskew")
        if self.use_tf:
            command.append("--use-tf")
        if self.save_cache:
            command.append("--save-cache")

        try:
            # Limit thread allocation inside ONNX Runtime CPU. This prevents a memory spike and 
            # bad_alloc crash when running multiple large session graphs in a single process.
            env = os.environ.copy()
            env["OMP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

            # Run oemer and capture output
            result = subprocess.run(
                command,
                cwd=str(musicxml_dir),
                env=env,
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
            console.print(f"[yellow][WARN][/yellow] Failed to process {image_path.name}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing {image_path.name}: {e}")
            return None

    def run(self) -> Path:
        """
        Execute the full PDF to MusicXML/MuseScore conversion pipeline.

        Returns:
            Path to the final output file (MuseScore .mscx or MusicXML .musicxml fallback)
        """
        console.print("\n[bold cyan]PDF2Muse Pipeline[/bold cyan]")
        console.print(f"Input: {self.pdf_path}")
        console.print(f"Output: {self.output_dir}\n")

        # Ensure oemer checkpoints are available
        console.print("[cyan]Checking oemer model checkpoints...[/cyan]")
        ensure_checkpoints()
        console.print("[green][OK][/green] Checkpoints ready\n")

        # Create temporary directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_dir = temp_path / "images"
            musicxml_dir = temp_path / "musicxml"
            image_dir.mkdir()
            musicxml_dir.mkdir()

            # Step 1: Convert PDF to PNG images
            png_files = self.pdf_to_png(image_dir)

            # Step 2: Process each image with oemer (concurrently)
            console.print(f"[cyan]Processing {len(png_files)} pages with oemer (concurrently)...[/cyan]")
            
            # Determine maximum concurrent workers based on CPU cores. Limit to 4 to avoid memory spikes.
            max_workers = min(4, max(1, (os.cpu_count() or 2) // 2))
            logger.info(f"Running concurrent OMR pipeline with max_workers={max_workers}")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing pages...", total=len(png_files))
                
                results = [None] * len(png_files)
                futures = {}
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for i, png_file in enumerate(png_files):
                        future = executor.submit(self.process_image_with_oemer, png_file, musicxml_dir)
                        futures[future] = (i, png_file.name)
                    
                    for future in as_completed(futures):
                        idx, filename = futures[future]
                        try:
                            musicxml_file = future.result()
                            if musicxml_file:
                                results[idx] = musicxml_file
                            progress.update(task, description=f"Completed {filename}")
                        except Exception as e:
                            logger.error(f"Error processing page {filename}: {e}")
                            progress.update(task, description=f"Failed {filename}")
                        progress.advance(task)
                
                musicxml_files = [res for res in results if res is not None]

            console.print(f"[green][OK][/green] Processed {len(musicxml_files)} pages successfully\n")

            if not musicxml_files:
                raise RuntimeError("No MusicXML files were generated")

            # Step 3: Join MusicXML files
            console.print("[cyan]Joining MusicXML files...[/cyan]")
            combined_musicxml = self.output_dir / "combined.musicxml"
            join_musicxml_files(musicxml_dir, combined_musicxml)
            console.print("[green][OK][/green] Created combined MusicXML\n")

            # Step 4: Convert to MuseScore format
            console.print("[cyan]Converting to MuseScore format...[/cyan]")
            musescore_file = self.output_dir / "combined.mscx"
            
            try:
                convert_to_musescore_format(
                    combined_musicxml,
                    musescore_file,
                    musescore_path=self.musescore_path,
                )
                console.print("[green][OK][/green] Created MuseScore file\n")
                result_file = musescore_file
            except Exception as e:
                console.print(f"[yellow][WARN][/yellow] MuseScore conversion skipped: {e}")
                console.print("[cyan]Falling back to using MusicXML file directly.[/cyan]\n")
                result_file = combined_musicxml

        console.print("[bold green]Conversion complete![/bold green]")
        console.print("Output files:")
        console.print(f"  - Primary Result: {result_file}\n")

        return result_file
