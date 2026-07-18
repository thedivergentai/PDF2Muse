"""Run oemer with ONNX Runtime pinned to CUDA execution when available."""

from __future__ import annotations

import functools
import os
import runpy
import site
import sys
from pathlib import Path
from typing import Optional

from ._oemer_common import (
    _patch_oemer_checkpoint_dir,
    _patch_oemer_inference_diagnostics,
    _patch_oemer_inference_tiling,
    _patch_oemer_postprocessing_guards,
    _patch_oemer_resize_image,
)

_CUDA_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]
_DLL_DIRECTORY_HANDLES = []
_CUDA_DEPENDENCY_HELP = (
    "ONNX Runtime could not load the CUDA execution provider. "
    "Install CUDA/cuDNN runtime dependencies into the project venv with: "
    'venv\\Scripts\\python.exe -m pip install "onnxruntime-gpu[cuda,cudnn]"'
)


def _site_package_dirs() -> list[Path]:
    dirs = [Path(p) for p in site.getsitepackages()]
    user_site = site.getusersitepackages()
    if user_site:
        dirs.append(Path(user_site))
    return dirs


def _add_nvidia_dll_directories() -> None:
    """Expose NVIDIA wheel DLL folders to Windows and cuDNN sublibrary loaders."""

    dll_dirs: list[Path] = []
    for site_dir in _site_package_dirs():
        nvidia_dir = site_dir / "nvidia"
        for package in (
            "cublas",
            "cuda_nvrtc",
            "cuda_runtime",
            "cudnn",
            "cufft",
            "curand",
            "nvjitlink",
        ):
            bin_dir = nvidia_dir / package / "bin"
            if bin_dir.is_dir():
                dll_dirs.append(bin_dir)

    unique_dirs = []
    seen = set()
    for dll_dir in dll_dirs:
        key = str(dll_dir).lower()
        if key not in seen:
            seen.add(key)
            unique_dirs.append(dll_dir)

    for dll_dir in unique_dirs:
        if hasattr(os, "add_dll_directory"):
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(dll_dir)))

    if unique_dirs:
        existing_path = os.environ.get("PATH", "")
        prepend = os.pathsep.join(str(dll_dir) for dll_dir in unique_dirs)
        os.environ["PATH"] = f"{prepend}{os.pathsep}{existing_path}" if existing_path else prepend


def _preload_onnxruntime_cuda_dlls(ort) -> None:
    """Load CUDA/cuDNN/MSVC DLLs from PyTorch, NVIDIA wheels, or system paths."""

    _add_nvidia_dll_directories()
    preload = getattr(ort, "preload_dlls", None)
    if preload is None:
        return

    try:
        preload(cuda=True, cudnn=True, msvc=True, directory=None)
    except Exception as exc:
        raise RuntimeError(_CUDA_DEPENDENCY_HELP) from exc


def _configured_ort_gpu_mem_limit_bytes() -> int:
    """ORT CUDA arena cap per InferenceSession (default 4096 MiB).

    Warm worker may keep unet_big + seg_net resident (~2x this). Use
    PDF2MUSE_OEMER_SINGLE_MODEL_VRAM=1 to keep only one session at a time.
    """

    raw = os.environ.get("PDF2MUSE_ORT_GPU_MEM_LIMIT_MB", "4096")
    try:
        mb = int(raw)
    except ValueError:
        mb = 4096
    if mb <= 0:
        mb = 4096
    return mb * 1024 * 1024


def _cuda_provider_options() -> dict:
    """Prefer faster cuDNN search and cap greedy CUDA arena growth."""

    mem_limit = _configured_ort_gpu_mem_limit_bytes()
    return {
        "device_id": 0,
        "cudnn_conv_algo_search": "HEURISTIC",
        "do_copy_in_default_stream": "1",
        "gpu_mem_limit": mem_limit,
        "arena_extend_strategy": "kSameAsRequested",
    }


def _build_session_options(ort):
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Hybrid graphs still run some ConvTranspose nodes on CPU EP.
    cpu_workers = max(1, min(8, (os.cpu_count() or 4)))
    options.intra_op_num_threads = cpu_workers
    options.inter_op_num_threads = 2
    options.enable_mem_pattern = True
    options.enable_cpu_mem_arena = True
    # Errors only — suppress ConvTranspose "Falling back to CPU" spam.
    options.log_severity_level = 3
    return options


def _patch_onnxruntime_cuda_provider() -> None:
    """Force implicit ONNX Runtime sessions to use CUDA before CPU fallback."""

    import onnxruntime as ort

    # Quiet default logger before first session (UTF-16 interleaved spam on Windows).
    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
    try:
        ort.set_default_logger_severity(3)
    except Exception:
        pass

    _preload_onnxruntime_cuda_dlls(ort)
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" not in available:
        raise RuntimeError(
            "CUDAExecutionProvider is not available in this ONNX Runtime environment. "
            f"Available providers: {available}"
        )

    cuda_options = _cuda_provider_options()
    providers = [
        ("CUDAExecutionProvider", cuda_options),
        "CPUExecutionProvider",
    ]
    mem_mb = int(cuda_options["gpu_mem_limit"]) // (1024 * 1024)
    print(
        "PDF2MUSE_DIAG onnx_providers "
        f"available={available} selected=['CUDAExecutionProvider', 'CPUExecutionProvider'] "
        f"gpu_mem_limit_mb={mem_mb}_per_session "
        f"(~{mem_mb * 2}_mb if unet+seg both warm) "
        f"arena_extend_strategy={cuda_options['arena_extend_strategy']} "
        "(ConvTranspose asymmetric-pad nodes may still run on CPU EP by ORT design)",
        flush=True,
    )
    original_session = ort.InferenceSession

    @functools.wraps(original_session)
    def cuda_session(*args, **kwargs):
        args = list(args)
        if "sess_options" not in kwargs and (
            len(args) < 2 or args[1] is None
        ):
            kwargs["sess_options"] = _build_session_options(ort)
        if len(args) >= 3:
            args[2] = list(providers)
            kwargs.pop("providers", None)
        else:
            kwargs["providers"] = list(providers)
        try:
            return original_session(*args, **kwargs)
        except Exception as exc:
            raise RuntimeError(_CUDA_DEPENDENCY_HELP) from exc

    ort.InferenceSession = cuda_session


def main(argv: Optional[list[str]] = None) -> None:
    """Run oemer.ete after forcing implicit ONNX Runtime sessions to CUDA."""

    args = list(sys.argv[1:] if argv is None else argv)
    _patch_onnxruntime_cuda_provider()
    _patch_oemer_checkpoint_dir()
    _patch_oemer_resize_image()
    _patch_oemer_inference_tiling()
    _patch_oemer_postprocessing_guards()
    if os.environ.get("PDF2MUSE_OEMER_DIAGNOSTICS") == "1":
        _patch_oemer_inference_diagnostics()

    previous_argv = sys.argv[:]
    sys.argv = ["oemer.ete", *args]
    try:
        runpy.run_module("oemer.ete", run_name="__main__")
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    main()
