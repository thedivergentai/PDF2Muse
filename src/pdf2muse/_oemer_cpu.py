"""Run oemer with ONNX Runtime pinned to CPU execution."""

import functools
import runpy
import sys
from typing import Optional

_CPU_PROVIDERS = ["CPUExecutionProvider"]


def _patch_onnxruntime_cpu_provider() -> None:
    """Force implicit ONNX Runtime sessions to use CPU inside this process."""
    import onnxruntime as ort

    original_session = ort.InferenceSession

    @functools.wraps(original_session)
    def cpu_session(*args, **kwargs):
        if "providers" not in kwargs and len(args) < 3:
            kwargs["providers"] = list(_CPU_PROVIDERS)
        return original_session(*args, **kwargs)

    ort.InferenceSession = cpu_session


def main(argv: Optional[list[str]] = None) -> None:
    """Run oemer.ete after forcing implicit ONNX Runtime sessions to CPU."""
    args = list(sys.argv[1:] if argv is None else argv)
    _patch_onnxruntime_cpu_provider()

    previous_argv = sys.argv[:]
    sys.argv = ["oemer.ete", *args]
    try:
        runpy.run_module("oemer.ete", run_name="__main__")
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    main()
