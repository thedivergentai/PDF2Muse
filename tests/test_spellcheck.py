"""Tests for symbolic MusicXML spellcheck prototype."""

from __future__ import annotations

from pathlib import Path

from pdf2muse.spellcheck import (
    build_synthetic_training_pairs,
    corrupt_musicxml_text,
    flag_implausible_melodic_jumps,
    spellcheck_musicxml,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "musicxml"
_MINI = (FIXTURES / "leap.musicxml").read_text(encoding="utf-8")


def test_corrupt_introduces_edits():
    corrupted, edits = corrupt_musicxml_text(_MINI, rate=1.0, seed=1)
    assert edits
    assert corrupted != _MINI


def test_flag_melodic_leap():
    flags = flag_implausible_melodic_jumps(_MINI, max_leap_semitones=16)
    assert flags
    assert flags[0].kind == "melodic_leap"


def test_spellcheck_writes_json(tmp_path: Path):
    path = tmp_path / "draft.musicxml"
    path.write_text(_MINI, encoding="utf-8")
    result = spellcheck_musicxml(path)
    assert result.flags
    assert path.with_suffix(".spellcheck.json").exists()


def test_build_synthetic_pairs(tmp_path: Path):
    gt = tmp_path / "gt.musicxml"
    gt.write_text(_MINI, encoding="utf-8")
    out = tmp_path / "pairs"
    manifest = build_synthetic_training_pairs([gt], out, rate=1.0)
    assert manifest["pairs"]
    assert Path(manifest["pairs"][0]["corrupt"]).exists()
