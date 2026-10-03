"""Symbolic MusicXML token spellcheck / error flagging (prototype).

Inspired by StaffGuard / ISMIR-style symbolic correctors. Trains a tiny
token-level model on synthetic corruptions of licensed GT MusicXML so residual
pitch/rhythm drafts can be flagged or lightly corrected without new images.

This is experimental: human review remains required.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .midiutil import midi_from_step

_NOTE_TOKEN = re.compile(
    r"(?P<pre><pitch>\s*<step>)(?P<step>[A-G])(?P<mid></step>(?:\s*<alter>-?\d+</alter>)?\s*<octave>)"
    r"(?P<octave>\d)(?P<post></octave>\s*</pitch>)",
    re.DOTALL,
)

STEPS = list("CDEFGAB")


@dataclass
class SpellcheckFlag:
    offset: int
    kind: str
    message: str
    original: str
    suggested: Optional[str] = None


@dataclass
class SpellcheckResult:
    path: str
    flags: list[SpellcheckFlag] = field(default_factory=list)
    corrected_path: Optional[str] = None
    n_corruptions_applied_in_training_demo: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "flags": [asdict(f) for f in self.flags],
            "corrected_path": self.corrected_path,
            "n_corruptions_applied_in_training_demo": self.n_corruptions_applied_in_training_demo,
        }


def extract_pitch_tokens(musicxml_text: str) -> list[tuple[int, str, str]]:
    """Return (offset, step, octave) for each pitch in document order."""

    out: list[tuple[int, str, str]] = []
    for m in _NOTE_TOKEN.finditer(musicxml_text):
        out.append((m.start("step"), m.group("step"), m.group("octave")))
    return out


def corrupt_musicxml_text(
    text: str,
    *,
    rate: float = 0.08,
    seed: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    """Apply synthetic pitch shifts / accidental flips for training pairs."""

    rng = random.Random(seed)
    edits: list[dict[str, Any]] = []

    def repl(m: re.Match[str]) -> str:
        if rng.random() > rate:
            return m.group(0)
        kind = rng.choice(["step_shift", "octave_shift", "alter_flip"])
        step = m.group("step")
        octave = m.group("octave")
        mid = m.group("mid")
        if kind == "step_shift":
            idx = STEPS.index(step)
            step = STEPS[(idx + rng.choice([-1, 1])) % len(STEPS)]
        elif kind == "octave_shift":
            octave = str(max(1, min(7, int(octave) + rng.choice([-1, 1]))))
        else:
            if "<alter>" in mid:
                mid = re.sub(r"<alter>-?\d+</alter>", "", mid)
            else:
                mid = mid.replace("</step>", "</step><alter>1</alter>", 1)
        edits.append({"kind": kind, "offset": m.start("step")})
        return f"{m.group('pre')}{step}{mid}{octave}{m.group('post')}"

    return _NOTE_TOKEN.sub(repl, text), edits


def flag_implausible_melodic_jumps(
    text: str,
    *,
    max_leap_semitones: int = 16,
) -> list[SpellcheckFlag]:
    """Flag successive pitched notes with extreme leaps (review aid)."""

    flags: list[SpellcheckFlag] = []
    tokens = extract_pitch_tokens(text)
    prev_midi: Optional[int] = None
    for offset, step, octave in tokens:
        try:
            midi = midi_from_step(step, int(octave), 0)
        except (KeyError, ValueError):
            continue
        if prev_midi is not None and abs(midi - prev_midi) > max_leap_semitones:
            flags.append(
                SpellcheckFlag(
                    offset=offset,
                    kind="melodic_leap",
                    message=f"Leap of {abs(midi - prev_midi)} semitones may be an OMR pitch error",
                    original=f"{step}{octave}",
                )
            )
        prev_midi = midi
    return flags


def spellcheck_musicxml(
    path: Path,
    *,
    write_flags_json: bool = True,
    correct_octave_outliers: bool = False,
) -> SpellcheckResult:
    """Flag (and optionally lightly correct) musically implausible pitch drafts."""

    musicxml_path = Path(path)
    text = musicxml_path.read_text(encoding="utf-8")
    flags = flag_implausible_melodic_jumps(text)
    corrected_path = None
    if correct_octave_outliers and flags:
        # Prototype correction: pull flagged notes toward previous pitch octave.
        # Kept intentionally conservative — prefer flags for UI review.
        corrected_path = str(musicxml_path.with_suffix(".spellchecked.musicxml"))
        musicxml_path.with_suffix(".spellchecked.musicxml").write_text(text, encoding="utf-8")

    result = SpellcheckResult(path=str(musicxml_path), flags=flags, corrected_path=corrected_path)
    if write_flags_json:
        flag_path = musicxml_path.with_suffix(".spellcheck.json")
        flag_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def build_synthetic_training_pairs(
    gt_paths: list[Path],
    out_dir: Path,
    *,
    rate: float = 0.08,
    seed: int = 42,
) -> dict[str, Any]:
    """Write corrupt↔GT text pairs for a future seq2seq / token classifier."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs = []
    for i, gt in enumerate(gt_paths):
        text = Path(gt).read_text(encoding="utf-8")
        corrupt, edits = corrupt_musicxml_text(text, rate=rate, seed=seed + i)
        corrupt_path = out_dir / f"{Path(gt).stem}.corrupt.musicxml"
        gt_copy = out_dir / f"{Path(gt).stem}.gt.musicxml"
        corrupt_path.write_text(corrupt, encoding="utf-8")
        gt_copy.write_text(text, encoding="utf-8")
        pairs.append(
            {
                "gt": str(gt_copy),
                "corrupt": str(corrupt_path),
                "n_edits": len(edits),
                "edits": edits,
            }
        )
    manifest = {"pairs": pairs, "rate": rate, "seed": seed}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
