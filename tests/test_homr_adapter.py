"""Tests for the optional HOMR OMR adapter (mocked; no live model download)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf2muse.adapters import HomrAdapter, create_adapter, resolve_auto_backend
from pdf2muse.adapters.base import OmrOptions
from pdf2muse.oemer_utils import get_model_backend_config, list_model_backend_configs


MINIMAL_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_create_homr_adapter():
    backend = get_model_backend_config("homr")
    adapter = create_adapter(backend)
    assert isinstance(adapter, HomrAdapter)
    assert backend.kind == "homr"


def test_model_backend_lists_homr():
    names = [config.name for config in list_model_backend_configs()]
    assert "homr" in names


def test_homr_healthcheck_unavailable_when_import_fails(monkeypatch):
    adapter = HomrAdapter()

    def fake_run(cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        if "import homr" in joined:
            raise subprocess.CalledProcessError(1, cmd, stderr="No module named 'homr'")
        if "sys.version_info" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="3.12\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    status = adapter.healthcheck()
    assert status.available is False
    assert "pdf2muse[homr]" in status.message


def test_homr_healthcheck_unavailable_on_old_python(monkeypatch):
    adapter = HomrAdapter()

    def fake_run(cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        if "sys.version_info" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="3.10\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    status = adapter.healthcheck()
    assert status.available is False
    assert "3.11" in status.message


def test_homr_recognize_page_success(tmp_path, monkeypatch):
    adapter = HomrAdapter()
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(
        HomrAdapter,
        "healthcheck",
        lambda self: type(
            "S",
            (),
            {"available": True, "message": "ok", "name": "homr", "requires_gpu": False},
        )(),
    )

    def fake_run(cmd, **kwargs):
        work_image = Path(cmd[2])
        produced = work_image.with_suffix(".musicxml")
        produced.write_text(MINIMAL_MUSICXML, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout=str(produced) + "\n", stderr="")

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    result = adapter.recognize_page(image, output_dir, OmrOptions(timeout_seconds=30))
    assert result.musicxml_path is not None
    assert result.musicxml_path.exists()
    assert result.failure_class is None
    assert result.backend == "homr"


def test_homr_recognize_page_timeout(tmp_path, monkeypatch):
    adapter = HomrAdapter()
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(
        HomrAdapter,
        "healthcheck",
        lambda self: type(
            "S",
            (),
            {"available": True, "message": "ok", "name": "homr", "requires_gpu": False},
        )(),
    )

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    result = adapter.recognize_page(image, output_dir, OmrOptions(timeout_seconds=5))
    assert result.musicxml_path is None
    assert result.failure_class == "timeout"


def test_homr_recognize_page_invalid_musicxml(tmp_path, monkeypatch):
    adapter = HomrAdapter()
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(
        HomrAdapter,
        "healthcheck",
        lambda self: type(
            "S",
            (),
            {"available": True, "message": "ok", "name": "homr", "requires_gpu": False},
        )(),
    )

    def fake_run(cmd, **kwargs):
        work_image = Path(cmd[2])
        produced = work_image.with_suffix(".musicxml")
        produced.write_text("<not-musicxml/>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout=str(produced) + "\n", stderr="")

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    result = adapter.recognize_page(image, output_dir, OmrOptions())
    assert result.failure_class == "invalid_musicxml"


def test_homr_unavailable_when_healthcheck_fails(tmp_path, monkeypatch):
    adapter = HomrAdapter()
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        HomrAdapter,
        "healthcheck",
        lambda self: type(
            "S",
            (),
            {
                "available": False,
                "message": "missing",
                "name": "homr",
                "requires_gpu": False,
            },
        )(),
    )
    result = adapter.recognize_page(image, tmp_path, OmrOptions())
    assert result.failure_class == "homr_unavailable"


def test_resolve_auto_stays_oemer_without_homr_opt_in(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_ALLOW_LEGATO_AUTO", raising=False)
    monkeypatch.delenv("PDF2MUSE_ALLOW_HOMR_AUTO", raising=False)
    assert resolve_auto_backend() == "oemer-stock"


def test_resolve_auto_can_select_homr_with_opt_in(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_ALLOW_LEGATO_AUTO", raising=False)
    monkeypatch.setenv("PDF2MUSE_ALLOW_HOMR_AUTO", "1")
    monkeypatch.setattr(
        "pdf2muse.adapters.registry.HomrAdapter.healthcheck",
        lambda self: type("S", (), {"available": True})(),
    )
    assert resolve_auto_backend() == "homr"


def test_pipeline_homr_skips_oemer_checkpoints(tmp_path, monkeypatch):
    from pdf2muse.core import PDF2MusePipeline

    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    ensure = MagicMock()
    monkeypatch.setattr("pdf2muse.core.ensure_checkpoints", ensure)
    monkeypatch.setattr(
        "pdf2muse.core.create_adapter",
        lambda *args, **kwargs: MagicMock(
            recognize_page=MagicMock(
                return_value=MagicMock(musicxml_path=None, error="skip", attempts=[])
            )
        ),
    )
    monkeypatch.setattr(
        PDF2MusePipeline,
        "pdf_to_png",
        lambda self, output_dir: [],
    )

    pipeline = PDF2MusePipeline(
        pdf_path=str(pdf),
        output_dir=str(tmp_path / "out"),
        model_backend="homr",
    )
    # Empty page list will fail later; we only care that checkpoints were skipped.
    with pytest.raises(Exception):
        pipeline.run()
    ensure.assert_not_called()


def test_homr_wrapper_omits_no_title_by_default(tmp_path, monkeypatch):
    adapter = HomrAdapter()
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    captured = {}

    monkeypatch.setattr(
        HomrAdapter,
        "healthcheck",
        lambda self: type(
            "S",
            (),
            {"available": True, "message": "ok", "name": "homr", "requires_gpu": False},
        )(),
    )

    def fake_run(cmd, **kwargs):
        captured["cmd"] = [str(c) for c in cmd]
        work_image = Path(cmd[2])
        produced = work_image.with_suffix(".musicxml")
        produced.write_text(MINIMAL_MUSICXML, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout=str(produced) + "\n", stderr="")

    monkeypatch.setattr("pdf2muse.adapters.homr.subprocess.run", fake_run)
    adapter.recognize_page(image, output_dir, OmrOptions(save_cache=True, timeout_seconds=30))
    assert "--no-title" not in captured["cmd"]
    assert "--cache" in captured["cmd"]


def test_cli_help_mentions_homr():
    from typer.testing import CliRunner

    from pdf2muse.cli import app

    result = CliRunner().invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    # Color forced on GitHub Actions inserts ANSI resets inside "--…" tokens.
    plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", result.stdout)
    assert "homr" in plain
