"""Measure-duration flags and reversible underfull rest fills."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .musicxml import _child_text, _findall_local, _find_local, _local_name


@dataclass
class MeasureFlag:
    part_id: str
    measure_number: str
    kind: str
    message: str
    expected: float
    actual: float


@dataclass
class RhythmRepairReport:
    path: str
    changed: bool = False
    flags: list[MeasureFlag] = field(default_factory=list)
    rests_appended: int = 0
    actions: list[str] = field(default_factory=list)


def _duration_unit(beats: int, beat_type: int, divisions: int) -> float:
    return divisions * beats * (4.0 / beat_type)


def _measure_duration(measure: ET.Element) -> float:
    total = 0.0
    for child in list(measure):
        name = _local_name(child.tag)
        if name == "note":
            if _find_local(child, "chord") is not None:
                continue
            if _find_local(child, "grace") is not None:
                continue
            dur_text = _child_text(child, "duration")
            if dur_text:
                try:
                    total += float(dur_text)
                except ValueError:
                    continue
        elif name == "backup":
            dur_text = _child_text(child, "duration")
            if dur_text:
                try:
                    total -= float(dur_text)
                except ValueError:
                    continue
        elif name == "forward":
            dur_text = _child_text(child, "duration")
            if dur_text:
                try:
                    total += float(dur_text)
                except ValueError:
                    continue
    return total


def _append_rest(measure: ET.Element, duration: int) -> None:
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest")
    dur = ET.SubElement(note, "duration")
    dur.text = str(duration)
    type_el = ET.SubElement(note, "type")
    type_el.text = "whole" if duration >= 8 else "quarter"


def repair_measure_durations(
    path: Path,
    *,
    output_path: Optional[Path] = None,
    fill_underfull: bool = True,
    tolerance: float = 0.51,
) -> RhythmRepairReport:
    """Flag overfull bars; optionally append a rest to underfull bars."""

    musicxml_path = Path(path)
    out = Path(output_path) if output_path else musicxml_path
    report = RhythmRepairReport(path=str(musicxml_path))
    try:
        tree = ET.parse(str(musicxml_path))
        root = tree.getroot()
    except (ET.ParseError, OSError) as exc:
        report.actions.append(f"parse_failed: {exc}")
        return report

    for part in [el for el in root if _local_name(el.tag) == "part"]:
        part_id = part.get("id") or ""
        divisions = 1
        beats = 4
        beat_type = 4
        for measure in _findall_local(part, "measure"):
            attrs = _find_local(measure, "attributes")
            if attrs is not None:
                div_text = _child_text(attrs, "divisions")
                if div_text:
                    try:
                        divisions = int(div_text)
                    except ValueError:
                        pass
                time_el = _find_local(attrs, "time")
                if time_el is not None:
                    beats_text = _child_text(time_el, "beats")
                    beat_type_text = _child_text(time_el, "beat-type")
                    try:
                        if beats_text:
                            beats = int(beats_text)
                        if beat_type_text:
                            beat_type = int(beat_type_text)
                    except ValueError:
                        pass
            expected = _duration_unit(beats, beat_type, divisions)
            actual = _measure_duration(measure)
            number = measure.get("number") or "?"
            delta = actual - expected
            if delta > tolerance:
                report.flags.append(
                    MeasureFlag(
                        part_id=part_id,
                        measure_number=number,
                        kind="overfull_measure",
                        message=(
                            f"Part {part_id} measure {number} is overfull "
                            f"({actual:.1f} vs {expected:.1f})"
                        ),
                        expected=expected,
                        actual=actual,
                    )
                )
            elif delta < -tolerance:
                report.flags.append(
                    MeasureFlag(
                        part_id=part_id,
                        measure_number=number,
                        kind="underfull_measure",
                        message=(
                            f"Part {part_id} measure {number} is underfull "
                            f"({actual:.1f} vs {expected:.1f})"
                        ),
                        expected=expected,
                        actual=actual,
                    )
                )
                if fill_underfull:
                    fill = int(round(expected - actual))
                    if fill > 0:
                        _append_rest(measure, fill)
                        report.rests_appended += 1
                        report.changed = True
                        report.actions.append(
                            f"fill_rest:{part_id}:{number}:{fill}"
                        )

    if report.changed:
        out.parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(out), encoding="utf-8", xml_declaration=True)
    if not report.actions and not report.flags:
        report.actions.append("noop_rhythms_ok")
    return report
