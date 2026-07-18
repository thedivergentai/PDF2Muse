"""Shared runtime patches for running oemer through PDF2Muse wrappers."""

from __future__ import annotations

import functools
import math
import os
import time
from pathlib import Path
from typing import Optional

from .oemer_utils import OEMER_CHECKPOINT_ENV

_OEMER_PROFILE_PIXELS = {
    "fast": 1_500_000,
    "balanced": 3_000_000,
    "quality": 4_350_000,
}
_DEFAULT_OEMER_PROFILE = "quality"
_MAX_OEMER_PIXELS = _OEMER_PROFILE_PIXELS[_DEFAULT_OEMER_PROFILE]

# Accumulated per-page stage timings (seconds). Reset via reset_stage_timings().
_STAGE_TIMINGS: dict[str, float] = {}
_SESSION_CACHE: dict[str, object] = {}
_SESSION_CACHE_ENABLED = False


def reset_stage_timings() -> None:
    """Clear per-page stage timing accumulators."""

    _STAGE_TIMINGS.clear()


def get_stage_timings() -> dict[str, float]:
    """Return a copy of accumulated stage timings in seconds."""

    return dict(_STAGE_TIMINGS)


def _record_stage(name: str, elapsed: float) -> None:
    _STAGE_TIMINGS[name] = float(_STAGE_TIMINGS.get(name, 0.0)) + float(elapsed)


def format_stage_timings_line(stages: Optional[dict[str, float]] = None) -> str:
    """One-line diagnostic summary for logs and conversion reports."""

    data = stages if stages is not None else get_stage_timings()
    if not data:
        return "PDF2MUSE_DIAG stage_timings (none)"
    parts = [f"{key}={value:.3f}s" for key, value in sorted(data.items())]
    return "PDF2MUSE_DIAG stage_timings " + " ".join(parts)


def clear_onnx_session_cache() -> None:
    """Drop cached ORT sessions (e.g. worker shutdown)."""

    _SESSION_CACHE.clear()


def _patch_onnxruntime_session_cache() -> None:
    """Reuse InferenceSession objects keyed by model path within one process."""

    global _SESSION_CACHE_ENABLED
    if _SESSION_CACHE_ENABLED:
        return

    import onnxruntime as ort

    original_session = ort.InferenceSession

    @functools.wraps(original_session)
    def cached_session(*args, **kwargs):
        model_path = ""
        if args:
            model_path = str(args[0])
        elif "path" in kwargs:
            model_path = str(kwargs["path"])
        providers = kwargs.get("providers")
        if providers is None and len(args) >= 3:
            providers = args[2]
        cache_key = f"{model_path}|{providers!r}"
        cached = _SESSION_CACHE.get(cache_key)
        if cached is not None:
            _record_stage("session_load", 0.0)
            return cached
        start = time.perf_counter()
        session = original_session(*args, **kwargs)
        elapsed = time.perf_counter() - start
        _record_stage("session_load", elapsed)
        _SESSION_CACHE[cache_key] = session
        print(
            f"PDF2MUSE_DIAG session_load model={Path(model_path).name} "
            f"elapsed={elapsed:.3f}s cached=0",
            flush=True,
        )
        return session

    ort.InferenceSession = cached_session
    _SESSION_CACHE_ENABLED = True

def _configured_max_pixels() -> int:
    explicit = os.environ.get("PDF2MUSE_OEMER_MAX_PIXELS")
    if explicit:
        try:
            value = int(explicit)
        except ValueError:
            value = 0
        if value > 0:
            return value
    profile = os.environ.get("PDF2MUSE_OEMER_QUALITY_PROFILE", _DEFAULT_OEMER_PROFILE)
    return _OEMER_PROFILE_PIXELS.get(profile, _OEMER_PROFILE_PIXELS[_DEFAULT_OEMER_PROFILE])


def _configured_line_threshold(default: float) -> float:
    explicit = os.environ.get("PDF2MUSE_OEMER_LINE_THRESHOLD")
    if explicit is None:
        return default
    try:
        return float(explicit)
    except ValueError:
        return default


_DEFAULT_OEMER_STEP_SIZE = 192
_DEFAULT_OEMER_BATCH_SIZE = 8
_QUALITY_OEMER_STEP_SIZE = 128
_QUALITY_OEMER_BATCH_SIZE = 16
_TILING_PATCHED = False


def _configured_step_size() -> int:
    raw = os.environ.get("PDF2MUSE_OEMER_STEP_SIZE")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    profile = os.environ.get("PDF2MUSE_OEMER_QUALITY_PROFILE", _DEFAULT_OEMER_PROFILE)
    if profile == "quality":
        return _QUALITY_OEMER_STEP_SIZE
    return _DEFAULT_OEMER_STEP_SIZE


def _configured_batch_size() -> int:
    raw = os.environ.get("PDF2MUSE_OEMER_BATCH_SIZE")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    profile = os.environ.get("PDF2MUSE_OEMER_QUALITY_PROFILE", _DEFAULT_OEMER_PROFILE)
    if profile == "quality":
        return _QUALITY_OEMER_BATCH_SIZE
    return _DEFAULT_OEMER_BATCH_SIZE


def _patch_oemer_inference_tiling() -> None:
    """Apply profile-aware tiling; quality uses stock-dense 128/16, others 192/8."""

    global _TILING_PATCHED
    if _TILING_PATCHED:
        return

    from oemer import inference

    original_inference = inference.inference
    step = _configured_step_size()
    batch = _configured_batch_size()
    print(
        f"PDF2MUSE_DIAG inference_tiling step_size={step} batch_size={batch}",
        flush=True,
    )

    @functools.wraps(original_inference)
    def tiled_inference(
        model_path,
        img_path,
        step_size=None,
        batch_size=None,
        manual_th=None,
        use_tf: bool = False,
    ):
        return original_inference(
            model_path,
            img_path,
            step_size=_configured_step_size() if step_size is None else step_size,
            batch_size=_configured_batch_size() if batch_size is None else batch_size,
            manual_th=manual_th,
            use_tf=use_tf,
        )

    inference.inference = tiled_inference
    _TILING_PATCHED = True


def _maybe_release_sessions_for_single_model_vram() -> None:
    """Drop cached ORT sessions between models when VRAM is constrained."""

    if os.environ.get("PDF2MUSE_OEMER_SINGLE_MODEL_VRAM") != "1":
        return
    if not _SESSION_CACHE:
        return
    clear_onnx_session_cache()
    print(
        "PDF2MUSE_DIAG single_model_vram cleared session cache between inference passes",
        flush=True,
    )
    try:
        import gc

        gc.collect()
    except Exception:
        pass


def _patch_oemer_checkpoint_dir() -> None:
    """Redirect oemer checkpoint paths when PDF2MUSE_OEMER_CHECKPOINT_DIR is set."""
    checkpoint_root = os.environ.get(OEMER_CHECKPOINT_ENV)
    if not checkpoint_root:
        return
    try:
        import oemer
        from oemer import inference
    except ImportError:
        return

    stock_root = str((Path(oemer.__file__).parent / "checkpoints").resolve())
    custom_root = str(Path(checkpoint_root).resolve())
    if stock_root == custom_root:
        return

    original_inference = inference.inference

    @functools.wraps(original_inference)
    def redirected_inference(model_path, img_path, *args, **kwargs):
        model_path_str = str(model_path)
        if model_path_str.startswith(stock_root):
            model_path_str = model_path_str.replace(stock_root, custom_root, 1)
        return original_inference(model_path_str, img_path, *args, **kwargs)

    inference.inference = redirected_inference


def _patch_oemer_resize_image() -> None:
    """Bound oemer input size using the selected quality profile."""
    from oemer import inference

    def bounded_resize(image):
        width, height = image.size
        pixels = width * height
        max_pixels = _configured_max_pixels()
        if pixels <= max_pixels:
            return image

        ratio = math.sqrt(max_pixels / pixels)
        target = (max(1, round(width * ratio)), max(1, round(height * ratio)))
        return image.resize(target)

    inference.resize_image = bounded_resize


def _patch_oemer_inference_diagnostics() -> None:
    """Print coarse oemer inference timing markers for timeout diagnosis."""
    from oemer import inference

    original_inference = inference.inference

    @functools.wraps(original_inference)
    def timed_inference(model_path, img_path, *args, **kwargs):
        model_name = Path(str(model_path)).name
        start = time.perf_counter()
        print(
            f"PDF2MUSE_DIAG inference_start model={model_name} image={img_path}",
            flush=True,
        )
        try:
            return original_inference(model_path, img_path, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            stage_key = f"inference_{model_name}"
            _record_stage(stage_key, elapsed)
            print(
                f"PDF2MUSE_DIAG inference_done model={model_name} elapsed={elapsed:.3f}s",
                flush=True,
            )
            _maybe_release_sessions_for_single_model_vram()

    inference.inference = timed_inference


def _patch_oemer_postprocess_stage_timings() -> None:
    """Time coarse post-processing buckets when hooks are available."""
    try:
        from oemer import dewarp
    except ImportError:
        return

    if getattr(dewarp, "_pdf2muse_timed", False):
        return

    # Time the main dewarp entry used by oemer.ete when present.
    target_name = None
    for candidate in ("dewarp", "run", "main"):
        if callable(getattr(dewarp, candidate, None)):
            target_name = candidate
            break
    if target_name is None:
        return

    original = getattr(dewarp, target_name)

    @functools.wraps(original)
    def timed_dewarp(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            _record_stage("dewarp", time.perf_counter() - start)

    setattr(dewarp, target_name, timed_dewarp)
    dewarp._pdf2muse_timed = True


def _patch_oemer_postprocessing_guards() -> None:
    """Classify known empty-data failures before oemer raises opaque errors."""
    _patch_dewarp_empty_grid_guard()
    _patch_staffline_empty_candidate_guard()
    _patch_staffline_empty_peak_guard()
    _patch_staffline_threshold()
    _patch_symbol_extraction_guard()
    _patch_build_system_key_guard()
    _patch_build_system_multitrack_align_guard()
    _patch_build_system_wrapped_forward_guard()
    _patch_build_system_wrapped_backup_guard()


def _patch_dewarp_empty_grid_guard() -> None:
    from oemer import dewarp

    original_connect = dewarp.connect_nearby_grid_group

    @functools.wraps(original_connect)
    def guarded_connect(gg_map, grid_groups, grid_map, grids, *args, **kwargs):
        if not grid_groups:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE dewarp_empty_grid_groups: "
                "oemer dewarp found no staffline grid groups"
            )
        return original_connect(gg_map, grid_groups, grid_map, grids, *args, **kwargs)

    dewarp.connect_nearby_grid_group = guarded_connect


def _patch_staffline_empty_candidate_guard() -> None:
    from oemer import staffline_extraction

    original_align = staffline_extraction.align_staffs

    @functools.wraps(original_align)
    def guarded_align(staffs, *args, **kwargs):
        if not staffs:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE staffline_no_candidates: "
                "oemer detected no complete staffline candidates"
            )
        return original_align(staffs, *args, **kwargs)

    staffline_extraction.align_staffs = guarded_align


def _patch_staffline_empty_peak_guard() -> None:
    from oemer import staffline_extraction

    original_filter = staffline_extraction.filter_line_peaks

    @functools.wraps(original_filter)
    def guarded_filter(peaks, *args, **kwargs):
        if len(peaks) == 0:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE staffline_empty_peaks: "
                "oemer staffline filtering found no peak candidates"
            )
        try:
            return original_filter(peaks, *args, **kwargs)
        except IndexError as exc:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE staffline_empty_peaks: "
                "oemer staffline filtering exhausted peak candidates"
            ) from exc

    staffline_extraction.filter_line_peaks = guarded_filter


def _patch_staffline_threshold() -> None:
    from oemer import staffline_extraction

    original_extract = staffline_extraction.extract

    @functools.wraps(original_extract)
    def configured_extract(*args, **kwargs):
        kwargs["line_threshold"] = _configured_line_threshold(
            float(kwargs.get("line_threshold", 0.8))
        )
        return original_extract(*args, **kwargs)

    staffline_extraction.extract = configured_extract


def _patch_symbol_extraction_guard() -> None:
    from oemer import bbox

    original_merge = bbox.rm_merge_overlap_bbox

    @functools.wraps(original_merge)
    def guarded_merge(bboxes, *args, **kwargs):
        if bboxes is None or len(bboxes) == 0:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE symbol_extraction_empty_candidates: "
                "oemer symbol extraction found no bbox candidates"
            )
        try:
            return original_merge(bboxes, *args, **kwargs)
        except IndexError as exc:
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE symbol_extraction_empty_candidates: "
                "oemer symbol bbox merge failed on empty candidate data"
            ) from exc

    bbox.rm_merge_overlap_bbox = guarded_merge


def _patch_build_system_key_guard() -> None:
    from oemer import build_system

    original_get_key = build_system.Measure.get_key

    @functools.wraps(original_get_key)
    def guarded_get_key(self, *args, **kwargs):
        try:
            return original_get_key(self, *args, **kwargs)
        except IndexError as exc:
            if getattr(self, "sfns", None):
                return build_system.Key(0)
            raise RuntimeError(
                "PDF2MUSE_OEMER_STAGE build_key_signature_no_candidates: "
                "oemer MusicXML builder found no key-signature candidates"
            ) from exc

    build_system.Measure.get_key = guarded_get_key


def _patch_build_system_multitrack_align_guard() -> None:
    from oemer import build_system

    original_align = build_system.Measure.align_symbols

    @functools.wraps(original_align)
    def guarded_align_symbols(self, *args, **kwargs):
        track_nums = build_system.get_total_track_nums()
        if track_nums <= 2:
            return original_align(self, *args, **kwargs)

        unit_size = build_system.get_global_unit_size()
        time_slots = []
        last_x = None
        for sym in self.symbols:
            if isinstance(sym, (build_system.Clef, build_system.Sfn)):
                continue
            if last_x is None:
                last_x = sym.x_center
                time_slots.append([sym])
            elif abs(sym.x_center - last_x) < unit_size:
                time_slots[-1].append(sym)
            else:
                time_slots.append([sym])
                last_x = sym.x_center

        track_duras = build_system.np.zeros((len(time_slots), track_nums), dtype=build_system.np.uint16)
        for idx, slot in enumerate(time_slots):
            track_dura = [[] for _ in range(track_nums)]
            for sym in slot:
                if 0 <= sym.track < track_nums:
                    track_dura[sym.track].append(build_system.get_duration(sym))
            for track, durations in enumerate(track_dura):
                track_duras[idx, track] = min(durations) if durations else 0

        self.time_slots = time_slots
        self.slot_duras = track_duras
        return None

    build_system.Measure.align_symbols = guarded_align_symbols


def _patch_build_system_wrapped_forward_guard() -> None:
    from oemer import build_system

    original_perform = build_system.AddForward.perform

    @functools.wraps(original_perform)
    def guarded_forward_perform(self, parent_elem=None):
        if 32768 <= int(self.dura) <= 65535:
            backup = build_system.decode_backup(65536 - int(self.dura))
            if parent_elem is not None:
                parent_elem.append(backup)
            return backup
        return original_perform(self, parent_elem=parent_elem)

    build_system.AddForward.perform = guarded_forward_perform


def _patch_build_system_wrapped_backup_guard() -> None:
    from oemer import build_system

    original_perform = build_system.AddBackup.perform

    @functools.wraps(original_perform)
    def guarded_backup_perform(self, parent_elem=None):
        if 32768 <= int(self.dura) <= 65535:
            forward = build_system.decode_forward(65536 - int(self.dura))
            if parent_elem is not None:
                parent_elem.append(forward)
            return forward
        return original_perform(self, parent_elem=parent_elem)

    build_system.AddBackup.perform = guarded_backup_perform


def classify_oemer_failure(stdout: Optional[str], stderr: Optional[str]) -> str:
    """Return a stable failure category for known oemer failure signatures."""
    text = "\n".join(part for part in (stdout, stderr) if part)
    if "PDF2MUSE_OEMER_STAGE dewarp_empty_grid_groups" in text:
        return "dewarp_empty_grid_groups"
    if "PDF2MUSE_OEMER_STAGE staffline_no_candidates" in text:
        return "staffline_no_candidates"
    if "PDF2MUSE_OEMER_STAGE staffline_empty_peaks" in text:
        return "staffline_empty_peaks"
    if "PDF2MUSE_OEMER_STAGE symbol_extraction_empty_candidates" in text:
        return "symbol_extraction_empty_candidates"
    if "symbol_extraction.py" in text and "IndexError" in text:
        return "symbol_extraction_empty_candidates"
    if "parse_clefs_keys" in text and "IndexError" in text:
        return "symbol_extraction_empty_candidates"
    if "max() iterable argument is empty" in text:
        return "staffline_no_candidates"
    if "filter_line_peaks" in text and "index 0 is out of bounds" in text:
        return "staffline_empty_peaks"
    if "align_symbols" in text and "AssertionError" in text:
        return "build_multitrack_alignment_unsupported"
    if "sfns_cands[0]" in text or (
        "build_system.py" in text and "Building MusicXML document" in text
    ):
        return "build_key_signature_no_candidates"
    if "IndexError: list index out of range" in text and "dewarp.py" in text:
        return "dewarp_empty_grid_groups"
    if "No MusicXML file generated" in text:
        return "no_musicxml_generated"
    if "Invalid MusicXML" in text:
        return "invalid_musicxml"
    if "timed out" in text:
        return "timeout"
    return "oemer_failed"
