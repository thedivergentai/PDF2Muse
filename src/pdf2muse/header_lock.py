"""Lock key, time, and tempo from a majority vote, then respell in that key."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .musicxml import _child_text, _findall_local, _find_local, _local_name
from .midiutil import midi_from_step


@dataclass
class HeaderLockReport:
    path: str
    changed: bool = False
    fifths: Optional[int] = None
    beats: Optional[int] = None
    beat_type: Optional[int] = None
    tempo: Optional[float] = None
    actions: list[str] = field(default_factory=list)
    notes_respelled: int = 0


def _iter_parts(root: ET.Element) -> list[ET.Element]:
    return [el for el in root if _local_name(el.tag) == "part"]


def _first_attributes(part: ET.Element) -> Optional[ET.Element]:
    for measure in _findall_local(part, "measure"):
        attrs = _find_local(measure, "attributes")
        if attrs is not None:
            return attrs
    return None


def _vote_key_time_tempo(root: ET.Element) -> tuple[Optional[int], Optional[int], Optional[int], Optional[float]]:
    fifths_votes: list[int] = []
    beat_votes: list[tuple[int, int]] = []
    tempo_votes: list[float] = []
    for part in _iter_parts(root):
        for measure in _findall_local(part, "measure")[:4]:
            attrs = _find_local(measure, "attributes")
            if attrs is not None:
                key_el = _find_local(attrs, "key")
                if key_el is not None:
                    fifths_text = _child_text(key_el, "fifths")
                    if fifths_text is not None:
                        try:
                            fifths_votes.append(int(fifths_text))
                        except ValueError:
                            pass
                time_el = _find_local(attrs, "time")
                if time_el is not None:
                    beats_text = _child_text(time_el, "beats")
                    beat_type_text = _child_text(time_el, "beat-type")
                    try:
                        if beats_text and beat_type_text:
                            beat_votes.append((int(beats_text), int(beat_type_text)))
                    except ValueError:
                        pass
            direction = _find_local(measure, "direction")
            if direction is not None:
                sound = None
                for el in direction.iter():
                    if _local_name(el.tag) == "sound" and el.get("tempo"):
                        sound = el
                        break
                    if _local_name(el.tag) == "per-minute" and el.text:
                        try:
                            tempo_votes.append(float(el.text.strip()))
                        except ValueError:
                            pass
                if sound is not None:
                    try:
                        tempo_votes.append(float(sound.get("tempo") or ""))
                    except ValueError:
                        pass
    fifths = Counter(fifths_votes).most_common(1)[0][0] if fifths_votes else None
    time_sig = Counter(beat_votes).most_common(1)[0][0] if beat_votes else None
    tempo = Counter(tempo_votes).most_common(1)[0][0] if tempo_votes else None
    beats = time_sig[0] if time_sig else None
    beat_type = time_sig[1] if time_sig else None
    return fifths, beats, beat_type, tempo


def _ensure_child(parent: ET.Element, tag: str) -> ET.Element:
    child = _find_local(parent, tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    return child


def _apply_attributes(
    root: ET.Element,
    *,
    fifths: Optional[int],
    beats: Optional[int],
    beat_type: Optional[int],
    tempo: Optional[float],
) -> list[str]:
    actions: list[str] = []
    for part in _iter_parts(root):
        measures = _findall_local(part, "measure")
        if not measures:
            continue
        first = measures[0]
        attrs = _find_local(first, "attributes")
        if attrs is None:
            attrs = ET.Element("attributes")
            first.insert(0, attrs)
        if fifths is not None:
            key_el = _ensure_child(attrs, "key")
            fifths_el = _ensure_child(key_el, "fifths")
            if (fifths_el.text or "").strip() != str(fifths):
                fifths_el.text = str(fifths)
                actions.append("lock_key")
        if beats is not None and beat_type is not None:
            time_el = _ensure_child(attrs, "time")
            beats_el = _ensure_child(time_el, "beats")
            beat_type_el = _ensure_child(time_el, "beat-type")
            if (beats_el.text or "").strip() != str(beats) or (
                beat_type_el.text or ""
            ).strip() != str(beat_type):
                beats_el.text = str(beats)
                beat_type_el.text = str(beat_type)
                actions.append("lock_time")
        if tempo is not None:
            sound = None
            for el in first.iter():
                if _local_name(el.tag) == "sound":
                    sound = el
                    break
            if sound is None:
                direction = ET.Element("direction")
                direction_type = ET.SubElement(direction, "direction-type")
                metronome = ET.SubElement(direction_type, "metronome")
                beat_unit = ET.SubElement(metronome, "beat-unit")
                beat_unit.text = "quarter"
                per_minute = ET.SubElement(metronome, "per-minute")
                per_minute.text = str(int(tempo))
                sound = ET.SubElement(direction, "sound")
                first.append(direction)
            sound.set("tempo", str(int(tempo) if tempo == int(tempo) else tempo))
            actions.append("lock_tempo")
        # Later measures: rewrite conflicting key/time.
        for measure in measures[1:]:
            attrs = _find_local(measure, "attributes")
            if attrs is None:
                continue
            if fifths is not None:
                key_el = _find_local(attrs, "key")
                if key_el is not None:
                    fifths_el = _ensure_child(key_el, "fifths")
                    fifths_el.text = str(fifths)
            if beats is not None and beat_type is not None:
                time_el = _find_local(attrs, "time")
                if time_el is not None:
                    _ensure_child(time_el, "beats").text = str(beats)
                    _ensure_child(time_el, "beat-type").text = str(beat_type)
    return list(dict.fromkeys(actions))


_PC_TO_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_PC_TO_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def spell_midi_in_key(midi: int, fifths: int) -> tuple[str, int, int]:
    """Return (step, alter, octave) for MIDI using key-signature accidentals."""

    pc = midi % 12
    octave = midi // 12 - 1
    prefer_flats = fifths < 0
    name = _PC_TO_FLAT[pc] if prefer_flats else _PC_TO_SHARP[pc]
    if fifths == 0:
        name = _PC_TO_SHARP[pc] if pc in {1, 3, 6, 8, 10} else _PC_TO_FLAT[pc]
        # C major: prefer naturals / common sharps for black keys as sharps.
        name = _PC_TO_SHARP[pc]
    step = name[0]
    alter = 0
    if name.endswith("bb"):
        alter = -2
    elif name.endswith("b"):
        alter = -1
    elif name.endswith("##"):
        alter = 2
    elif name.endswith("#"):
        alter = 1
    return step, alter, octave


def _respell_pitches(root: ET.Element, fifths: int) -> int:
    changed = 0
    for pitch_el in root.iter():
        if _local_name(pitch_el.tag) != "pitch":
            continue
        step_el = _find_local(pitch_el, "step")
        octave_el = _find_local(pitch_el, "octave")
        if step_el is None or octave_el is None or not step_el.text or not octave_el.text:
            continue
        alter_el = _find_local(pitch_el, "alter")
        try:
            alter = int(float(alter_el.text)) if alter_el is not None and alter_el.text else 0
            octave = int(octave_el.text)
        except ValueError:
            continue
        step = step_el.text.strip()
        try:
            midi = midi_from_step(step, int(octave), alter)
        except (KeyError, ValueError):
            continue
        new_step, new_alter, new_octave = spell_midi_in_key(midi, fifths)
        if (new_step, new_alter, new_octave) == (step, alter, octave):
            continue
        step_el.text = new_step
        octave_el.text = str(new_octave)
        if new_alter == 0:
            if alter_el is not None:
                pitch_el.remove(alter_el)
        else:
            if alter_el is None:
                alter_el = ET.Element("alter")
                # alter belongs after step
                pitch_el.insert(1, alter_el)
            alter_el.text = str(new_alter)
        changed += 1
    return changed


def lock_musicxml_header(path: Path, *, output_path: Optional[Path] = None) -> HeaderLockReport:
    """Majority-vote key/time/tempo on page-1 measures and rewrite the score."""

    musicxml_path = Path(path)
    out = Path(output_path) if output_path else musicxml_path
    report = HeaderLockReport(path=str(musicxml_path))
    try:
        tree = ET.parse(str(musicxml_path))
        root = tree.getroot()
    except (ET.ParseError, OSError) as exc:
        report.actions.append(f"parse_failed: {exc}")
        return report

    fifths, beats, beat_type, tempo = _vote_key_time_tempo(root)
    report.fifths = fifths
    report.beats = beats
    report.beat_type = beat_type
    report.tempo = tempo
    if fifths is None and beats is None and tempo is None:
        report.actions.append("noop_no_header")
        return report

    report.actions.extend(
        _apply_attributes(
            root, fifths=fifths, beats=beats, beat_type=beat_type, tempo=tempo
        )
    )
    if fifths is not None:
        report.notes_respelled = _respell_pitches(root, fifths)
        if report.notes_respelled:
            report.actions.append(f"respell:{report.notes_respelled}")
    if report.actions:
        report.changed = True
        out.parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(out), encoding="utf-8", xml_declaration=True)
    return report
