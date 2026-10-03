"""Client for the persistent pdf2muse._oemer_worker process."""

from __future__ import annotations

import atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ._oemer_worker import RESULT_PREFIX

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_WORKERS: dict[str, "_OemerWorkerClient"] = {}


def worker_enabled_for_device(device: str, *, use_tf: bool = False) -> bool:
    """Default: warm worker on for CPU and CUDA. Set PDF2MUSE_OEMER_WORKER=0 to disable."""

    if use_tf:
        return False
    flag = os.environ.get("PDF2MUSE_OEMER_WORKER")
    if flag == "0":
        return False
    return True


def get_oemer_worker(device: str) -> "_OemerWorkerClient":
    with _LOCK:
        existing = _WORKERS.get(device)
        if existing is not None and existing.alive:
            return existing
        client = _OemerWorkerClient(device=device)
        client.start()
        _WORKERS[device] = client
        return client


def reset_oemer_workers(device: Optional[str] = None) -> None:
    """Shut down warm workers so the next call starts a clean process."""

    with _LOCK:
        if device is None:
            workers = list(_WORKERS.values())
            _WORKERS.clear()
        else:
            worker = _WORKERS.pop(device, None)
            workers = [worker] if worker is not None else []
    for worker in workers:
        try:
            worker.shutdown()
        except Exception as exc:
            logger.warning("oemer worker shutdown during reset failed: %s", exc)


def shutdown_all_oemer_workers() -> None:
    reset_oemer_workers(None)


atexit.register(shutdown_all_oemer_workers)


class _OemerWorkerClient:
    """JSON-line client talking to `python -m pdf2muse._oemer_worker`."""

    def __init__(self, *, device: str) -> None:
        self.device = device
        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.alive:
            return
        command = [
            sys.executable,
            "-W",
            "ignore",
            "-m",
            "pdf2muse._oemer_worker",
            "--device",
            self.device,
            "--preload",
        ]
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        # Wait briefly for preload readiness marker.
        deadline = time.monotonic() + 120
        ready = False
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                err = self._drain_stderr()
                raise RuntimeError(f"oemer worker failed to start: {err or self._proc.returncode}")
            line_holder: dict[str, Optional[str]] = {"line": None}

            def _read() -> None:
                try:
                    line_holder["line"] = self._proc.stderr.readline()  # type: ignore[union-attr]
                except Exception:
                    line_holder["line"] = ""

            thread = threading.Thread(target=_read, daemon=True)
            thread.start()
            thread.join(timeout=1.0)
            line = line_holder["line"]
            if line and "worker_ready" in line:
                ready = True
                if os.environ.get("PDF2MUSE_OEMER_STREAM") == "1":
                    sys.stderr.write(line)
                    sys.stderr.flush()
                break
            if line and os.environ.get("PDF2MUSE_OEMER_STREAM") == "1":
                sys.stderr.write(line)
                sys.stderr.flush()
        if not ready:
            logger.warning(
                "Warm oemer worker did not print ready marker; continuing anyway (pid=%s)",
                self._proc.pid,
            )
        logger.info("Started warm oemer worker pid=%s device=%s", self._proc.pid, self.device)

    def shutdown(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def run_page(
        self,
        *,
        image_path: Path,
        cwd: Path,
        env: dict[str, str],
        deskew: bool,
        use_tf: bool,
        save_cache: bool,
        timeout: int,
        stream: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if not self.alive:
                self.start()
            assert self._proc is not None and self._proc.stdin and self._proc.stdout

            # Only forward oemer-relevant env keys; worker process already has base env.
            env_updates = {
                key: value
                for key, value in env.items()
                if key.startswith("PDF2MUSE_")
                or key
                in {
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "ONNXRUNTIME_INTER_OP_NUM_THREADS",
                    "ONNXRUNTIME_INTRA_OP_NUM_THREADS",
                    "ORT_LOG_SEVERITY_LEVEL",
                }
            }
            request = {
                "image_path": str(image_path),
                "cwd": str(cwd),
                "device": self.device,
                "deskew": deskew,
                "use_tf": use_tf,
                "save_cache": save_cache,
                "env": env_updates,
            }
            self._proc.stdin.write(json.dumps(request) + "\n")
            self._proc.stdin.flush()

            stderr_chunks: list[str] = []
            stop_stderr = threading.Event()
            result_holder: dict[str, Any] = {}

            def _stderr_pump() -> None:
                assert self._proc is not None and self._proc.stderr is not None
                while not stop_stderr.is_set():
                    line = self._proc.stderr.readline()
                    if line == "":
                        break
                    if line.startswith(RESULT_PREFIX):
                        try:
                            result_holder["header"] = json.loads(
                                line[len(RESULT_PREFIX) :].strip()
                            )
                        except json.JSONDecodeError as exc:
                            result_holder["error"] = str(exc)
                        stop_stderr.set()
                        continue
                    stderr_chunks.append(line)
                    if stream:
                        sys.stderr.write(line)
                        sys.stderr.flush()

            pump = threading.Thread(target=_stderr_pump, daemon=True)
            pump.start()
            try:
                deadline = time.monotonic() + max(1, timeout)
                while "header" not in result_holder and "error" not in result_holder:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._kill()
                        raise subprocess.TimeoutExpired(
                            cmd=["pdf2muse._oemer_worker"],
                            timeout=timeout,
                            output="",
                            stderr="".join(stderr_chunks),
                        )
                    if self._proc.poll() is not None and not pump.is_alive():
                        err = "".join(stderr_chunks) or f"exit={self._proc.returncode}"
                        raise RuntimeError(f"oemer worker exited unexpectedly: {err}")
                    pump.join(timeout=min(0.5, remaining))
                    if "header" in result_holder or "error" in result_holder:
                        break
                    # Keep stdout drained so it cannot fill and block the worker.
                    while self._readline_stdout(timeout=0.01):
                        pass

                if "error" in result_holder:
                    raise RuntimeError(f"oemer worker RESULT decode failed: {result_holder['error']}")
                header = result_holder["header"]
                result_path = header.get("result_path")
                if result_path:
                    payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
                else:
                    payload = header
                drained = "".join(stderr_chunks)
                if drained:
                    existing = payload.get("stderr") or ""
                    if drained not in existing:
                        payload["stderr"] = existing + drained
                return payload
            finally:
                stop_stderr.set()
                pump.join(timeout=1)

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def _readline_stdout(self, *, timeout: float) -> Optional[str]:
        assert self._proc is not None and self._proc.stdout is not None
        # Blocking readline with a soft timeout via polling thread would be heavy;
        # use short waits by checking poll + reading when data ready is hard on Windows.
        # Practical approach: blocking readline; TimeoutExpired handled by outer deadline
        # via a reader thread.
        result: dict[str, Optional[str]] = {"line": None}
        error: list[BaseException] = []

        def _read() -> None:
            try:
                result["line"] = self._proc.stdout.readline()  # type: ignore[union-attr]
            except BaseException as exc:  # noqa: BLE001
                error.append(exc)

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            return None
        if error:
            raise error[0]
        line = result["line"]
        if line is None or line == "":
            return None
        return line.rstrip("\n")

    def _drain_stderr(self) -> str:
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            return self._proc.stderr.read() or ""
        except Exception:
            return ""

    def _drain_stderr_nonblocking(self, chunks: list[str], *, stream: bool) -> None:
        # Best-effort: on Windows pipes aren't easily non-blocking; skip if no data API.
        # Streaming still works because worker tees to its stderr during the job; parent
        # collects remaining stderr after RESULT arrives via a short background drain.
        if self._proc is None or self._proc.stderr is None:
            return
        # Read whatever is already buffered by spawning a timed read of one line.
        result: dict[str, Optional[str]] = {"line": ""}

        def _read_line() -> None:
            try:
                result["line"] = self._proc.stderr.readline()  # type: ignore[union-attr]
            except Exception:
                result["line"] = ""

        while True:
            thread = threading.Thread(target=_read_line, daemon=True)
            thread.start()
            thread.join(timeout=0.05)
            if thread.is_alive():
                break
            line = result["line"]
            if not line:
                break
            chunks.append(line)
            if stream:
                sys.stderr.write(line)
                sys.stderr.flush()
