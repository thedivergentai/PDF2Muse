"""Utilities for working with MusicXML files."""

import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


@dataclass(frozen=True)
class MusicXmlValidationResult:
    """MusicXML parseability status for one file."""

    path: str
    ok: bool
    error: Optional[str] = None


@dataclass(frozen=True)
class MusicXmlJoinReport:
    """Summary of a multi-page MusicXML join operation."""

    files_seen: int
    files_joined: int
    files_skipped: int
    skipped_files: list[str]
    warnings: list[str]
    engine: str = "etree"
    failure_class: Optional[str] = None


@dataclass(frozen=True)
class MusicXmlStructureReport:
    """Basic structural quality indicators for generated MusicXML."""

    path: str
    parse_ok: bool
    root: Optional[str] = None
    parts: int = 0
    measures: int = 0
    notes: int = 0
    rests: int = 0
    pitched_notes: int = 0
    error: Optional[str] = None


def _local_name(tag: str) -> str:
    """Return an XML tag name without a namespace prefix."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(element: ET.Element, child_name: str) -> Optional[str]:
    child = element.find(child_name)
    return child.text.strip() if child is not None and child.text else None


class MusicXmlGateError(RuntimeError):
    """Raised when MusicXML fails a production validation gate."""


def validate_musicxml_file(path: Path, *, structural: bool = True) -> MusicXmlValidationResult:
    """Return whether a MusicXML file is well-formed and structurally usable."""

    musicxml_path = Path(path)
    try:
        root = ET.parse(str(musicxml_path)).getroot()
    except ET.ParseError as exc:
        return MusicXmlValidationResult(path=str(musicxml_path), ok=False, error=str(exc))
    except OSError as exc:
        return MusicXmlValidationResult(path=str(musicxml_path), ok=False, error=str(exc))

    if structural:
        root_name = _local_name(root.tag)
        if root_name not in {"score-partwise", "score-timewise"}:
            return MusicXmlValidationResult(
                path=str(musicxml_path),
                ok=False,
                error=f"Unexpected MusicXML root element: {root_name}",
            )
        structure = analyze_musicxml_structure(musicxml_path)
        if not structure.parse_ok:
            return MusicXmlValidationResult(
                path=str(musicxml_path), ok=False, error=structure.error
            )
        if structure.parts == 0 or structure.measures == 0:
            return MusicXmlValidationResult(
                path=str(musicxml_path),
                ok=False,
                error="MusicXML contains no parts or measures",
            )
    return MusicXmlValidationResult(path=str(musicxml_path), ok=True)


def analyze_musicxml_structure(path: Path) -> MusicXmlStructureReport:
    """Return parse and coarse notation counts for one MusicXML file."""

    musicxml_path = Path(path)
    try:
        root = ET.parse(str(musicxml_path)).getroot()
    except ET.ParseError as exc:
        return MusicXmlStructureReport(path=str(musicxml_path), parse_ok=False, error=str(exc))
    except OSError as exc:
        return MusicXmlStructureReport(path=str(musicxml_path), parse_ok=False, error=str(exc))

    root_name = _local_name(root.tag)
    parts = measures = notes = rests = pitched_notes = 0
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "part":
            parts += 1
        elif name == "measure":
            measures += 1
        elif name == "note":
            notes += 1
            if any(_local_name(child.tag) == "rest" for child in element):
                rests += 1
            if any(_local_name(child.tag) == "pitch" for child in element):
                pitched_notes += 1

    return MusicXmlStructureReport(
        path=str(musicxml_path),
        parse_ok=True,
        root=root_name,
        parts=parts,
        measures=measures,
        notes=notes,
        rests=rests,
        pitched_notes=pitched_notes,
    )


def _findall_local(parent: ET.Element, name: str) -> list[ET.Element]:
    return [el for el in parent if _local_name(el.tag) == name]


def _find_local(parent: ET.Element, name: str) -> Optional[ET.Element]:
    for el in parent:
        if _local_name(el.tag) == name:
            return el
    return None


def _join_with_music21(
    musicxml_files: list[Path],
    output_path: Path,
    *,
    strict: bool,
) -> MusicXmlJoinReport:
    """Join pages using music21 for measure-aware merging."""

    from music21 import converter

    skipped_files: list[str] = []
    warnings: list[str] = []
    combined = None
    joined_files = 0

    for musicxml_file in musicxml_files:
        try:
            score = converter.parse(str(musicxml_file))
        except Exception as exc:
            message = f"Invalid MusicXML in {musicxml_file.name}: {exc}"
            if strict:
                raise ValueError(message) from exc
            skipped_files.append(str(musicxml_file))
            warnings.append(message)
            continue

        if combined is None:
            combined = score
            joined_files = 1
            continue

        for index, part in enumerate(score.parts):
            if index < len(combined.parts):
                target = combined.parts[index]
                for measure in part.getElementsByClass("Measure"):
                    target.append(measure)
            else:
                combined.insert(0, part)
                warnings.append(f"Added new part from {musicxml_file.name}")
        joined_files += 1

    if combined is None:
        raise MusicXmlGateError("No valid MusicXML inputs to join")

    try:
        combined.write("musicxml", fp=str(output_path))
    except Exception as exc:
        # music21 makeNotation/makeTies often fails on complex OMR drafts even when
        # the page XML itself is parseable — caller must fall back to etree.
        raise MusicXmlGateError(
            f"join_music21_write_failed: music21 write failed: {exc}"
        ) from exc

    final_validation = validate_musicxml_file(output_path)
    if not final_validation.ok:
        raise MusicXmlGateError(f"Combined MusicXML failed validation: {final_validation.error}")

    return MusicXmlJoinReport(
        files_seen=len(musicxml_files),
        files_joined=joined_files,
        files_skipped=len(skipped_files),
        skipped_files=skipped_files,
        warnings=warnings,
        engine="music21",
    )


def _join_with_etree(
    musicxml_files: list[Path],
    output_path: Path,
    *,
    strict: bool,
    warnings: Optional[list[str]] = None,
) -> MusicXmlJoinReport:
    """Join pages by appending measures with ElementTree (namespace-aware)."""

    warnings = list(warnings or [])
    skipped_files: list[str] = []
    base_tree: Optional[ET.ElementTree] = None
    base_file: Optional[Path] = None
    for musicxml_file in musicxml_files:
        validation = validate_musicxml_file(musicxml_file)
        if not validation.ok:
            message = f"Invalid MusicXML in {musicxml_file.name}: {validation.error}"
            if strict:
                raise ValueError(message)
            logger.error(message)
            skipped_files.append(str(musicxml_file))
            warnings.append(message)
            continue
        try:
            base_tree = ET.parse(str(musicxml_file))
            base_file = musicxml_file
            break
        except ET.ParseError as e:
            message = f"Invalid MusicXML in {musicxml_file.name}: {e}"
            if strict:
                raise ValueError(message) from e
            skipped_files.append(str(musicxml_file))
            warnings.append(message)

    if base_tree is None or base_file is None:
        raise MusicXmlGateError(
            "No valid MusicXML inputs to join "
            f"(seen={len(musicxml_files)}, skipped={len(skipped_files)})"
        )

    root = base_tree.getroot()
    parts = _findall_local(root, "part")
    part_map = {_part_key(root, part): part for part in parts}
    joined_files = 1

    for musicxml_file in musicxml_files:
        if musicxml_file == base_file or musicxml_file in map(Path, skipped_files):
            continue
        validation = validate_musicxml_file(musicxml_file)
        if not validation.ok:
            message = f"Invalid MusicXML in {musicxml_file.name}: {validation.error}"
            if strict:
                raise ValueError(message)
            skipped_files.append(str(musicxml_file))
            warnings.append(message)
            continue
        logger.debug(f"Adding {musicxml_file.name}")
        try:
            tree = ET.parse(str(musicxml_file))
            new_root = tree.getroot()
            new_parts = _findall_local(new_root, "part")

            for new_part in new_parts:
                key = _part_key(new_root, new_part)
                target_part = part_map.get(key)
                if target_part is None:
                    target_part = deepcopy(new_part)
                    _append_part_list_entry(root, new_root, new_part)
                    root.append(target_part)
                    part_map[key] = target_part
                    warnings.append(f"Added new part from {musicxml_file.name}: {key}")
                    continue

                for measure in _findall_local(new_part, "measure"):
                    target_part.append(deepcopy(measure))
            joined_files += 1

        except ET.ParseError as e:
            message = f"Invalid MusicXML in {musicxml_file.name}: {e}"
            if strict:
                raise ValueError(message) from e
            skipped_files.append(str(musicxml_file))
            warnings.append(message)
            continue

    for part in _findall_local(root, "part"):
        for index, measure in enumerate(_findall_local(part, "measure"), start=1):
            measure.set("number", str(index))

    base_tree = ET.ElementTree(root)
    ET.indent(base_tree, space="  ")
    base_tree.write(
        str(output_path),
        encoding="UTF-8",
        xml_declaration=True,
    )

    final_validation = validate_musicxml_file(output_path)
    if not final_validation.ok:
        raise MusicXmlGateError(
            f"Combined MusicXML failed validation after etree join: {final_validation.error}"
        )
    if joined_files <= 0:
        raise MusicXmlGateError("No MusicXML files were joined")

    logger.info(f"Saved combined MusicXML to {output_path}")
    return MusicXmlJoinReport(
        files_seen=len(musicxml_files),
        files_joined=joined_files,
        files_skipped=len(skipped_files),
        skipped_files=skipped_files,
        warnings=warnings,
        engine="etree",
    )


def join_musicxml_file_list(
    musicxml_files: list[Path],
    output_file: Path,
    *,
    strict: bool = False,
) -> MusicXmlJoinReport:
    """Join an ordered list of MusicXML files (system crops or pages)."""

    output_path = Path(output_file)
    files = [Path(path) for path in musicxml_files]
    if not files:
        raise MusicXmlGateError("No MusicXML files found to join")
    if len(files) == 1:
        only = files[0]
        validation = validate_musicxml_file(only)
        if not validation.ok:
            raise MusicXmlGateError(
                f"Single-page MusicXML failed validation: {validation.error}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(only, output_path)
        return MusicXmlJoinReport(
            files_seen=1,
            files_joined=1,
            files_skipped=0,
            skipped_files=[],
            warnings=["single_page_copy"],
            engine="copy",
        )
    temp_dir = output_path.parent / f".join-{output_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, source in enumerate(files):
            dest = temp_dir / f"{index:03d}_{source.name}"
            shutil.copy2(source, dest)
        return join_musicxml_files(temp_dir, output_path, strict=strict)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def join_musicxml_files(
    input_dir: Path,
    output_file: Path,
    *,
    strict: bool = False,
) -> MusicXmlJoinReport:
    """
    Join multiple MusicXML files into a single file by appending measures.

    Args:
        input_dir: Directory containing MusicXML files
        output_file: Path to save the combined MusicXML file
    """
    input_path = Path(input_dir)
    output_path = Path(output_file)

    musicxml_files = sorted(input_path.glob("*.musicxml"))

    if not musicxml_files:
        logger.warning(f"No MusicXML files found in {input_dir}")
        console.print("[yellow]⚠[/yellow] No MusicXML files found")
        raise MusicXmlGateError("No MusicXML files found to join")

    logger.info(f"Joining {len(musicxml_files)} MusicXML files")

    # Single valid page: copy without music21 rewrite (avoids makeNotation crashes).
    if len(musicxml_files) == 1:
        only = musicxml_files[0]
        validation = validate_musicxml_file(only)
        if not validation.ok:
            raise MusicXmlGateError(
                f"Single-page MusicXML failed validation: {validation.error}"
            )
        shutil.copy2(only, output_path)
        return MusicXmlJoinReport(
            files_seen=1,
            files_joined=1,
            files_skipped=0,
            skipped_files=[],
            warnings=["single_page_copy"],
            engine="copy",
        )

    use_music21 = os.environ.get("PDF2MUSE_JOIN_ENGINE", "music21") != "etree"
    warnings: list[str] = []
    if use_music21:
        try:
            report = _join_with_music21(musicxml_files, output_path, strict=strict)
            # If music21 collapsed parts relative to page inputs, prefer etree structure.
            try:
                input_parts = max(
                    analyze_musicxml_structure(path).parts for path in musicxml_files
                )
                output_parts = analyze_musicxml_structure(output_path).parts
            except Exception:
                input_parts = output_parts = 0
            if input_parts > 0 and output_parts < input_parts:
                warnings.append(
                    f"music21 join collapsed parts ({output_parts}<{input_parts}); "
                    "falling back to etree"
                )
                logger.warning(warnings[-1])
            else:
                return report
        except ImportError:
            logger.debug("music21 not installed; falling back to ElementTree join")
            warnings.append("music21 not installed; using etree join")
        except MusicXmlGateError as exc:
            # Always allow etree recovery for write/makeNotation failures, even under strict.
            message = str(exc)
            if "join_music21_write_failed" in message or "write failed" in message.lower():
                warnings.append(message)
                logger.warning("music21 write failed; falling back to etree join: %s", exc)
            else:
                raise
        except Exception as exc:
            warnings.append(f"music21 join failed, using fallback: {exc}")
            logger.warning(warnings[-1])

    return _join_with_etree(
        musicxml_files,
        output_path,
        strict=strict,
        warnings=warnings,
    )


def _part_key(root: ET.Element, part: ET.Element) -> str:
    part_id = part.attrib.get("id")
    if part_id:
        return f"id:{part_id}"
    part_name = _part_name_for_id(root, part_id)
    return f"name:{part_name}" if part_name else "position:unknown"


def _part_name_for_id(root: ET.Element, part_id: Optional[str]) -> Optional[str]:
    if not part_id:
        return None
    part_list = _find_local(root, "part-list")
    if part_list is None:
        return None
    for score_part in _findall_local(part_list, "score-part"):
        if score_part.attrib.get("id") != part_id:
            continue
        part_name = _find_local(score_part, "part-name")
        if part_name is not None and part_name.text:
            return part_name.text
    return None


def _append_part_list_entry(root: ET.Element, new_root: ET.Element, new_part: ET.Element) -> None:
    part_list = _find_local(root, "part-list")
    new_part_list = _find_local(new_root, "part-list")
    part_id = new_part.attrib.get("id")
    if part_list is None:
        part_list = ET.Element("part-list")
        root.insert(0, part_list)
    if new_part_list is not None:
        for score_part in _findall_local(new_part_list, "score-part"):
            if score_part.attrib.get("id") == part_id:
                part_list.append(deepcopy(score_part))
                return
    # Synthesize a minimal score-part so we never attach an orphan <part>.
    score_part = ET.Element("score-part", {"id": part_id or "P_auto"})
    name_el = ET.SubElement(score_part, "part-name")
    name_el.text = part_id or "Music"
    part_list.append(score_part)


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
        command = [str(mscore_binary), "-f", "-o", str(output_path), str(input_path)]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.debug(result.stdout)
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(
                f"MuseScore exited 0 but did not write output file: {output_path}"
            )
        logger.info(f"Successfully converted {input_file} to {output_file}")

    except subprocess.CalledProcessError as e:
        logger.error(f"MuseScore CLI failed: {e.stderr}")
        raise RuntimeError(f"MuseScore conversion failed: {e.stderr}") from e
    except Exception as e:
        logger.error(f"Failed to execute MuseScore: {e}")
        raise RuntimeError(f"Failed to execute MuseScore: {e}") from e
