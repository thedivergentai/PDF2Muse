"""Utilities for working with MusicXML files."""

import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def join_musicxml_files(input_dir: Path, output_file: Path) -> None:
    """
    Join multiple MusicXML files into a single file by appending measures.

    Args:
        input_dir: Directory containing MusicXML files
        output_file: Path to save the combined MusicXML file
    """
    input_path = Path(input_dir)
    output_path = Path(output_file)

    # Get sorted list of MusicXML files
    musicxml_files = sorted(input_path.glob("*.musicxml"))

    if not musicxml_files:
        logger.warning(f"No MusicXML files found in {input_dir}")
        console.print("[yellow]⚠[/yellow] No MusicXML files found")
        return

    logger.info(f"Joining {len(musicxml_files)} MusicXML files")

    # Parse the first file as the base
    tree = ET.parse(str(musicxml_files[0]))
    root = tree.getroot()

    # Find the part elements
    parts = root.findall("part")

    # Process remaining files
    for musicxml_file in musicxml_files[1:]:
        logger.debug(f"Adding {musicxml_file.name}")
        try:
            tree = ET.parse(str(musicxml_file))
            new_root = tree.getroot()
            new_parts = new_root.findall("part")

            # Append measures from each part
            for i, new_part in enumerate(new_parts):
                if i < len(parts):
                    # Append measures to existing part
                    for measure in new_part.findall("measure"):
                        parts[i].append(measure)
                else:
                    # Add new part if it doesn't exist
                    parts.append(new_part)
                    root.append(new_part)

        except ET.ParseError as e:
            logger.error(f"Error parsing {musicxml_file.name}: {e}")
            console.print(f"[yellow]⚠[/yellow] Skipped {musicxml_file.name} (parse error)")
            continue

    # Write the combined file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Pretty print
    tree.write(
        str(output_path),
        encoding="UTF-8",
        xml_declaration=True,
    )

    logger.info(f"Saved combined MusicXML to {output_file}")


def find_musescore_binary(custom_path: Optional[Path] = None) -> Optional[Path]:
    """
    Locate the MuseScore binary on the system.

    Args:
        custom_path: An optional custom path specified by the user

    Returns:
        Path to the MuseScore binary, or None if not found
    """
    if custom_path:
        custom_path = Path(custom_path)
        if custom_path.exists():
            return custom_path
        logger.warning(f"Specified MuseScore path does not exist: {custom_path}")

    # 1. Search in PATH
    for candidate in ["MuseScore4", "MuseScore3", "mscore", "mscore3", "musescore"]:
        path = shutil.which(candidate)
        if path:
            return Path(path)

    # 2. Search common installation directories
    if os.name == "nt":  # Windows
        common_paths = [
            Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"),
            Path(r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe"),
            Path(r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe"),
        ]
        for path in common_paths:
            if path.exists():
                return path
    elif sys_platform := os.uname().sysname if hasattr(os, "uname") else "":  # Unix-like
        if "Darwin" in sys_platform:  # macOS
            mac_paths = [
                Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore"),
                Path("/Applications/MuseScore 3.app/Contents/MacOS/mscore"),
            ]
            for path in mac_paths:
                if path.exists():
                    return path

    return None


def convert_to_musescore_format(
    input_file: Path,
    output_file: Path,
    format: str = "mscx",
    musescore_path: Optional[Path] = None,
) -> None:
    """
    Convert a MusicXML file to MuseScore format (.mscx) using the MuseScore CLI.

    Args:
        input_file: Path to the input MusicXML file
        output_file: Path to save the MuseScore file
        format: Output format (only 'mscx' is supported)
        musescore_path: Path to the MuseScore executable (optional)
    """
    if format != "mscx":
        raise ValueError(f"Unsupported format: {format}. Only 'mscx' is supported.")

    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Find the MuseScore executable
    mscore_binary = find_musescore_binary(musescore_path)

    if not mscore_binary:
        raise RuntimeError(
            "MuseScore executable not found. Please install MuseScore or specify its path "
            "to enable automatic conversion to MuseScore (.mscx) format."
        )

    logger.info(f"Using MuseScore binary: {mscore_binary}")
    console.print("[cyan]Converting via MuseScore CLI...[/cyan]")

    try:
        # Run conversion command: mscore -o output.mscx input.musicxml
        # We run MuseScore in conversion mode which is headless and extremely fast
        result = subprocess.run(
            [str(mscore_binary), "-o", str(output_path), str(input_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.debug(result.stdout)
        logger.info(f"Successfully converted {input_file} to {output_file}")

    except subprocess.CalledProcessError as e:
        logger.error(f"MuseScore CLI failed: {e.stderr}")
        raise RuntimeError(f"MuseScore conversion failed: {e.stderr}") from e
    except Exception as e:
        logger.error(f"Failed to execute MuseScore: {e}")
        raise RuntimeError(f"Failed to execute MuseScore: {e}") from e
