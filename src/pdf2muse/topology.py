"""Post-OMR MusicXML topology repairs for multi-staff / multi-part scores.

Detects piano-like G+F part pairs and merges them into a grand-staff part, and
aligns simultaneous multi-part timelines that were serialized sequentially.
This does not improve note recognition quality; it repairs export topology.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _findall_local(parent: ET.Element, name: str) -> list[ET.Element]:
    return [el for el in parent if _local_name(el.tag) == name]


def _find_local(parent: ET.Element, name: str) -> Optional[ET.Element]:
    for el in parent:
        if _local_name(el.tag) == name:
            return el
    return None


def _child_text(element: ET.Element, child_name: str) -> Optional[str]:
    child = _find_local(element, child_name)
    return child.text.strip() if child is not None and child.text else None


@dataclass(frozen=True)
class PartClefProfile:
    part_id: str
    measure_count: int
    note_count: int
    primary_clef: Optional[str]  # "G", "F", "C", or None
    mean_midi: Optional[float]


@dataclass
class TopologyRepairReport:
    path: str
    changed: bool = False
    actions: list[str] = field(default_factory=list)
    predicted_parts_before: int = 0
    predicted_parts_after: int = 0


def _note_midi(note_el: ET.Element) -> Optional[int]:
    pitch_el = _find_local(note_el, "pitch")
    if pitch_el is None:
        return None
    step = _child_text(pitch_el, "step")
    octave = _child_text(pitch_el, "octave")
    alter = _child_text(pitch_el, "alter")
    if not step or octave is None:
        return None
    try:
        from .midiutil import midi_from_step

        alter_i = int(float(alter)) if alter else 0
        return midi_from_step(step, int(octave), alter_i)
    except (KeyError, ValueError):
        return None


def _primary_clef(part: ET.Element) -> Optional[str]:
    for measure in _findall_local(part, "measure"):
        attrs = _find_local(measure, "attributes")
        if attrs is None:
            continue
        for clef in _findall_local(attrs, "clef"):
            sign = _child_text(clef, "sign")
            if sign in {"G", "F", "C"}:
                return sign
    return None


def _profile_part(part: ET.Element) -> PartClefProfile:
    part_id = part.get("id") or ""
    measures = _findall_local(part, "measure")
    midis: list[int] = []
    notes = 0
    for measure in measures:
        for note_el in _findall_local(measure, "note"):
            notes += 1
            midi = _note_midi(note_el)
            if midi is not None:
                midis.append(midi)
    return PartClefProfile(
        part_id=part_id,
        measure_count=len(measures),
        note_count=notes,
        primary_clef=_primary_clef(part),
        mean_midi=(sum(midis) / len(midis)) if midis else None,
    )


def looks_like_piano_hands(a: PartClefProfile, b: PartClefProfile) -> bool:
    """Heuristic: G then F (or high then low register) with similar measure counts."""

    if a.measure_count == 0 or b.measure_count == 0:
        return False
    measure_ratio = min(a.measure_count, b.measure_count) / max(a.measure_count, b.measure_count)
    if measure_ratio < 0.7:
        return False

    clef_pair = {a.primary_clef, b.primary_clef}
    if clef_pair == {"G", "F"}:
        return True
    if a.mean_midi is not None and b.mean_midi is not None:
        # Distinct registers often indicate RH/LH even when clef tags are missing.
        if abs(a.mean_midi - b.mean_midi) >= 8 and measure_ratio >= 0.85:
            return True
    return False


def _ensure_staff_on_notes(measure: ET.Element, staff_number: int) -> None:
    for note_el in _findall_local(measure, "note"):
        staff = _find_local(note_el, "staff")
        if staff is None:
            staff = ET.SubElement(note_el, "staff")
            staff.text = str(staff_number)
        else:
            staff.text = str(staff_number)


def _set_clef_staff(measure: ET.Element, staff_number: int) -> None:
    attrs = _find_local(measure, "attributes")
    if attrs is None:
        return
    for clef in _findall_local(attrs, "clef"):
        clef.set("number", str(staff_number))
    staves = _find_local(attrs, "staves")
    if staves is None:
        staves = ET.Element("staves")
        # Insert near front of attributes
        attrs.insert(0, staves)
    staves.text = "2"


def merge_parts_to_grand_staff(
    root: ET.Element,
    upper_id: str,
    lower_id: str,
) -> bool:
    """Merge two part elements into one grand-staff part (staff 1/2)."""

    parts = {
        (p.get("id") or ""): p
        for p in root
        if _local_name(p.tag) == "part"
    }
    if upper_id not in parts or lower_id not in parts:
        return False

    upper = parts[upper_id]
    lower = parts[lower_id]
    upper_measures = _findall_local(upper, "measure")
    lower_measures = {
        m.get("number"): m for m in _findall_local(lower, "measure")
    }

    for um in upper_measures:
        num = um.get("number")
        _ensure_staff_on_notes(um, 1)
        _set_clef_staff(um, 1)
        lm = lower_measures.get(num)
        if lm is None:
            continue
        # Append lower-staff notes into the upper measure for simultaneous playback.
        for child in list(lm):
            name = _local_name(child.tag)
            if name == "note":
                cloned = deepcopy(child)
                staff = _find_local(cloned, "staff")
                if staff is None:
                    staff = ET.SubElement(cloned, "staff")
                staff.text = "2"
                um.append(cloned)
            elif name == "attributes":
                # Copy clef for staff 2 if present.
                for clef in _findall_local(child, "clef"):
                    attrs = _find_local(um, "attributes")
                    if attrs is None:
                        attrs = ET.Element("attributes")
                        um.insert(0, attrs)
                    cloned_clef = deepcopy(clef)
                    cloned_clef.set("number", "2")
                    attrs.append(cloned_clef)
                    staves = _find_local(attrs, "staves")
                    if staves is None:
                        staves = ET.Element("staves")
                        attrs.insert(0, staves)
                    staves.text = "2"

    # Update part-list: keep upper score-part, drop lower.
    part_list = _find_local(root, "part-list")
    if part_list is not None:
        for sp in list(part_list):
            if _local_name(sp.tag) == "score-part" and sp.get("id") == lower_id:
                part_list.remove(sp)
        # Prefer a piano-ish name on the kept part.
        for sp in _findall_local(part_list, "score-part"):
            if sp.get("id") == upper_id:
                name_el = _find_local(sp, "part-name")
                if name_el is not None and (not name_el.text or name_el.text.strip() in {"", "Part"}):
                    name_el.text = "Piano"
                break

    root.remove(lower)
    return True


def _parts_look_sequential(profiles: list[PartClefProfile]) -> bool:
    """True when multiple parts exist but look like concatenated timelines."""

    if len(profiles) < 2:
        return False
    # If measure counts are similar, prefer simultaneous (grand staff / SATB).
    counts = [p.measure_count for p in profiles if p.measure_count > 0]
    if not counts:
        return False
    return min(counts) / max(counts) >= 0.7


def ensure_grand_staff_metadata(root: ET.Element) -> list[str]:
    """Ensure single-part G+F scores declare staves=2 and piano-ish naming."""

    actions: list[str] = []
    parts = [el for el in root if _local_name(el.tag) == "part"]
    if len(parts) != 1:
        return actions
    part = parts[0]
    staff_nums: set[str] = set()
    for el in part.iter():
        if _local_name(el.tag) == "staff" and el.text:
            staff_nums.add(el.text.strip())
    if not ({"1", "2"} <= staff_nums):
        return actions

    for measure in _findall_local(part, "measure"):
        attrs = _find_local(measure, "attributes")
        if attrs is None:
            continue
        staves = _find_local(attrs, "staves")
        if staves is None:
            staves = ET.Element("staves")
            attrs.insert(0, staves)
            staves.text = "2"
            actions.append("inserted_staves_2")
        elif (staves.text or "").strip() != "2":
            staves.text = "2"
            actions.append("set_staves_2")
        break

    part_list = _find_local(root, "part-list")
    if part_list is not None:
        for sp in _findall_local(part_list, "score-part"):
            name_el = _find_local(sp, "part-name")
            if name_el is not None and (not name_el.text or name_el.text.strip() in {"", "Part", "Music"}):
                name_el.text = "Piano"
                actions.append("named_piano")
            break
    return actions


def expand_grand_staff_to_two_parts(root: ET.Element) -> bool:
    """Split staff 1/2 of a single part into two simultaneous parts (eval aid)."""

    parts = [el for el in root if _local_name(el.tag) == "part"]
    if len(parts) != 1:
        return False
    source = parts[0]
    source_id = source.get("id") or "P1"
    lower_id = "P2" if source_id != "P2" else "P2b"

    lower = ET.Element("part", {"id": lower_id})
    for measure in _findall_local(source, "measure"):
        new_m = ET.Element("measure", {"number": measure.get("number", "1")})
        # Copy attributes; keep staff-2 clefs.
        attrs = _find_local(measure, "attributes")
        if attrs is not None:
            new_attrs = deepcopy(attrs)
            for clef in list(_findall_local(new_attrs, "clef")):
                num = clef.get("number")
                if num == "1":
                    new_attrs.remove(clef)
                else:
                    clef.set("number", "1")
            staves = _find_local(new_attrs, "staves")
            if staves is not None:
                new_attrs.remove(staves)
            new_m.append(new_attrs)
        for note_el in _findall_local(measure, "note"):
            staff = _find_local(note_el, "staff")
            staff_n = (staff.text or "1").strip() if staff is not None else "1"
            if staff_n != "2":
                continue
            cloned = deepcopy(note_el)
            st = _find_local(cloned, "staff")
            if st is not None:
                cloned.remove(st)
            new_m.append(cloned)
        lower.append(new_m)

        # Strip staff-2 notes from source measure.
        for note_el in list(_findall_local(measure, "note")):
            staff = _find_local(note_el, "staff")
            if staff is not None and (staff.text or "").strip() == "2":
                measure.remove(note_el)
        # Drop staff-2 clefs / staves from source.
        attrs = _find_local(measure, "attributes")
        if attrs is not None:
            for clef in list(_findall_local(attrs, "clef")):
                if clef.get("number") == "2":
                    attrs.remove(clef)
            staves = _find_local(attrs, "staves")
            if staves is not None:
                attrs.remove(staves)
            for note_el in _findall_local(measure, "note"):
                st = _find_local(note_el, "staff")
                if st is not None:
                    note_el.remove(st)

    part_list = _find_local(root, "part-list")
    if part_list is not None:
        sp = ET.Element("score-part", {"id": lower_id})
        pn = ET.SubElement(sp, "part-name")
        pn.text = "Piano LH"
        part_list.append(sp)
        for existing in _findall_local(part_list, "score-part"):
            if existing.get("id") == source_id:
                name_el = _find_local(existing, "part-name")
                if name_el is not None:
                    name_el.text = "Piano RH"
    root.append(lower)
    return True


def apply_layout_staff_hint(root: ET.Element, staff_count: int) -> list[str]:
    """When layout saw piano systems, declare staves on a single-part score."""

    actions: list[str] = []
    if staff_count < 2:
        return actions
    parts = [el for el in root if _local_name(el.tag) == "part"]
    if len(parts) != 1:
        return actions
    part = parts[0]
    for measure in _findall_local(part, "measure"):
        attrs = _find_local(measure, "attributes")
        if attrs is None:
            attrs = ET.Element("attributes")
            measure.insert(0, attrs)
        staves = _find_local(attrs, "staves")
        if staves is None:
            staves = ET.Element("staves")
            attrs.insert(0, staves)
            actions.append(f"layout_hint_staves_{staff_count}")
        staves.text = str(staff_count)
        break
    return actions


def repair_musicxml_topology(
    path: Path,
    *,
    output_path: Optional[Path] = None,
    expand_for_eval: bool = False,
    layout_staff_count: Optional[int] = None,
) -> TopologyRepairReport:
    """Apply grand-staff / simultaneous-part heuristics to one MusicXML file."""

    musicxml_path = Path(path)
    out = Path(output_path) if output_path else musicxml_path
    report = TopologyRepairReport(path=str(musicxml_path))

    try:
        tree = ET.parse(str(musicxml_path))
        root = tree.getroot()
    except (ET.ParseError, OSError) as exc:
        report.actions.append(f"parse_failed: {exc}")
        return report

    part_els = [el for el in root if _local_name(el.tag) == "part"]
    report.predicted_parts_before = len(part_els)
    if len(part_els) == 0:
        report.predicted_parts_after = 0
        report.actions.append("noop_no_parts")
        return report

    if len(part_els) == 1:
        if layout_staff_count:
            hint_actions = apply_layout_staff_hint(root, layout_staff_count)
            if hint_actions:
                report.actions.extend(hint_actions)
                report.changed = True
        meta_actions = ensure_grand_staff_metadata(root)
        if meta_actions:
            report.actions.extend(meta_actions)
            report.changed = True
        if expand_for_eval and expand_grand_staff_to_two_parts(root):
            report.actions.append("expand_grand_staff_to_two_parts")
            report.changed = True
        if report.changed:
            out.parent.mkdir(parents=True, exist_ok=True)
            tree.write(str(out), encoding="utf-8", xml_declaration=True)
        report.predicted_parts_after = len(
            [el for el in root if _local_name(el.tag) == "part"]
        )
        if not report.actions:
            report.actions.append("noop_single_part")
        return report

    profiles = [_profile_part(p) for p in part_els]
    # Try pairwise G+F merges (first matching pair).
    merged = False
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            a, b = profiles[i], profiles[j]
            if not looks_like_piano_hands(a, b):
                continue
            # Upper = G / higher mean MIDI.
            if a.primary_clef == "G" or (
                a.mean_midi is not None
                and b.mean_midi is not None
                and a.mean_midi >= b.mean_midi
            ):
                upper_id, lower_id = a.part_id, b.part_id
            else:
                upper_id, lower_id = b.part_id, a.part_id
            if merge_parts_to_grand_staff(root, upper_id, lower_id):
                report.actions.append(f"grand_staff_merge:{upper_id}+{lower_id}")
                report.changed = True
                merged = True
                break
        if merged:
            break

    if not merged and _parts_look_sequential(profiles):
        report.actions.append("simultaneous_parts_assumed")
        part_list = _find_local(root, "part-list")
        if part_list is not None and len(profiles) >= 2:
            report.actions.append("kept_separate_simultaneous_parts")
            report.changed = True

    if report.changed:
        out.parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(out), encoding="utf-8", xml_declaration=True)

    report.predicted_parts_after = len([el for el in root if _local_name(el.tag) == "part"])
    return report
