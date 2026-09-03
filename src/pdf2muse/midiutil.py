"""MIDI pitch helpers shared by MusicXML post-processors."""

from __future__ import annotations

_STEP_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi_from_step(step: str, octave: int, alter: int = 0) -> int:
    """Convert MusicXML step/octave/alter to MIDI note number."""

    try:
        pc = _STEP_TO_PC[step.strip().upper()]
    except KeyError as exc:
        raise KeyError(f"Unknown pitch step: {step!r}") from exc
    return (int(octave) + 1) * 12 + pc + int(alter)
