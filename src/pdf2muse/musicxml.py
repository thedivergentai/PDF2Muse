"""Utilities for working with MusicXML files."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def join_musicxml_files(input_dir: Path, output_file: Path) -> None:
    """
    Join multiple MusicXML files into a single file.

    This function combines MusicXML files by concatenating their measures
    into a single score. Each file is treated as a separate page/section.

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
        console.print(f"[yellow]⚠[/yellow] No MusicXML files found")
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


def convert_to_musescore_format(
    input_file: Path,
    output_file: Path,
    format: str = "mscx"
) -> None:
    """
    Convert a MusicXML file to MuseScore format (.mscx).

    Note: This creates a basic MuseScore wrapper around the MusicXML.
    For full compatibility, consider using MuseScore's command-line tool.

    Args:
        input_file: Path to the input MusicXML file
        output_file: Path to save the MuseScore file
        format: Output format (only 'mscx' is supported)
    """
    if format != "mscx":
        raise ValueError(f"Unsupported format: {format}. Only 'mscx' is supported.")

    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    try:
        # Parse the MusicXML file
        tree = ET.parse(str(input_path))
        root = tree.getroot()

        # Create MuseScore wrapper
        # Note: This is a simplified conversion. For production use,
        # consider using MuseScore's actual conversion tools.
        musescore_root = ET.Element("museScore", {"version": "4.20"})
        score = ET.SubElement(musescore_root, "Score")

        # Add metadata
        meta_tag = ET.SubElement(score, "metaTag", {"name": "source"})
        meta_tag.text = "PDF2Muse"

        # Copy parts from MusicXML
        part_list = root.find("part-list")
        if part_list is not None:
            score.append(part_list)

        for part in root.findall("part"):
            score.append(part)

        # Write the MuseScore file
        mscx_tree = ET.ElementTree(musescore_root)
        ET.indent(mscx_tree, space="  ")  # Pretty print
        mscx_tree.write(
            str(output_path),
            encoding="UTF-8",
            xml_declaration=True,
        )

        logger.info(f"Converted {input_file} to {output_file}")

    except ET.ParseError as e:
        logger.error(f"Error parsing MusicXML: {e}")
        raise RuntimeError(f"Failed to parse MusicXML: {e}") from e
    except Exception as e:
        logger.error(f"Error converting to MuseScore format: {e}")
        raise RuntimeError(f"Conversion failed: {e}") from e
