"""Oemer ONNX/TF adapter."""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .._oemer_common import classify_oemer_failure
from ..musicxml import analyze_musicxml_structure, validate_musicxml_file
from ..oemer_utils import OEMER_CHECKPOINT_ENV
from ..oemer_worker_client import (
    get_oemer_worker,
    shutdown_all_oemer_workers,
    worker_enabled_for_device,
)
from .base import AdapterStatus, OmrOptions, PageResult

logger = logging.getLogger(__name__)

_NON_RETRYABLE_FAILURES = frozenset(
    {"timeout", "invalid_musicxml", "no_musicxml_generated", "unexpected_error"}
)
_SYMBOL_FAILURES = frozenset({"symbol_extraction_empty_candidates", "symbol_extraction_failed"})


@dataclass(frozen=True)
class _OemerAttempt:
    name: str
    deskew: bool
    quality_profile: str
    line_threshold: Optional[float] = None
    step_size: Optional[int] = None
    batch_size: Optional[int] = None


class OemerAdapter:
    """Run oemer via PDF2Muse CPU/CUDA wrappers or TensorFlow ete module."""

    name = "oemer"

    def __init__(
        self,
        *,
        retries: bool = True,
        quality_report: bool = True,
        keep_page_artifacts: bool = False,
        artifact_root: Optional[Path] = None,
    ) -> None:
        self.retries = retries
        self.quality_report = quality_report
        self.keep_page_artifacts = keep_page_artifacts
        self.artifact_root = artifact_root

    def _record_attempt_artifacts(
        self,
        image_path: Path,
        attempt_name: str,
        attempt_dir: Path,
        metadata: dict,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        if not self.keep_page_artifacts or self.artifact_root is None:
            return
        page_artifacts = self.artifact_root / image_path.stem
        page_artifacts.mkdir(parents=True, exist_ok=True)
        image_copy = page_artifacts / image_path.name
        if image_path.exists() and not image_copy.exists():
            shutil.copy2(image_path, image_copy)
        attempt_artifacts = page_artifacts / attempt_name
        attempt_artifacts.mkdir(parents=True, exist_ok=True)
        (attempt_artifacts / "stdout.txt").write_text(stdout or "", encoding="utf-8")
        (attempt_artifacts / "stderr.txt").write_text(stderr or "", encoding="utf-8")
        import json

        (attempt_artifacts / "metadata.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        for cache_file in attempt_dir.glob("*.pkl"):
            shutil.copy2(cache_file, attempt_artifacts / cache_file.name)

    def healthcheck(self) -> AdapterStatus:
        try:
            import oemer  # noqa: F401
            import onnxruntime as ort

            providers = ort.get_available_providers()
            return AdapterStatus(
                name=self.name,
                available=True,
                message=f"oemer ready (ONNX providers: {providers})",
            )
        except ImportError as exc:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=f"oemer dependencies missing: {exc}",
            )

    def _attempts(self, options: OmrOptions) -> list[_OemerAttempt]:
        base = _OemerAttempt(
            name=options.quality_profile,
            deskew=options.deskew,
            quality_profile=options.quality_profile,
        )
        if not self.retries or options.use_tf:
            return [base]
        attempts = [base]
        if options.deskew:
            attempts.append(
                _OemerAttempt(
                    name=f"{options.quality_profile}_no_deskew",
                    deskew=False,
                    quality_profile=options.quality_profile,
                )
            )
        attempts.append(
            _OemerAttempt(
                name=f"{options.quality_profile}_low_staff_threshold",
                deskew=False,
                quality_profile=options.quality_profile,
                line_threshold=0.6,
            )
        )
        # Denser tiling before dropping to a smaller input profile (quality→balanced→fast).
        attempts.append(
            _OemerAttempt(
                name=f"{options.quality_profile}_dense_tiles",
                deskew=False,
                quality_profile=options.quality_profile,
                line_threshold=0.6,
                step_size=128,
                batch_size=16,
            )
        )
        if options.quality_profile == "quality":
            attempts.append(
                _OemerAttempt(
                    name="balanced",
                    deskew=False,
                    quality_profile="balanced",
                    line_threshold=0.6,
                    step_size=128,
                    batch_size=16,
                )
            )
        if options.quality_profile != "fast":
            attempts.append(
                _OemerAttempt(
                    name="fast",
                    deskew=False,
                    quality_profile="fast",
                )
            )
        return attempts

    def _should_continue_retries(
        self,
        failure_class: Optional[str],
        next_attempt: _OemerAttempt,
    ) -> bool:
        if failure_class in _NON_RETRYABLE_FAILURES:
            return False
        if failure_class in _SYMBOL_FAILURES or failure_class in {
            "staffline_empty_peaks",
            "staffline_no_candidates",
        }:
            # Prefer no-deskew / threshold / denser tiles / balanced before fast.
            return (
                not next_attempt.deskew
                or next_attempt.line_threshold is not None
                or next_attempt.step_size is not None
                or next_attempt.quality_profile in {"balanced", "fast"}
            )
        if failure_class == "oemer_failed":
            return (
                next_attempt.step_size is not None
                or next_attempt.quality_profile in {"balanced", "fast"}
            )
        if failure_class == "dewarp_empty_grid_groups":
            return (
                not next_attempt.deskew
                or next_attempt.line_threshold is not None
                or next_attempt.quality_profile in {"balanced", "fast"}
            )
        return True

    def _run_oemer_subprocess(
        self,
        command: list[str],
        *,
        attempt_dir: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        stream = os.environ.get("PDF2MUSE_OEMER_STREAM") == "1"
        if stream:
            return self._run_oemer_subprocess_streaming(
                command,
                attempt_dir=attempt_dir,
                env=env,
                timeout=timeout,
            )
        return subprocess.run(
            command,
            cwd=str(attempt_dir),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def _should_use_worker(self, options: OmrOptions) -> bool:
        return worker_enabled_for_device(options.device, use_tf=options.use_tf)

    def _run_oemer_via_worker(
        self,
        image_path: Path,
        attempt: _OemerAttempt,
        options: OmrOptions,
        *,
        attempt_dir: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        stream = os.environ.get("PDF2MUSE_OEMER_STREAM") == "1"
        worker = get_oemer_worker(options.device)
        payload = worker.run_page(
            image_path=image_path,
            cwd=attempt_dir,
            env=env,
            deskew=attempt.deskew,
            use_tf=options.use_tf,
            save_cache=bool(options.save_cache or self.keep_page_artifacts),
            timeout=timeout,
            stream=stream,
        )
        stdout = payload.get("stdout") or ""
        stderr = payload.get("stderr") or ""
        stages = payload.get("stages") or {}
        if stages:
            summary = "PDF2MUSE_DIAG stage_timings " + " ".join(
                f"{key}={value}s" for key, value in sorted(stages.items())
            )
            print(summary, flush=True)
            stdout = f"{stdout}\n{summary}\n" if stdout else f"{summary}\n"
        result = subprocess.CompletedProcess(
            args=["pdf2muse._oemer_worker", str(image_path)],
            returncode=int(payload.get("returncode") or (0 if payload.get("ok") else 1)),
            stdout=stdout,
            stderr=stderr,
        )
        # Attach stages for attempt metadata without breaking CompletedProcess.
        result.stages = stages  # type: ignore[attr-defined]
        if result.returncode != 0 or payload.get("error"):
            raise subprocess.CalledProcessError(
                result.returncode or 1,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result

    def _run_oemer(
        self,
        image_path: Path,
        attempt: _OemerAttempt,
        options: OmrOptions,
        *,
        attempt_dir: Path,
        env: dict[str, str],
        timeout: int,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        if self._should_use_worker(options):
            try:
                return self._run_oemer_via_worker(
                    image_path,
                    attempt,
                    options,
                    attempt_dir=attempt_dir,
                    env=env,
                    timeout=timeout,
                )
            except Exception as exc:
                logger.warning(
                    "Warm oemer worker failed (%s); shutting down worker to free VRAM "
                    "before cold subprocess fallback",
                    exc,
                )
                try:
                    shutdown_all_oemer_workers()
                except Exception as shutdown_exc:
                    logger.warning("Failed to shut down warm worker: %s", shutdown_exc)
        return self._run_oemer_subprocess(
            command,
            attempt_dir=attempt_dir,
            env=env,
            timeout=timeout,
        )

    def _run_oemer_subprocess_streaming(
        self,
        command: list[str],
        *,
        attempt_dir: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        """Run oemer with live stdout/stderr while still capturing for classification."""

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _tee(stream, chunks: list[str], dest) -> None:
            for line in iter(stream.readline, ""):
                chunks.append(line)
                dest.write(line)
                dest.flush()
            stream.close()

        proc = subprocess.Popen(
            command,
            cwd=str(attempt_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        stdout_thread = threading.Thread(
            target=_tee,
            args=(proc.stdout, stdout_chunks, sys.stdout),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_tee,
            args=(proc.stderr, stderr_chunks, sys.stderr),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=timeout,
                output="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
            ) from exc
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        result = subprocess.CompletedProcess(
            args=command,
            returncode=returncode,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
        )
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode,
                command,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result

    def _command(self, image_path: Path, attempt: _OemerAttempt, options: OmrOptions) -> list[str]:
        if options.use_tf:
            oemer_module = "oemer.ete"
        elif options.device == "cuda":
            oemer_module = "pdf2muse._oemer_cuda"
        else:
            oemer_module = "pdf2muse._oemer_cpu"
        command = [sys.executable, "-W", "ignore", "-m", oemer_module, str(image_path)]
        if not attempt.deskew:
            command.append("--without-deskew")
        if options.use_tf:
            command.append("--use-tf")
        if options.save_cache or self.keep_page_artifacts:
            command.append("--save-cache")
        return command

    def _env(self, attempt: _OemerAttempt, options: OmrOptions) -> dict[str, str]:
        env = os.environ.copy()
        # Keep ORT/OpenMP from oversubscribing during CUDA EP work, but do not
        # starve NumPy/OpenCV post-processing (often the majority of wall time).
        cpu_workers = str(max(1, min(8, (os.cpu_count() or 4))))
        if options.device == "cuda":
            env["OMP_NUM_THREADS"] = cpu_workers
            env["OPENBLAS_NUM_THREADS"] = cpu_workers
            env["MKL_NUM_THREADS"] = cpu_workers
            env["NUMEXPR_NUM_THREADS"] = cpu_workers
            # CPU EP nodes that fall back from ConvTranspose still benefit from threads.
            env["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "2"
            env["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = cpu_workers
        else:
            env["OMP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
            env["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"
        # Quiet hybrid CUDA→CPU ConvTranspose warnings that look like "not using GPU".
        env.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
        env["PDF2MUSE_OEMER_QUALITY_PROFILE"] = attempt.quality_profile
        if attempt.line_threshold is not None:
            env["PDF2MUSE_OEMER_LINE_THRESHOLD"] = str(attempt.line_threshold)
        else:
            env.pop("PDF2MUSE_OEMER_LINE_THRESHOLD", None)
        if attempt.step_size is not None:
            env["PDF2MUSE_OEMER_STEP_SIZE"] = str(attempt.step_size)
        else:
            env.pop("PDF2MUSE_OEMER_STEP_SIZE", None)
        if attempt.batch_size is not None:
            env["PDF2MUSE_OEMER_BATCH_SIZE"] = str(attempt.batch_size)
        else:
            env.pop("PDF2MUSE_OEMER_BATCH_SIZE", None)
        if not options.use_tf:
            env["PDF2MUSE_OEMER_DIAGNOSTICS"] = "1"
        else:
            env.pop("PDF2MUSE_OEMER_DIAGNOSTICS", None)
        if options.checkpoint_dir:
            env[OEMER_CHECKPOINT_ENV] = str(options.checkpoint_dir)
        return env

    def recognize_page(
        self,
        image_path: Path,
        output_dir: Path,
        options: OmrOptions,
    ) -> PageResult:
        page_dir = output_dir / image_path.stem
        page_dir.mkdir(parents=True, exist_ok=True)
        attempts_meta: list[dict] = []
        last_error = f"No oemer attempts were run for {image_path.name}"

        last_failure_class: Optional[str] = None
        # Cap total wall time across retries; each attempt still respects timeout_seconds.
        wall_budget = max(1, int(options.timeout_seconds))
        if self.retries and not options.use_tf:
            wall_budget = max(wall_budget, int(options.timeout_seconds) * 2)
        page_deadline = time.monotonic() + wall_budget

        for index, attempt in enumerate(self._attempts(options)):
            remaining = page_deadline - time.monotonic()
            if remaining <= 1:
                last_failure_class = "timeout"
                last_error = (
                    f"oemer page wall-time budget exhausted "
                    f"({options.timeout_seconds}s) on {image_path.name}"
                )
                logger.error(last_error)
                break
            if index > 0 and not self._should_continue_retries(
                last_failure_class, attempt
            ):
                continue
            attempt_dir = page_dir if index == 0 else page_dir / attempt.name
            attempt_dir.mkdir(parents=True, exist_ok=True)
            command = self._command(image_path, attempt, options)
            configured_timeout = max(1, int(options.timeout_seconds))
            # Keep the configured per-attempt timeout unless the page wall budget is nearly spent.
            if remaining + 1.0 < configured_timeout:
                attempt_timeout = max(1, min(configured_timeout, math.ceil(remaining)))
            else:
                attempt_timeout = configured_timeout
            metadata: dict = {
                "attempt": attempt.name,
                "deskew": attempt.deskew,
                "quality_profile": attempt.quality_profile,
                "line_threshold": attempt.line_threshold,
                "command": command,
                "cwd": str(attempt_dir),
                "status": "not_run",
                "failure_class": None,
                "musicxml": None,
                "timeout_seconds": attempt_timeout,
            }
            try:
                result = self._run_oemer(
                    image_path,
                    attempt,
                    options,
                    attempt_dir=attempt_dir,
                    env=self._env(attempt, options),
                    timeout=attempt_timeout,
                    command=command,
                )
                stdout = getattr(result, "stdout", "") or ""
                stderr = getattr(result, "stderr", "") or ""
                stages = getattr(result, "stages", None)
                if isinstance(stages, dict) and stages:
                    metadata["stages"] = stages
                logger.debug(stdout)
                expected_musicxml = attempt_dir / f"{image_path.stem}.musicxml"
                musicxml_files = list(attempt_dir.glob("*.musicxml"))
                if not musicxml_files:
                    last_failure_class = "no_musicxml_generated"
                    metadata.update(status="failed", failure_class="no_musicxml_generated")
                    last_error = f"No MusicXML file generated for {image_path.name}"
                    attempts_meta.append(metadata)
                    break

                actual_file = next(
                    (p for p in musicxml_files if p.name == expected_musicxml.name),
                    musicxml_files[0],
                )
                combined_path = output_dir / f"{image_path.stem}.musicxml"
                if actual_file.resolve() != combined_path.resolve():
                    shutil.copy2(actual_file, combined_path)

                validation = validate_musicxml_file(combined_path)
                if not validation.ok:
                    last_failure_class = "invalid_musicxml"
                    metadata.update(status="failed", failure_class="invalid_musicxml")
                    last_error = f"Invalid MusicXML for {image_path.name}: {validation.error}"
                    attempts_meta.append(metadata)
                    return PageResult(
                        error=last_error,
                        failure_class="invalid_musicxml",
                        backend=self.name,
                        attempts=attempts_meta,
                    )

                metadata.update(status="succeeded", musicxml=str(combined_path))
                if self.quality_report:
                    metadata["structure"] = asdict(analyze_musicxml_structure(combined_path))
                attempts_meta.append(metadata)
                self._record_attempt_artifacts(
                    image_path,
                    attempt.name,
                    attempt_dir,
                    metadata,
                    stdout,
                    stderr,
                )
                return PageResult(
                    musicxml_path=combined_path,
                    backend=self.name,
                    attempts=attempts_meta,
                )
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                stdout = (exc.stdout or "").strip()
                failure_class = classify_oemer_failure(stdout, stderr)
                last_failure_class = failure_class
                snippet = stderr or stdout or str(exc)
                if len(snippet) > 800:
                    snippet = snippet[:800] + "..."
                metadata.update(status="failed", failure_class=failure_class)
                attempts_meta.append(metadata)
                self._record_attempt_artifacts(
                    image_path,
                    attempt.name,
                    attempt_dir,
                    metadata,
                    stdout,
                    stderr,
                )
                last_error = f"oemer failed on {image_path.name} [{failure_class}]: {snippet}"
                logger.error(last_error)
                if failure_class in _NON_RETRYABLE_FAILURES:
                    break
                continue
            except subprocess.TimeoutExpired as exc:
                last_failure_class = "timeout"
                stdout = ""
                if exc.stdout:
                    stdout = (
                        exc.stdout.decode("utf-8", errors="replace")
                        if isinstance(exc.stdout, bytes)
                        else str(exc.stdout)
                    )
                metadata.update(status="failed", failure_class="timeout")
                attempts_meta.append(metadata)
                self._record_attempt_artifacts(
                    image_path,
                    attempt.name,
                    attempt_dir,
                    metadata,
                    stdout,
                    "",
                )
                last_error = (
                    f"oemer timed out after {options.timeout_seconds} seconds "
                    f"on {image_path.name}"
                )
                if stdout.strip():
                    last_error = f"{last_error}: {stdout.strip()}"
                logger.error(last_error)
                break
            except Exception as exc:
                last_failure_class = "unexpected_error"
                metadata.update(status="failed", failure_class="unexpected_error")
                attempts_meta.append(metadata)
                last_error = f"Unexpected error on {image_path.name}: {exc}"
                logger.error(last_error)
                continue

        return PageResult(
            error=last_error,
            failure_class=attempts_meta[-1].get("failure_class") if attempts_meta else "oemer_failed",
            backend=self.name,
            attempts=attempts_meta,
        )
