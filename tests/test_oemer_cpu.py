"""Tests for the CPU-only oemer wrapper."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_oemer_cpu_wrapper_forces_cpu_provider(monkeypatch):
    from pdf2muse import _oemer_cpu

    monkeypatch.setenv("PDF2MUSE_OEMER_COREML", "0")
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


def test_oemer_cpu_wrapper_overrides_explicit_providers(monkeypatch):
    from pdf2muse import _oemer_cpu

    monkeypatch.setenv("PDF2MUSE_OEMER_COREML", "0")
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

    assert session_calls[0][1]["providers"] == ["CPUExecutionProvider"]


def test_oemer_cpu_wrapper_overrides_positional_providers(monkeypatch):
    from pdf2muse import _oemer_cpu

    monkeypatch.setenv("PDF2MUSE_OEMER_COREML", "0")
    session_calls = []

    def fake_session(*args, **kwargs):
        session_calls.append((args, kwargs))
        return object()

    fake_ort = SimpleNamespace(InferenceSession=fake_session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    def fake_run_module(*args, **kwargs):
        fake_ort.InferenceSession(
            "model.onnx",
            None,
            ["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

    monkeypatch.setattr(_oemer_cpu.runpy, "run_module", fake_run_module)

    _oemer_cpu.main(["page_000.png"])

    assert session_calls[0][0][2] == ["CPUExecutionProvider"]


def test_oemer_cpu_wrapper_disables_small_image_upscaling(monkeypatch):
    from pdf2muse import _oemer_cpu

    class FakeImage:
        size = (800, 1000)

        def resize(self, size):
            raise AssertionError(f"small image should not be upscaled to {size}")

    fake_inference = SimpleNamespace()
    fake_oemer = SimpleNamespace(inference=fake_inference)
    monkeypatch.setitem(sys.modules, "oemer", fake_oemer)

    _oemer_cpu._patch_oemer_resize_image()

    assert fake_inference.resize_image(FakeImage()).size == (800, 1000)


def test_oemer_cpu_wrapper_downscales_large_images(monkeypatch):
    from pdf2muse import _oemer_cpu

    class FakeImage:
        size = (5000, 5000)

        def resize(self, size):
            return SimpleNamespace(size=size)

    fake_inference = SimpleNamespace()
    fake_oemer = SimpleNamespace(inference=fake_inference)
    monkeypatch.setitem(sys.modules, "oemer", fake_oemer)

    _oemer_cpu._patch_oemer_resize_image()

    resized = fake_inference.resize_image(FakeImage())
    assert resized.size[0] * resized.size[1] <= _oemer_cpu._MAX_OEMER_PIXELS + 5000


def test_oemer_cpu_wrapper_can_emit_inference_diagnostics(monkeypatch, capsys):
    from pdf2muse import _oemer_cpu

    def fake_inference(model_path, img_path, **kwargs):
        return "class-map", "raw-output"

    fake_inference_module = SimpleNamespace(inference=fake_inference)
    fake_oemer = SimpleNamespace(inference=fake_inference_module)
    monkeypatch.setitem(sys.modules, "oemer", fake_oemer)

    _oemer_cpu._patch_oemer_inference_diagnostics()
    result = fake_inference_module.inference("checkpoints/unet_big", "page.png")

    captured = capsys.readouterr()
    assert result == ("class-map", "raw-output")
    assert "PDF2MUSE_DIAG inference_start model=unet_big" in captured.out
    assert "PDF2MUSE_DIAG inference_done model=unet_big" in captured.out


def test_oemer_cuda_wrapper_forces_cuda_provider(monkeypatch):
    from pdf2muse import _oemer_cuda

    session_calls = []

    def fake_session(*args, **kwargs):
        session_calls.append((args, kwargs))
        return object()

    fake_ort = SimpleNamespace(
        InferenceSession=fake_session,
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
        SessionOptions=MagicMock,
        GraphOptimizationLevel=SimpleNamespace(ORT_ENABLE_ALL=99),
        set_default_logger_severity=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    def fake_run_module(*args, **kwargs):
        fake_ort.InferenceSession("model.onnx")

    run_module = MagicMock(side_effect=fake_run_module)
    monkeypatch.setattr(_oemer_cuda.runpy, "run_module", run_module)

    _oemer_cuda.main(["page_000.png"])

    run_module.assert_called_once_with("oemer.ete", run_name="__main__")
    providers = session_calls[0][1]["providers"]
    assert "CUDAExecutionProvider" in str(providers)
    assert "CPUExecutionProvider" in str(providers)


def test_oemer_cuda_wrapper_rejects_missing_cuda_provider(monkeypatch):
    from pdf2muse import _oemer_cuda

    fake_ort = SimpleNamespace(
        InferenceSession=MagicMock(),
        get_available_providers=lambda: ["CPUExecutionProvider"],
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    try:
        _oemer_cuda._patch_onnxruntime_cuda_provider()
    except RuntimeError as exc:
        assert "CUDAExecutionProvider is not available" in str(exc)
    else:
        raise AssertionError("Expected missing CUDA provider to raise")


def test_oemer_cpu_coreml_falls_back_to_cpu(monkeypatch):
    from pdf2muse import _oemer_cpu

    session_calls = []

    def fake_session(*args, **kwargs):
        providers = kwargs.get("providers") or (args[2] if len(args) >= 3 else None)
        session_calls.append(providers)
        if providers and providers[0] == "CoreMLExecutionProvider":
            raise RuntimeError("coreml unavailable")
        return object()

    fake_ort = SimpleNamespace(InferenceSession=fake_session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setattr(_oemer_cpu.sys, "platform", "darwin")
    monkeypatch.delenv("PDF2MUSE_OEMER_COREML", raising=False)

    def fake_run_module(*args, **kwargs):
        fake_ort.InferenceSession("model.onnx")

    monkeypatch.setattr(_oemer_cpu.runpy, "run_module", fake_run_module)
    _oemer_cpu.main(["page_000.png"])
    assert session_calls[0][0] == "CoreMLExecutionProvider"
    assert session_calls[1] == ["CPUExecutionProvider"]
