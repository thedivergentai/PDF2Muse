"""Tests for post-OMR grand-staff topology repair."""

from __future__ import annotations

from pathlib import Path

from pdf2muse.topology import (
    looks_like_piano_hands,
    PartClefProfile,
    repair_musicxml_topology,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "musicxml"


def test_looks_like_piano_hands_g_f():
    a = PartClefProfile("P1", 4, 10, "G", 72.0)
    b = PartClefProfile("P2", 4, 10, "F", 48.0)
    assert looks_like_piano_hands(a, b)


def test_repair_merges_grand_staff(tmp_path: Path):
    path = tmp_path / "piano.musicxml"
    path.write_text((FIXTURES / "sequential-piano.musicxml").read_text(encoding="utf-8"), encoding="utf-8")
    report = repair_musicxml_topology(path)
    assert report.changed
    assert report.predicted_parts_before == 2
    assert report.predicted_parts_after == 1
    assert any(a.startswith("grand_staff_merge:") for a in report.actions)
    text = path.read_text(encoding="utf-8")
    assert "<staves>2</staves>" in text or 'number="2"' in text
    assert 'id="P2"' not in text or text.count("<part ") == 1


_SINGLE_GRAND = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Part</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <clef number="1"><sign>G</sign><line>2</line></clef>
        <clef number="2"><sign>F</sign><line>4</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>5</octave></pitch>
        <duration>1</duration><type>quarter</type>
        <staff>1</staff>
      </note>
      <note>
        <pitch><step>C</step><octave>3</octave></pitch>
        <duration>1</duration><type>quarter</type>
        <staff>2</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_ensure_grand_staff_metadata(tmp_path: Path):
    path = tmp_path / "single.musicxml"
    path.write_text(_SINGLE_GRAND, encoding="utf-8")
    report = repair_musicxml_topology(path)
    assert report.changed
    text = path.read_text(encoding="utf-8")
    assert "<staves>2</staves>" in text
    assert "Piano" in text


def test_expand_grand_staff_for_eval(tmp_path: Path):
    path = tmp_path / "single.musicxml"
    path.write_text(_SINGLE_GRAND, encoding="utf-8")
    report = repair_musicxml_topology(path, expand_for_eval=True)
    assert report.predicted_parts_after == 2
    assert "expand_grand_staff_to_two_parts" in report.actions


_SINGLE_NO_STAVES = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def test_layout_staff_hint_declares_two_staves(tmp_path: Path):
    path = tmp_path / "hint.musicxml"
    path.write_text(_SINGLE_NO_STAVES, encoding="utf-8")
    report = repair_musicxml_topology(path, layout_staff_count=2)
    assert report.changed
    assert any("layout_hint_staves_2" in action for action in report.actions)
    assert "<staves>2</staves>" in path.read_text(encoding="utf-8")
