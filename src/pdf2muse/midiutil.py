"""MIDI helpers that do not require music21."""

from __future__ import annotations

STEP_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi_from_step(step: str, octave: int, alter: int = 0) -> int:
    """Return MIDI note number for a MusicXML step/octave/alter triple."""

    pc = STEP_PC[step.strip().upper()]
    return (int(octave) + 1) * 12 + pc + int(alter)
