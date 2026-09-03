"""Tests for key/time/tempo header normalize (preserve vs lock)."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from pdf2muse.cli import app
from pdf2muse.header_lock import lock_musicxml_header, spell_midi_in_key

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "musicxml"
runner = CliRunner()


def _minimal_score(
    *,
    measures: list[str],
) -> str:
    body = "\n".join(measures)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
{body}
  </part>
</score-partwise>
"""


def test_spell_fs_as_gb_in_two_flats():
    step, alter, octave = spell_midi_in_key(66, -2)
    assert (step, alter, octave) == ("G", -1, 4)


def test_lock_mode_votes_two_flats_and_respells(tmp_path: Path):
    path = tmp_path / "autumn.musicxml"
    path.write_text((FIXTURES / "wrong-key.musicxml").read_text(encoding="utf-8"), encoding="utf-8")
    report = lock_musicxml_header(path, mode="lock")
    assert report.mode == "lock"
    assert report.fifths == -2
    assert report.beats == 4
    text = path.read_text(encoding="utf-8")
    assert "<fifths>-2</fifths>" in text
    assert "<fifths>2</fifths>" not in text
    assert "<step>G</step>" in text
    assert "<alter>-1</alter>" in text or "<alter>-1.0</alter>" in text


def test_preserve_keeps_mid_score_key_change(tmp_path: Path):
    path = tmp_path / "modulate.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>-2</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="2">
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="3">
      <note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="4">
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="5">
      <attributes>
        <key><fifths>2</fifths></key>
      </attributes>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    report = lock_musicxml_header(path, mode="preserve")
    assert report.mode == "preserve"
    text = path.read_text(encoding="utf-8")
    assert text.count("<fifths>-2</fifths>") == 1
    assert text.count("<fifths>2</fifths>") == 1


def test_preserve_keeps_time_signature_change(tmp_path: Path):
    path = tmp_path / "meter.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="2">
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="3">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="4">
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="5">
      <attributes>
        <time><beats>6</beats><beat-type>8</beat-type></time>
      </attributes>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>6</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    lock_musicxml_header(path, mode="preserve")
    text = path.read_text(encoding="utf-8")
    assert "<beats>4</beats>" in text
    assert "<beat-type>4</beat-type>" in text
    assert "<beats>6</beats>" in text
    assert "<beat-type>8</beat-type>" in text


def test_preserve_keeps_tempo_change(tmp_path: Path):
    path = tmp_path / "tempo.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction>
        <direction-type>
          <metronome>
            <beat-unit>quarter</beat-unit>
            <per-minute>120</per-minute>
          </metronome>
        </direction-type>
        <sound tempo="120"/>
      </direction>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="2">
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="3">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="4">
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="5">
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="6">
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="7">
      <note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="8">
      <direction>
        <direction-type>
          <metronome>
            <beat-unit>quarter</beat-unit>
            <per-minute>90</per-minute>
          </metronome>
        </direction-type>
        <sound tempo="90"/>
      </direction>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    lock_musicxml_header(path, mode="preserve")
    text = path.read_text(encoding="utf-8")
    assert 'tempo="120"' in text
    assert 'tempo="90"' in text
    assert "<per-minute>120</per-minute>" in text
    assert "<per-minute>90</per-minute>" in text


def test_preserve_respells_per_segment(tmp_path: Path):
    """F# (MIDI 66) becomes Gb under two flats; stays F# under two sharps."""
    path = tmp_path / "segments.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>-2</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>
        <duration>4</duration>
      </note>
    </measure>""",
                """    <measure number="2">
      <attributes>
        <key><fifths>2</fifths></key>
      </attributes>
      <note>
        <pitch><step>G</step><alter>-1</alter><octave>4</octave></pitch>
        <duration>4</duration>
      </note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    report = lock_musicxml_header(path, mode="preserve")
    assert report.notes_respelled >= 1
    text = path.read_text(encoding="utf-8")
    # Measure 1 (Bb/Eb / two flats): prefer Gb
    assert text.index("<fifths>-2</fifths>") < text.index("<step>G</step>")
    # Measure 2 (two sharps): prefer F#
    assert "<fifths>2</fifths>" in text
    assert "<step>F</step>" in text
    assert "<alter>1</alter>" in text or "<alter>1.0</alter>" in text


def test_preserve_noop_when_no_key(tmp_path: Path):
    path = tmp_path / "no-key.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns
    report = lock_musicxml_header(path, mode="preserve")
    assert report.mode == "preserve"
    assert report.changed is False or "noop" in " ".join(report.actions)
    assert path.read_text(encoding="utf-8") == before
    assert path.stat().st_mtime_ns == mtime_before or not report.changed


def test_lock_overwrites_later_key_change(tmp_path: Path):
    path = tmp_path / "lock-mod.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>-2</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="2">
      <attributes><key><fifths>-2</fifths></key></attributes>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="3">
      <attributes><key><fifths>-2</fifths></key></attributes>
      <note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="4">
      <attributes><key><fifths>-2</fifths></key></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="5">
      <attributes>
        <key><fifths>2</fifths></key>
      </attributes>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    report = lock_musicxml_header(path, mode="lock")
    assert report.fifths == -2
    text = path.read_text(encoding="utf-8")
    assert "<fifths>2</fifths>" not in text
    assert text.count("<fifths>-2</fifths>") >= 1


def test_default_mode_is_preserve(tmp_path: Path):
    path = tmp_path / "default.musicxml"
    path.write_text(
        _minimal_score(
            measures=[
                """    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>-2</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>""",
                """    <measure number="2">
      <attributes><key><fifths>2</fifths></key></attributes>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>""",
            ]
        ),
        encoding="utf-8",
    )
    report = lock_musicxml_header(path)
    assert report.mode == "preserve"
    text = path.read_text(encoding="utf-8")
    assert "<fifths>-2</fifths>" in text
    assert "<fifths>2</fifths>" in text


def test_cli_header_lock_flag_in_help():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "--header-lock" in result.stdout


@patch("pdf2muse.cli.PDF2MusePipeline")
def test_cli_header_lock_passes_lock_mode(mock_pipeline, tmp_path: Path):
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    mock_pipeline.return_value.run.return_value = tmp_path / "out.musicxml"
    result = runner.invoke(
        app,
        ["convert", str(pdf), "--output", str(tmp_path / "out"), "--header-lock"],
    )
    assert result.exit_code == 0
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs["header_lock_mode"] == "lock"


@patch("pdf2muse.cli.PDF2MusePipeline")
def test_cli_default_header_lock_mode_is_preserve(mock_pipeline, tmp_path: Path):
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    mock_pipeline.return_value.run.return_value = tmp_path / "out.musicxml"
    result = runner.invoke(
        app,
        ["convert", str(pdf), "--output", str(tmp_path / "out")],
    )
    assert result.exit_code == 0
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs["header_lock_mode"] == "preserve"
