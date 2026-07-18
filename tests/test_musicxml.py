import xml.etree.ElementTree as ET

import pytest

from pdf2muse.musicxml import join_musicxml_files, validate_musicxml_file


def score_with_parts(parts: list[tuple[str, str, list[str]]]) -> str:
    part_list = "\n".join(
        f'    <score-part id="{part_id}"><part-name>{name}</part-name></score-part>'
        for part_id, name, _ in parts
    )
    part_bodies = []
    for part_id, _, measures in parts:
        measure_xml = "\n".join(
            f'    <measure number="{number}"><note><rest/><duration>1</duration></note></measure>'
            for number in measures
        )
        part_bodies.append(f'  <part id="{part_id}">\n{measure_xml}\n  </part>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<score-partwise version="3.1">\n'
        "  <part-list>\n"
        f"{part_list}\n"
        "  </part-list>\n"
        f"{chr(10).join(part_bodies)}\n"
        "</score-partwise>\n"
    )


def test_validate_musicxml_file_reports_parse_status(tmp_path):
    valid = tmp_path / "valid.musicxml"
    invalid = tmp_path / "invalid.musicxml"
    valid.write_text(score_with_parts([("P1", "Piano", ["1"])]), encoding="utf-8")
    invalid.write_text("<score-partwise>", encoding="utf-8")

    assert validate_musicxml_file(valid).ok is True
    invalid_result = validate_musicxml_file(invalid)
    assert invalid_result.ok is False
    assert "no element found" in invalid_result.error


def test_join_musicxml_files_matches_parts_by_id_and_renumbers_measures(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.musicxml").write_text(
        score_with_parts([("P1", "Violin", ["1"]), ("P2", "Cello", ["1"])]),
        encoding="utf-8",
    )
    (input_dir / "002.musicxml").write_text(
        score_with_parts([("P2", "Cello", ["1"]), ("P1", "Violin", ["1"])]),
        encoding="utf-8",
    )
    output = tmp_path / "combined.musicxml"

    report = join_musicxml_files(input_dir, output)

    assert report.files_joined == 2
    root = ET.parse(output).getroot()
    part_ids = [part.attrib["id"] for part in root.findall("part")]
    assert part_ids == ["P1", "P2"]
    for part in root.findall("part"):
        assert [measure.attrib["number"] for measure in part.findall("measure")] == ["1", "2"]


def test_join_musicxml_files_reports_and_skips_parse_errors(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.musicxml").write_text(
        score_with_parts([("P1", "Piano", ["1"])]),
        encoding="utf-8",
    )
    (input_dir / "002.musicxml").write_text("<score-partwise>", encoding="utf-8")
    output = tmp_path / "combined.musicxml"

    report = join_musicxml_files(input_dir, output)

    assert output.exists()
    assert report.files_joined == 1
    assert report.files_skipped == 1
    assert report.skipped_files[0].endswith("002.musicxml")


def test_join_musicxml_files_can_be_strict_about_parse_errors(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.musicxml").write_text(
        score_with_parts([("P1", "Piano", ["1"])]),
        encoding="utf-8",
    )
    (input_dir / "002.musicxml").write_text("<score-partwise>", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid MusicXML"):
        join_musicxml_files(input_dir, tmp_path / "combined.musicxml", strict=True)


def test_join_single_page_copies_without_music21(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    page = input_dir / "001.musicxml"
    page.write_text(score_with_parts([("P1", "Piano", ["1", "2"])]), encoding="utf-8")
    output = tmp_path / "combined.musicxml"

    def boom(*_args, **_kwargs):
        raise AssertionError("music21 join should be skipped for single page")

    monkeypatch.setenv("PDF2MUSE_JOIN_ENGINE", "music21")
    monkeypatch.setattr("pdf2muse.musicxml._join_with_music21", boom)

    report = join_musicxml_files(input_dir, output, strict=True)

    assert report.engine == "copy"
    assert report.files_joined == 1
    assert output.exists()
    assert validate_musicxml_file(output).ok


def test_join_falls_back_to_etree_when_music21_write_fails(tmp_path, monkeypatch):
    from pdf2muse.musicxml import MusicXmlGateError

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.musicxml").write_text(
        score_with_parts([("P1", "Piano", ["1"])]),
        encoding="utf-8",
    )
    (input_dir / "002.musicxml").write_text(
        score_with_parts([("P1", "Piano", ["1"])]),
        encoding="utf-8",
    )
    output = tmp_path / "combined.musicxml"

    def fail_write(files, output_path, *, strict):
        raise MusicXmlGateError("join_music21_write_failed: music21 write failed: boom")

    monkeypatch.setenv("PDF2MUSE_JOIN_ENGINE", "music21")
    monkeypatch.setattr("pdf2muse.musicxml._join_with_music21", fail_write)

    report = join_musicxml_files(input_dir, output, strict=True)

    assert report.engine == "etree"
    assert report.files_joined == 2
    assert output.exists()
    assert validate_musicxml_file(output).ok
    assert any("join_music21_write_failed" in w for w in report.warnings)


def test_join_empty_dir_raises_gate_error(tmp_path):
    from pdf2muse.musicxml import MusicXmlGateError

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(MusicXmlGateError, match="No MusicXML files found"):
        join_musicxml_files(empty, tmp_path / "out.musicxml")
