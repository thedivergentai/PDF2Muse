from pathlib import Path

from pdf2muse.rhythm_repair import repair_measure_durations

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "musicxml"

OVERFULL = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def test_underfull_measure_appends_rest(tmp_path: Path):
    path = tmp_path / "under.musicxml"
    path.write_text(
        (FIXTURES / "underfull-bar.musicxml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    report = repair_measure_durations(path)
    assert report.rests_appended == 1
    assert any(flag.kind == "underfull_measure" for flag in report.flags)
    assert "<rest" in path.read_text(encoding="utf-8")


def test_overfull_measure_flags_without_deleting_notes(tmp_path: Path):
    path = tmp_path / "over.musicxml"
    path.write_text(OVERFULL, encoding="utf-8")
    report = repair_measure_durations(path)
    assert report.changed is False
    assert any(flag.kind == "overfull_measure" for flag in report.flags)
    assert path.read_text(encoding="utf-8").count("<note>") == 1
