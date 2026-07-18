"""Persistent oemer worker: load ORT sessions once, process many pages."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import runpy
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Optional, TextIO


RESULT_PREFIX = "PDF2MUSE_WORKER_RESULT "


class _Tee(io.TextIOBase):
    """Write to multiple text streams (capture + live mirror)."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def _apply_runtime_patches(device: str) -> None:
    from pdf2muse._oemer_common import (
        _patch_oemer_checkpoint_dir,
        _patch_oemer_inference_diagnostics,
        _patch_oemer_inference_tiling,
        _patch_oemer_postprocess_stage_timings,
        _patch_oemer_postprocessing_guards,
        _patch_oemer_resize_image,
        _patch_onnxruntime_session_cache,
    )

    if device == "cuda":
        from pdf2muse._oemer_cuda import _patch_onnxruntime_cuda_provider

        _patch_onnxruntime_cuda_provider()
    else:
        from pdf2muse._oemer_cpu import _patch_onnxruntime_cpu_provider

        _patch_onnxruntime_cpu_provider()

    _patch_onnxruntime_session_cache()
    _patch_oemer_checkpoint_dir()
    _patch_oemer_resize_image()
    _patch_oemer_inference_tiling()
    _patch_oemer_postprocessing_guards()
    _patch_oemer_inference_diagnostics()
    _patch_oemer_postprocess_stage_timings()


def _run_oemer_once(image_path: Path, *, deskew: bool, use_tf: bool, save_cache: bool) -> None:
    args = [str(image_path)]
    if not deskew:
        args.append("--without-deskew")
    if use_tf:
        args.append("--use-tf")
    if save_cache:
        args.append("--save-cache")

    previous_argv = sys.argv[:]
    sys.argv = ["oemer.ete", *args]
    try:
        runpy.run_module("oemer.ete", run_name="__main__")
    finally:
        sys.argv = previous_argv


def _handle_request(request: dict[str, Any], *, patched_device: Optional[str]) -> tuple[dict[str, Any], Optional[str]]:
    from pdf2muse._oemer_common import (
        format_stage_timings_line,
        get_stage_timings,
        reset_stage_timings,
    )

    device = str(request.get("device") or "cpu")
    image_path = Path(str(request["image_path"]))
    cwd = Path(str(request.get("cwd") or Path.cwd()))
    deskew = bool(request.get("deskew", True))
    use_tf = bool(request.get("use_tf", False))
    save_cache = bool(request.get("save_cache", False))
    env_updates = request.get("env") or {}

    if patched_device is None:
        _apply_runtime_patches(device)
        patched_device = device
    elif patched_device != device:
        return (
            {
                "ok": False,
                "returncode": 2,
                "stdout": "",
                "stderr": f"Worker device mismatch: started as {patched_device}, got {device}",
                "stages": {},
                "error": "device_mismatch",
            },
            patched_device,
        )

    previous_env = {key: os.environ.get(key) for key in env_updates}
    for key, value in env_updates.items():
        if value is None:
            os.environ.pop(str(key), None)
        else:
            os.environ[str(key)] = str(value)
    # Always enable diagnostics inside the worker for stage timings.
    os.environ["PDF2MUSE_OEMER_DIAGNOSTICS"] = "1"

    cwd.mkdir(parents=True, exist_ok=True)
    previous_cwd = Path.cwd()
    reset_stage_timings()
    page_start = time.perf_counter()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    # Mirror live output to real stderr so PDF2MUSE_OEMER_STREAM can tee.
    tee_out = _Tee(stdout_buf, sys.__stderr__)
    tee_err = _Tee(stderr_buf, sys.__stderr__)

    returncode = 0
    error: Optional[str] = None
    try:
        os.chdir(cwd)
        with contextlib.redirect_stdout(tee_out), contextlib.redirect_stderr(tee_err):
            _run_oemer_once(
                image_path,
                deskew=deskew,
                use_tf=use_tf,
                save_cache=save_cache,
            )
    except SystemExit as exc:
        code = exc.code
        returncode = int(code) if isinstance(code, int) else (0 if code is None else 1)
        if returncode != 0:
            error = f"oemer exited with code {returncode}"
    except Exception as exc:
        returncode = 1
        error = str(exc)
        traceback.print_exc(file=tee_err)
    finally:
        os.chdir(previous_cwd)
        for key, prior in previous_env.items():
            if prior is None:
                os.environ.pop(str(key), None)
            else:
                os.environ[str(key)] = prior

    stages = get_stage_timings()
    stages["total_page"] = time.perf_counter() - page_start
    inference_total = sum(
        value for key, value in stages.items() if key.startswith("inference_")
    )
    accounted = stages.get("session_load", 0.0) + inference_total + stages.get("dewarp", 0.0)
    residual = max(0.0, stages["total_page"] - accounted)
    if residual > 0.01:
        stages["postprocess_other"] = residual

    print(format_stage_timings_line(stages), file=sys.__stderr__, flush=True)

    # Keep the stdout RESULT line tiny — large JSON deadlocks Windows pipes.
    def _clip(text: str, limit: int = 12000) -> str:
        if len(text) <= limit:
            return text
        return text[: limit // 2] + "\n...\n" + text[-limit // 2 :]

    musicxml_paths = sorted(str(path) for path in cwd.glob("*.musicxml"))
    payload = {
        "ok": returncode == 0 and error is None,
        "returncode": returncode,
        "stdout": _clip(stdout_buf.getvalue()),
        "stderr": _clip(stderr_buf.getvalue()),
        "stages": {key: round(value, 3) for key, value in stages.items()},
        "musicxml_paths": musicxml_paths,
        "error": error,
    }
    result_path = cwd / ".pdf2muse_worker_result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    return (
        {
            "ok": payload["ok"],
            "returncode": payload["returncode"],
            "result_path": str(result_path),
            "error": error,
        },
        patched_device,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default="cuda",
        help="ONNX execution device for this worker process",
    )
    parser.add_argument(
        "--preload",
        action="store_true",
        help="Apply runtime patches immediately at startup",
    )
    args = parser.parse_args(argv)

    patched_device: Optional[str] = None
    if args.preload:
        _apply_runtime_patches(args.device)
        patched_device = args.device
        print(
            f"PDF2MUSE_DIAG worker_ready device={args.device}",
            file=sys.stderr,
            flush=True,
        )

    # Line-oriented JSON protocol on stdin; one RESULT_PREFIX JSON line per job on stdout.
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        if line in {"quit", "exit"}:
            break
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "ok": False,
                "returncode": 2,
                "stdout": "",
                "stderr": f"invalid JSON request: {exc}",
                "stages": {},
                "error": "invalid_request",
            }
            _emit_result(response)
            continue

        if request.get("cmd") == "shutdown":
            response = {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "stages": {}}
            _emit_result(response)
            break

        response, patched_device = _handle_request(request, patched_device=patched_device)
        _emit_result(response)

    return 0


def _emit_result(response: dict[str, Any]) -> None:
    """Emit RESULT on stderr (parent always pumps stderr; stdout pipes deadlock)."""

    line = RESULT_PREFIX + json.dumps(response)
    stream = getattr(sys, "__stderr__", None) or sys.stderr
    print(line, file=stream, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
