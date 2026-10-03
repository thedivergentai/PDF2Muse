"""Platform ONNX Runtime wheel selection for source installs."""

from pdf2muse.install_runtime import resolve_onnxruntime_requirement


def test_darwin_never_requests_gpu_wheel():
    assert resolve_onnxruntime_requirement("darwin", nvidia_smi=True) == "onnxruntime"
    assert resolve_onnxruntime_requirement("darwin", nvidia_smi=False) == "onnxruntime"


def test_linux_without_nvidia_uses_cpu_runtime():
    assert resolve_onnxruntime_requirement("linux", nvidia_smi=False) == "onnxruntime"


def test_windows_with_nvidia_uses_gpu_runtime():
    assert resolve_onnxruntime_requirement("win32", nvidia_smi=True) == "onnxruntime-gpu"


def test_install_plan_pins_oemer_without_deps():
    from pdf2muse.install_runtime import build_install_plan

    plan = build_install_plan(platform_name="darwin", nvidia_smi=True, extras=("ui",))
    assert any(step[0] == "oemer --no-deps" for step in plan)
    wheels = [step[1][0] for step in plan if step[0] == "onnxruntime"]
    assert wheels == ["onnxruntime"]
    assert not any("onnxruntime-gpu" in " ".join(step[1]) for step in plan)
