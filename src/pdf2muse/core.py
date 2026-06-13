"""Core processing pipeline for PDF2Muse."""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

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
            musescore_path: Path to the MuseScore executable (default: None)
            first_page: First page of the PDF to convert (1-indexed, default: None)
            last_page: Last page of the PDF to convert (1-indexed, default: None)
        """
        self.pdf_path = Path(pdf_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.deskew = deskew
        self.use_tf = use_tf
        self.save_cache = save_cache
        self.musescore_path = Path(musescore_path).resolve() if musescore_path else None
        self.first_page = first_page
        self.last_page = last_page

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

            for i in range(start_idx, end_idx):
                page = pdf[i]
                # Render the page at 300 DPI (scale=4.166 for 72dpi base)
                # Standard PDF is 72 DPI. 300/72 = 4.166
                bitmap = page.render(scale=4.1666)
                pil_image = bitmap.to_pil()

                png_path = output_dir / f"page_{i:03d}.png"
                pil_image.save(str(png_path), "PNG")
                png_files.append(png_path)
                logger.debug(f"Saved page {i} to {png_path}")

            console.print(f"[green][OK][/green] Converted {len(png_files)} pages to images")
            return png_files

        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise RuntimeError(f"Failed to convert PDF to images: {e}") from e

    def process_image_with_oemer(
        self, image_path: Path, musicxml_dir: Path
    ) -> tuple[Optional[Path], Optional[str]]:
        """
        Process a single image with oemer to extract MusicXML.

        Each page runs in its own subdirectory under ``musicxml_dir`` so concurrent
        workers do not race on shared ``*.musicxml`` glob results.

        Args:
            image_path: Path to the PNG image
            musicxml_dir: Parent directory for per-page OMR outputs

        Returns:
            Tuple of (path to MusicXML in musicxml_dir, error message if failed)
        """
        logger.info(f"Processing {image_path.name} with oemer")

        page_dir = musicxml_dir / image_path.stem
        page_dir.mkdir(parents=True, exist_ok=True)

        oemer_module = "oemer.ete" if self.use_tf else "pdf2muse._oemer_cpu"
        command = [sys.executable, "-W", "ignore", "-m", oemer_module, str(image_path)]

        if not self.deskew:
            command.append("--without-deskew")
        if self.use_tf:
            command.append("--use-tf")
        if self.save_cache:
            command.append("--save-cache")

        try:
            env = os.environ.copy()
            env["OMP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

            result = subprocess.run(
                command,
                cwd=str(page_dir),
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(result.stdout)

            expected_musicxml = page_dir / f"{image_path.stem}.musicxml"
            musicxml_files = list(page_dir.glob("*.musicxml"))

            if not musicxml_files:
                return None, f"No MusicXML file generated for {image_path.name}"

            actual_file = next(
                (p for p in musicxml_files if p.name == expected_musicxml.name),
                musicxml_files[0],
            )

            combined_path = musicxml_dir / f"{image_path.stem}.musicxml"
            if actual_file.resolve() != combined_path.resolve():
                shutil.copy2(actual_file, combined_path)

            return combined_path, None

        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            snippet = stderr or stdout or str(e)
            if len(snippet) > 800:
                snippet = snippet[:800] + "..."
            logger.error(f"Error processing {image_path.name}: {snippet}")
            console.print(f"[yellow][WARN][/yellow] Failed to process {image_path.name}")
            return None, f"oemer failed on {image_path.name}: {snippet}"
        except Exception as e:
            logger.error(f"Unexpected error processing {image_path.name}: {e}")
            return None, f"Unexpected error on {image_path.name}: {e}"

    def run(self) -> Path:
        """
        Execute the full PDF to MusicXML/MuseScore conversion pipeline.

        Returns:
            Path to the final output file (MuseScore .mscx or MusicXML .musicxml fallback)
        """
        console.print("\n[bold cyan]PDF2Muse Pipeline[/bold cyan]")
        console.print(f"Input: {self.pdf_path}")
        console.print(f"Output: {self.output_dir}\n")

        console.print("[cyan]Checking oemer model checkpoints...[/cyan]")
        ensure_checkpoints()
        console.print("[green][OK][/green] Checkpoints ready\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_dir = temp_path / "images"
            musicxml_dir = temp_path / "musicxml"
            image_dir.mkdir()
            musicxml_dir.mkdir()

            png_files = self.pdf_to_png(image_dir)

            console.print(
                f"[cyan]Processing {len(png_files)} pages with oemer (concurrently)...[/cyan]"
            )

            max_workers = min(4, max(1, (os.cpu_count() or 2) // 2))
            logger.info(f"Running concurrent OMR pipeline with max_workers={max_workers}")

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
                                progress.update(task, description=f"Completed {filename}")
                            else:
                                if err:
                                    page_errors.append(err)
                                progress.update(task, description=f"Failed {filename}")
                        except Exception as e:
                            page_errors.append(f"{filename}: {e}")
                            logger.error(f"Error processing page {filename}: {e}")
                            progress.update(task, description=f"Failed {filename}")
                        progress.advance(task)

                musicxml_files = [res for res in results if res is not None]

            console.print(
                f"[green][OK][/green] Processed {len(musicxml_files)} pages successfully\n"
            )

            if not musicxml_files:
                detail = "\n".join(page_errors) if page_errors else "Unknown error"
                raise RuntimeError(f"No MusicXML files were generated.\n{detail}")

            console.print("[cyan]Joining MusicXML files...[/cyan]")
            combined_musicxml = self.output_dir / "combined.musicxml"
            join_musicxml_files(musicxml_dir, combined_musicxml)
            console.print("[green][OK][/green] Created combined MusicXML\n")

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
