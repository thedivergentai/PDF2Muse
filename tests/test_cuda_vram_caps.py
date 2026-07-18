"""Tests for CUDA VRAM caps and inference tiling overrides."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pdf2muse._oemer_common import (
    _configured_batch_size,
    _configured_step_size,
    _patch_oemer_inference_tiling,
)
from pdf2muse._oemer_cuda import _configured_ort_gpu_mem_limit_bytes, _cuda_provider_options


def test_ort_gpu_mem_limit_default_is_4gib_per_session(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_ORT_GPU_MEM_LIMIT_MB", raising=False)
    assert _configured_ort_gpu_mem_limit_bytes() == 4096 * 1024 * 1024
    opts = _cuda_provider_options()
    assert opts["gpu_mem_limit"] == 4096 * 1024 * 1024
    assert opts["arena_extend_strategy"] == "kSameAsRequested"
    assert opts["cudnn_conv_algo_search"] == "HEURISTIC"


def test_ort_gpu_mem_limit_env_override(monkeypatch):
    monkeypatch.setenv("PDF2MUSE_ORT_GPU_MEM_LIMIT_MB", "2048")
    assert _configured_ort_gpu_mem_limit_bytes() == 2048 * 1024 * 1024
    assert _cuda_provider_options()["gpu_mem_limit"] == 2048 * 1024 * 1024


def test_tiling_defaults_and_env(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_OEMER_STEP_SIZE", raising=False)
    monkeypatch.delenv("PDF2MUSE_OEMER_BATCH_SIZE", raising=False)
    monkeypatch.setenv("PDF2MUSE_OEMER_QUALITY_PROFILE", "balanced")
    assert _configured_step_size() == 192
    assert _configured_batch_size() == 8
    monkeypatch.setenv("PDF2MUSE_OEMER_QUALITY_PROFILE", "quality")
    assert _configured_step_size() == 128
    assert _configured_batch_size() == 16
    monkeypatch.setenv("PDF2MUSE_OEMER_STEP_SIZE", "256")
    monkeypatch.setenv("PDF2MUSE_OEMER_BATCH_SIZE", "8")
    assert _configured_step_size() == 256
    assert _configured_batch_size() == 8


def test_inference_tiling_patch_overrides_defaults(monkeypatch):
    monkeypatch.setenv("PDF2MUSE_OEMER_STEP_SIZE", "200")
    monkeypatch.setenv("PDF2MUSE_OEMER_BATCH_SIZE", "10")
    import pdf2muse._oemer_common as common
    import oemer.inference as inference_mod

    monkeypatch.setattr(common, "_TILING_PATCHED", False)
    captured = {}
    original = inference_mod.inference

    def fake_inference(model_path, img_path, step_size=128, batch_size=16, manual_th=None, use_tf=False):
        captured["step_size"] = step_size
        captured["batch_size"] = batch_size
        return ("ok", "ok")

    monkeypatch.setattr(inference_mod, "inference", fake_inference)
    try:
        common._patch_oemer_inference_tiling()
        inference_mod.inference("m", "i")
        assert captured["step_size"] == 200
        assert captured["batch_size"] == 10
    finally:
        monkeypatch.setattr(inference_mod, "inference", original)
        common._TILING_PATCHED = False


@patch("pdf2muse.adapters.oemer.shutdown_all_oemer_workers")
@patch("pdf2muse.adapters.oemer.get_oemer_worker")
def test_worker_fallback_shuts_down_before_subprocess(
    mock_get_worker, mock_shutdown, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    monkeypatch.setenv("PDF2MUSE_OEMER_WORKER", "1")
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    worker = MagicMock()
    worker.run_page.side_effect = RuntimeError("worker crashed")
    mock_get_worker.return_value = worker

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{mock_image.stem}.musicxml").write_text(mock_xml_content, encoding="utf-8")
        return MagicMock(stdout="ok", stderr="")

    with patch("pdf2muse.adapters.oemer.subprocess.run", side_effect=side_effect) as mock_run:
        from pdf2muse.core import PDF2MusePipeline

        pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), oemer_device="cpu")
        xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert err is None
    assert xml_path is not None
    mock_shutdown.assert_called()
    assert mock_run.called
