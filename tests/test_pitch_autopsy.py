"""Unit tests for pitch-error autopsy classification."""

from __future__ import annotations

from pdf2muse.pitch_autopsy import (
    classify_musicdiff_text,
    classify_note_pair,
    summarize_autopsies,
    autopsy_sample,
)


def test_classify_staff_off_by_one():
    assert classify_note_pair("C4", "D4") == "staff_off_by_one"


def test_classify_accidental():
    assert classify_note_pair("C4", "C#4") == "accidental"
    assert classify_note_pair("E4", "Eb4") == "accidental"


def test_classify_clef_context_octave():
    assert classify_note_pair("C4", "C5") == "clef_context"


def test_classify_duration_beam():
    assert classify_note_pair("C4", "C4", aspect="flagsbeams") == "duration_beam"
    assert classify_note_pair("C4", "C4", duration_changed=True) == "duration_beam"


def test_classify_musicdiff_paired_notes():
    text = """
@@ measure 1, staff 1, beat 1.0 @@
-(Note) C4 (quarter note)
+(Note) D4 (quarter note)
@@ measure 1, staff 1, beat 2.0 @@
-(Note:flagsbeams) E4 (eighth note), 1 flag
+(Note:flagsbeams) E4 (eighth note), 1 beam
"""
    counts = classify_musicdiff_text(text)
    assert counts.staff_off_by_one == 1
    assert counts.duration_beam == 1


def test_autopsy_part_mismatch_boost():
    sample = autopsy_sample(
        sample_id="x",
        musicdiff_text="",
        predicted_parts=1,
        gt_parts=2,
    )
    assert sample.counts.part_mismatch > 0
    assert sample.dominant_subclass == "part_mismatch"


def test_summarize_attribution_gate():
    samples = [
        autopsy_sample(
            sample_id="a",
            musicdiff_text="-(Note) C4 (quarter note)\n+(Note) D4 (quarter note)\n",
        ),
        autopsy_sample(
            sample_id="b",
            musicdiff_text="-(Note) E4 (quarter note)\n+(Note) F4 (quarter note)\n",
        ),
    ]
    summary = summarize_autopsies(samples)
    assert summary["samples"] == 2
    assert summary["attribution_rate"] >= 0.7
    assert summary["success_gate_70pct"] is True
