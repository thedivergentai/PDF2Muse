import json
import zipfile

import pytest

from pdf2muse.evaluation import load_manifest, parse_musicxml
from scripts.openscore_benchmark import (
    OpenScoreSample,
    create_openscore_benchmark,
    extract_musicxml_from_mxl,
)


VALID_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_extract_musicxml_from_mxl(tmp_path):
    mxl = tmp_path / "score.mxl"
    target = tmp_path / "truth.musicxml"
    with zipfile.ZipFile(mxl, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container>
  <rootfiles>
    <rootfile full-path="score.musicxml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr("wrong.xml", "<not-musicxml/>")
        archive.writestr("score.musicxml", VALID_MUSICXML)

    extract_musicxml_from_mxl(mxl, target)

    assert parse_musicxml(target).ok is True


def test_create_openscore_benchmark_writes_manifest(monkeypatch, tmp_path):
    source_mxl = tmp_path / "source.mxl"
    with zipfile.ZipFile(source_mxl, "w") as archive:
        archive.writestr("score.musicxml", VALID_MUSICXML)

    musescore = tmp_path / "MuseScore4.exe"
    musescore.write_text("", encoding="utf-8")

    def fake_download(url, target):
        target.write_bytes(source_mxl.read_bytes())

    def fake_render(mxl_path, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4\n% fake pdf\n")

    monkeypatch.setattr("scripts.openscore_benchmark.find_musescore_binary", lambda: musescore)
    monkeypatch.setattr("scripts.openscore_benchmark._download_file", fake_download)
    monkeypatch.setattr("scripts.openscore_benchmark._render_mxl_to_pdf", fake_render)

    manifest = tmp_path / "manifest.json"
    create_openscore_benchmark(
        output_dir=tmp_path / "openscore",
        manifest_path=manifest,
        samples=[
            OpenScoreSample(
                sample_id="openscore-test",
                title="OpenScore Test",
                mxl_url="https://example.test/score.mxl",
                source_path="scores/example/score.mscx",
                difficulty_tags=["clean-typeset", "cc0"],
            )
        ],
    )

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["samples"][0]["source"] == "OpenScore Lieder"
    assert data["samples"][0]["input_quality"]["trusted_for_accuracy"] is True
    assert "CC0-1.0" in data["samples"][0]["license_notes"]
    loaded = load_manifest(manifest)
    assert loaded[0].input_path.exists()
    assert loaded[0].ground_truth_path.exists()
    assert loaded[0].trusted_for_accuracy is True


def test_create_openscore_benchmark_requires_musescore(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.openscore_benchmark.find_musescore_binary", lambda: None)
    with pytest.raises(RuntimeError, match="MuseScore CLI is required"):
        create_openscore_benchmark(
            output_dir=tmp_path / "openscore",
            manifest_path=tmp_path / "manifest.json",
            samples=[],
        )
