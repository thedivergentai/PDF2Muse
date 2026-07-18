import json
import subprocess
import zipfile
from pathlib import Path

from pdf2muse.evaluation import load_manifest
from scripts.musescore_com_benchmark import (
    MuseScoreComSample,
    collect_musescore_com_benchmark,
    download_pdf_with_librescore,
    load_score_urls,
    normalize_sample_sources,
    sample_id_for_url,
    write_evaluation_manifest,
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


def test_load_score_urls_ignores_comments_and_applies_limit(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "\n".join(
            [
                "# public-domain candidates",
                "https://musescore.com/user/1/scores/111",
                "",
                "https://musescore.com/user/2/scores/222",
            ]
        ),
        encoding="utf-8",
    )

    assert load_score_urls(urls, limit=1) == ["https://musescore.com/user/1/scores/111"]


def test_sample_id_for_url_uses_score_id_when_available():
    assert sample_id_for_url("https://musescore.com/user/123/scores/456789") == "musescore-456789"


def test_download_pdf_with_librescore_marks_blocked_on_failure(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="Cloudflare blocked request")

    monkeypatch.setattr("scripts.musescore_com_benchmark.subprocess.run", fake_run)

    result = download_pdf_with_librescore("https://musescore.com/user/1/scores/111", tmp_path)

    assert result.status == "pdf_blocked"
    assert "Cloudflare" in result.message


def test_download_pdf_with_librescore_records_pdf_path(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        (tmp_path / "Downloaded Score.pdf").write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("scripts.musescore_com_benchmark.subprocess.run", fake_run)

    result = download_pdf_with_librescore("https://musescore.com/user/1/scores/111", tmp_path)

    assert result.status == "pdf_downloaded"
    assert result.pdf_path == tmp_path / "Downloaded Score.pdf"


def test_normalize_sample_sources_extracts_mxl_and_keeps_mscx(tmp_path):
    mxl = tmp_path / "source.mxl"
    with zipfile.ZipFile(mxl, "w") as archive:
        archive.writestr("score.musicxml", VALID_MUSICXML)
    (tmp_path / "source.mscx").write_text("<museScore></museScore>", encoding="utf-8")
    (tmp_path / "input.pdf").write_bytes(b"%PDF-1.4")

    sample = normalize_sample_sources(tmp_path)

    assert sample.status == "complete"
    assert sample.musicxml_path == tmp_path / "ground_truth.musicxml"
    assert sample.mscx_path == tmp_path / "source.mscx"


def test_write_evaluation_manifest_only_includes_complete_samples(tmp_path):
    complete_dir = tmp_path / "complete"
    blocked_dir = tmp_path / "blocked"
    complete_dir.mkdir()
    blocked_dir.mkdir()
    pdf = complete_dir / "input.pdf"
    truth = complete_dir / "ground_truth.musicxml"
    mscx = complete_dir / "source.mscx"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    mscx.write_text("<museScore></museScore>", encoding="utf-8")
    samples = [
        MuseScoreComSample(
            sample_id="musescore-1",
            url="https://musescore.com/user/1/scores/1",
            sample_dir=complete_dir,
            status="complete",
            pdf_path=pdf,
            musicxml_path=truth,
            mscx_path=mscx,
        ),
        MuseScoreComSample(
            sample_id="musescore-2",
            url="https://musescore.com/user/2/scores/2",
            sample_dir=blocked_dir,
            status="pdf_blocked",
            message="blocked",
        ),
    ]
    manifest = tmp_path / "manifest.json"

    write_evaluation_manifest(samples, manifest)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert [item["id"] for item in data["samples"]] == ["musescore-1"]
    assert data["samples"][0]["metadata"]["source_mscx"].endswith("source.mscx")
    assert data["samples"][0]["input_quality"]["trusted_for_accuracy"] is True
    assert data["samples"][0]["input_quality"]["renderer"] == "musescore-com-download"
    loaded = load_manifest(manifest)[0]
    assert loaded.sample_id == "musescore-1"
    assert loaded.trusted_for_accuracy is True


def test_collect_musescore_com_benchmark_writes_resumable_status(tmp_path, monkeypatch):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://musescore.com/user/1/scores/111\n", encoding="utf-8")

    def fake_download(url, sample_dir):
        (sample_dir / "input.pdf").write_bytes(b"%PDF-1.4")
        return MuseScoreComSample(
            sample_id=sample_id_for_url(url),
            url=url,
            sample_dir=sample_dir,
            status="pdf_downloaded",
            pdf_path=sample_dir / "input.pdf",
        )

    monkeypatch.setattr("scripts.musescore_com_benchmark.download_pdf_with_librescore", fake_download)
    monkeypatch.setattr("scripts.musescore_com_benchmark.normalize_sample_sources", lambda sample_dir, **_: MuseScoreComSample(
        sample_id="musescore-111",
        url="https://musescore.com/user/1/scores/111",
        sample_dir=sample_dir,
        status="complete",
        pdf_path=sample_dir / "input.pdf",
        musicxml_path=sample_dir / "ground_truth.musicxml",
        mscx_path=sample_dir / "source.mscx",
    ))
    (tmp_path / "musescore-111").mkdir()
    (tmp_path / "musescore-111" / "ground_truth.musicxml").write_text(VALID_MUSICXML, encoding="utf-8")
    (tmp_path / "musescore-111" / "source.mscx").write_text("<museScore></museScore>", encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    samples = collect_musescore_com_benchmark(
        urls_file=urls,
        output_dir=tmp_path,
        manifest_path=manifest,
        limit=1,
        allow_unofficial_downloader=True,
    )

    status = json.loads((tmp_path / "collection_status.json").read_text(encoding="utf-8"))
    assert samples[0].status == "complete"
    assert status["samples"][0]["id"] == "musescore-111"
    assert manifest.exists()


def test_collect_musescore_com_benchmark_can_use_interactive_browser(tmp_path, monkeypatch):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://musescore.com/user/1/scores/111\n", encoding="utf-8")
    calls = []

    def fake_browser_downloads(**kwargs):
        calls.append(kwargs)
        sample_dir = kwargs["output_dir"] / "musescore-111"
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "input.pdf").write_bytes(b"%PDF-1.4")
        (sample_dir / "ground_truth.musicxml").write_text(VALID_MUSICXML, encoding="utf-8")
        (sample_dir / "source.mscx").write_text("<museScore></museScore>", encoding="utf-8")
        return []

    monkeypatch.setattr("scripts.musescore_com_benchmark.collect_browser_downloads", fake_browser_downloads)
    monkeypatch.setattr("scripts.musescore_com_benchmark.find_musescore_executable", lambda **_: None)

    samples = collect_musescore_com_benchmark(
        urls_file=urls,
        output_dir=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        limit=1,
        interactive_browser_downloads=True,
        browser_user_data_dir=tmp_path / "profile",
        browser_wait_seconds=90,
    )

    assert calls[0]["user_data_dir"] == tmp_path / "profile"
    assert calls[0]["wait_seconds"] == 90
    assert samples[0].status == "complete"
