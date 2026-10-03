"""Classify pitch/rhythm OMR disagreements into actionable subclasses."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .midiutil import midi_from_step

SUBCLASSES = (
    "staff_off_by_one",
    "accidental",
    "clef_context",
    "duration_beam",
    "insert_delete",
    "part_mismatch",
    "other",
)

_NOTE_RE = re.compile(
    r"^(?P<op>[+-])\(Note(?::(?P<aspect>[^)]+))?\)\s+"
    r"(?P<head>[A-G][#b]?\d+)\s+\((?P<dur>[^)]+)\)(?P<rest>.*)$",
    re.MULTILINE,
)
_REST_RE = re.compile(r"^[+-]\(Rest\)", re.MULTILINE)
_PART_HINT = re.compile(r"part|staff|PartStaff|Piano", re.IGNORECASE)
_PITCH_TOKEN = re.compile(r"^([A-G])([#b]?)(\d+)$")


@dataclass
class SubclassCounts:
    staff_off_by_one: int = 0
    accidental: int = 0
    clef_context: int = 0
    duration_beam: int = 0
    insert_delete: int = 0
    part_mismatch: int = 0
    other: int = 0

    def total(self) -> int:
        return sum(asdict(self).values())

    def dominant(self) -> str:
        items = asdict(self)
        if not any(items.values()):
            return "other"
        return max(items, key=items.get)


@dataclass
class PitchAutopsySample:
    sample_id: str
    omr_ned: Optional[float]
    predicted_parts: Optional[int]
    gt_parts: Optional[int]
    counts: SubclassCounts = field(default_factory=SubclassCounts)
    dominant_subclass: str = "other"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "omr_ned": self.omr_ned,
            "predicted_parts": self.predicted_parts,
            "gt_parts": self.gt_parts,
            "counts": asdict(self.counts),
            "dominant_subclass": self.dominant_subclass,
            "notes": self.notes,
        }


def _parse_pitch_token(token: str) -> Optional[tuple[str, int, int, int]]:
    """Return (step, alter, octave, midi) for tokens like C4, C#4, Eb4."""

    match = _PITCH_TOKEN.match((token or "").strip())
    if not match:
        return None
    step, accidental, octave_s = match.group(1), match.group(2), match.group(3)
    alter = 1 if accidental == "#" else (-1 if accidental == "b" else 0)
    try:
        octave = int(octave_s)
        midi = midi_from_step(step, octave, alter)
    except (KeyError, ValueError):
        return None
    return step, alter, octave, midi


def classify_note_pair(
    pred_head: str,
    gt_head: str,
    *,
    aspect: str = "",
    duration_changed: bool = False,
) -> str:
    """Map one predicted/GT note disagreement to a subclass label."""

    aspect_l = (aspect or "").lower()
    if "flagsbeams" in aspect_l or "beams" in aspect_l or "stem" in aspect_l:
        if not duration_changed:
            return "duration_beam"
    if duration_changed and pred_head == gt_head:
        return "duration_beam"

    pred = _parse_pitch_token(pred_head)
    gt = _parse_pitch_token(gt_head)
    if pred is None or gt is None:
        return "other"

    pred_step, pred_alter, pred_octave, pred_midi = pred
    gt_step, gt_alter, gt_octave, gt_midi = gt
    midi_delta = abs(pred_midi - gt_midi)
    if midi_delta == 0:
        if pred_step != gt_step or pred_alter != gt_alter:
            return "accidental"
        return "other"
    if midi_delta == 1:
        return "accidental"
    if midi_delta in (11, 12, 13):
        # Octave / clef-track style jumps are common when RH/LH assignment fails.
        return "clef_context"
    if midi_delta == 2 and pred_step == gt_step:
        return "accidental"
    # Staff position is roughly 2 MIDI per diatonic step near a staff.
    if midi_delta in (1, 2) or (2 <= midi_delta <= 3 and pred_octave == gt_octave):
        return "staff_off_by_one"
    if 4 <= midi_delta <= 7 and pred_octave == gt_octave:
        return "staff_off_by_one"
    if midi_delta >= 8:
        return "clef_context"
    return "other"


def _consume_note_ops(lines: list[str], start: int) -> tuple[list, list, int]:
    """Collect consecutive note ops until a non-note / measure header."""

    minus: list = []
    plus: list = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            break
        m = _NOTE_RE.match(line)
        if m:
            if m.group("op") == "-":
                minus.append(m)
            else:
                plus.append(m)
            i += 1
            continue
        if _REST_RE.match(line):
            # Treat rests as insert/delete markers outside pairing.
            i += 1
            continue
        if line.startswith("-") or line.startswith("+"):
            i += 1
            continue
        break
    return minus, plus, i


def classify_musicdiff_text(text: str) -> SubclassCounts:
    """Bucket note-level ops from musicdiff text output."""

    counts = SubclassCounts()
    if not text:
        return counts

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        if not (_NOTE_RE.match(lines[i]) or _REST_RE.match(lines[i])):
            if _REST_RE.match(lines[i]):
                counts.insert_delete += 1
            i += 1
            continue

        # Include a leading rest-only line as insert/delete.
        if _REST_RE.match(lines[i]) and not _NOTE_RE.match(lines[i]):
            counts.insert_delete += 1
            i += 1
            continue

        minus, plus, next_i = _consume_note_ops(lines, i)
        if next_i == i:
            i += 1
            continue
        i = next_i

        paired = min(len(minus), len(plus))
        for pred, gt in zip(minus[:paired], plus[:paired]):
            dur_changed = pred.group("dur") != gt.group("dur")
            aspect = pred.group("aspect") or gt.group("aspect") or ""
            label = classify_note_pair(
                pred.group("head"),
                gt.group("head"),
                aspect=aspect,
                duration_changed=dur_changed,
            )
            setattr(counts, label, getattr(counts, label) + 1)
        counts.insert_delete += abs(len(minus) - len(plus))

    return counts


def compare_pitch_streams(
    predicted: Path,
    ground_truth: Path,
    *,
    max_notes: int = 2000,
) -> SubclassCounts:
    """Fallback: align flattened note pitches when musicdiff text is thin."""

    counts = SubclassCounts()
    try:
        from music21 import converter, note
    except ImportError:
        return counts
    try:
        pred_score = converter.parse(str(predicted))
        gt_score = converter.parse(str(ground_truth))
    except Exception:
        return counts

    pred_notes = list(pred_score.flatten().notes)[:max_notes]
    gt_notes = list(gt_score.flatten().notes)[:max_notes]
    n = min(len(pred_notes), len(gt_notes))
    if abs(len(pred_notes) - len(gt_notes)) > max(4, n // 10):
        counts.insert_delete += abs(len(pred_notes) - len(gt_notes))

    for pn, gn in zip(pred_notes[:n], gt_notes[:n]):
        if not isinstance(pn, note.Note) or not isinstance(gn, note.Note):
            continue
        dur_changed = abs(float(pn.quarterLength) - float(gn.quarterLength)) > 1e-6
        label = classify_note_pair(
            pn.pitch.nameWithOctave,
            gn.pitch.nameWithOctave,
            duration_changed=dur_changed,
        )
        setattr(counts, label, getattr(counts, label) + 1)
    return counts


def autopsy_sample(
    *,
    sample_id: str,
    musicdiff_text: str = "",
    omr_ned: Optional[float] = None,
    predicted_parts: Optional[int] = None,
    gt_parts: Optional[int] = None,
    predicted_path: Optional[Path] = None,
    ground_truth_path: Optional[Path] = None,
) -> PitchAutopsySample:
    """Build a per-sample pitch autopsy record."""

    counts = classify_musicdiff_text(musicdiff_text)
    notes: list[str] = []
    if predicted_path and ground_truth_path:
        if predicted_path.exists() and ground_truth_path.exists():
            from .musicxml import analyze_musicxml_structure

            if predicted_parts is None:
                predicted_parts = analyze_musicxml_structure(predicted_path).parts
            if gt_parts is None:
                gt_parts = analyze_musicxml_structure(ground_truth_path).parts
            # Prefer stream pitch labels when musicdiff is mostly insert/delete noise.
            stream_counts = compare_pitch_streams(predicted_path, ground_truth_path)
            pitchy = (
                stream_counts.staff_off_by_one
                + stream_counts.accidental
                + stream_counts.clef_context
            )
            if pitchy > 0 and (
                counts.total() < 5
                or counts.insert_delete > (counts.total() * 0.6)
                or pitchy >= (
                    counts.staff_off_by_one + counts.accidental + counts.clef_context
                )
            ):
                # Merge: keep duration_beam/part from text, replace pitch subclasses.
                merged = SubclassCounts(
                    staff_off_by_one=stream_counts.staff_off_by_one,
                    accidental=stream_counts.accidental,
                    clef_context=stream_counts.clef_context,
                    duration_beam=max(counts.duration_beam, stream_counts.duration_beam),
                    insert_delete=max(counts.insert_delete, stream_counts.insert_delete),
                    part_mismatch=counts.part_mismatch,
                    other=stream_counts.other,
                )
                counts = merged
                notes.append("merged_music21_pitch_stream")

    if (
        predicted_parts is not None
        and gt_parts is not None
        and predicted_parts > 0
        and gt_parts > 0
        and predicted_parts != gt_parts
    ):
        counts.part_mismatch += max(1, abs(gt_parts - predicted_parts) * 3)
        notes.append("part_count_mismatch")

    dominant = counts.dominant()
    return PitchAutopsySample(
        sample_id=sample_id,
        omr_ned=omr_ned,
        predicted_parts=predicted_parts,
        gt_parts=gt_parts,
        counts=counts,
        dominant_subclass=dominant,
        notes=notes,
    )


def summarize_autopsies(samples: list[PitchAutopsySample]) -> dict[str, Any]:
    """Aggregate subclass totals and attribution rate."""

    totals = Counter()
    dominant = Counter()
    attributed = 0
    for sample in samples:
        totals.update(asdict(sample.counts))
        dominant[sample.dominant_subclass] += 1
        if sample.dominant_subclass != "other" and sample.counts.total() > 0:
            attributed += 1
    n = len(samples)
    return {
        "samples": n,
        "attributed_samples": attributed,
        "attribution_rate": (attributed / n) if n else 0.0,
        "subclass_totals": dict(totals),
        "dominant_distribution": dict(dominant),
        "success_gate_70pct": (attributed / n) >= 0.70 if n else False,
    }
