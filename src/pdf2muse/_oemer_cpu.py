"""Run oemer with ONNX Runtime pinned to CPU execution."""

import functools
import os
import runpy
import sys
from typing import Optional

from ._oemer_common import (
    _MAX_OEMER_PIXELS,
    _patch_oemer_checkpoint_dir,
    _patch_oemer_inference_diagnostics,
    _patch_oemer_inference_tiling,
    _patch_oemer_postprocessing_guards,
    _patch_oemer_resize_image,
)

_CPU_PROVIDERS = ["CPUExecutionProvider"]


def _patch_onnxruntime_cpu_provider() -> None:
    """Force implicit ONNX Runtime sessions to use CPU inside this process."""
    import onnxruntime as ort

    original_session = ort.InferenceSession

    @functools.wraps(original_session)
    def cpu_session(*args, **kwargs):
        args = list(args)
        if len(args) >= 3:
            args[2] = list(_CPU_PROVIDERS)
            kwargs.pop("providers", None)
        else:
            kwargs["providers"] = list(_CPU_PROVIDERS)
        return original_session(*args, **kwargs)

    ort.InferenceSession = cpu_session


def main(argv: Optional[list[str]] = None) -> None:
    """Run oemer.ete after forcing implicit ONNX Runtime sessions to CPU."""
    args = list(sys.argv[1:] if argv is None else argv)
    _patch_onnxruntime_cpu_provider()
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
