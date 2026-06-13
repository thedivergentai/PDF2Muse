"""Tests for the CPU-only oemer wrapper."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_oemer_cpu_wrapper_forces_cpu_provider(monkeypatch):
    from pdf2muse import _oemer_cpu

    session_calls = []

    def fake_session(*args, **kwargs):
        session_calls.append((args, kwargs))
        return object()

    fake_ort = SimpleNamespace(InferenceSession=fake_session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    def fake_run_module(*args, **kwargs):
        fake_ort.InferenceSession("model.onnx")

    run_module = MagicMock(side_effect=fake_run_module)
    monkeypatch.setattr(_oemer_cpu.runpy, "run_module", run_module)

    _oemer_cpu.main(["page_000.png"])

    run_module.assert_called_once_with("oemer.ete", run_name="__main__")
    assert session_calls[0][1]["providers"] == ["CPUExecutionProvider"]


def test_oemer_cpu_wrapper_preserves_explicit_providers(monkeypatch):
    from pdf2muse import _oemer_cpu

    session_calls = []

    def fake_session(*args, **kwargs):
        session_calls.append((args, kwargs))
        return object()

    fake_ort = SimpleNamespace(InferenceSession=fake_session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    def fake_run_module(*args, **kwargs):
        fake_ort.InferenceSession("model.onnx", providers=["CustomExecutionProvider"])

    monkeypatch.setattr(_oemer_cpu.runpy, "run_module", fake_run_module)

    _oemer_cpu.main(["page_000.png"])

    assert session_calls[0][1]["providers"] == ["CustomExecutionProvider"]
