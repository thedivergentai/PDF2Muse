from pathlib import Path

from pdf2muse.header_lock import lock_musicxml_header, spell_midi_in_key

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "musicxml"


def test_spell_fs_as_gb_in_two_flats():
    step, alter, octave = spell_midi_in_key(66, -2)
    assert (step, alter, octave) == ("G", -1, 4)


def test_header_lock_votes_two_flats_and_respells(tmp_path: Path):
    path = tmp_path / "autumn.musicxml"
    path.write_text((FIXTURES / "wrong-key.musicxml").read_text(encoding="utf-8"), encoding="utf-8")
    report = lock_musicxml_header(path)
    assert report.fifths == -2
    assert report.beats == 4
    text = path.read_text(encoding="utf-8")
    assert "<fifths>-2</fifths>" in text
    assert "<fifths>2</fifths>" not in text
    assert "<step>G</step>" in text
    assert "<alter>-1</alter>" in text or "<alter>-1.0</alter>" in text
