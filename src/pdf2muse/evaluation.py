"""Experimental evaluation helpers for PDF2Muse OMR output."""

from __future__ import annotations

import json
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from .core import PDF2MusePipeline

logger = logging.getLogger(__name__)


class EvaluationManifestError(ValueError):
    """Raised when an evaluation manifest is missing required data."""


@dataclass(frozen=True)
class EvaluationSample:
    """One local evaluation sample from a manifest."""

    sample_id: str
    input_path: Path
    ground_truth_path: Path
    source: str = "local"
    first_page: Optional[int] = None
    last_page: Optional[int] = None
    license_notes: Optional[str] = None
    difficulty_tags: tuple[str, ...] = ()
    input_quality: dict[str, Any] = field(default_factory=dict)

    @property
    def trusted_for_accuracy(self) -> bool:
        if "trusted_for_accuracy" in self.input_quality:
            return bool(self.input_quality["trusted_for_accuracy"])
        return True


@dataclass(frozen=True)
class ParseResult:
    """MusicXML parseability status."""

    ok: bool
    error: Optional[str] = None


@dataclass(frozen=True)
class MusicXmlCounts:
    """Small structural feature counts for fallback comparison."""

    parts: int = 0
    measures: int = 0
    notes: int = 0
    rests: int = 0
    pitched_notes: int = 0


@dataclass
class EvaluationResult:
    """Evaluation result for a single sample."""

    sample_id: str
    source: str
    input_path: str
    ground_truth_path: str
    output_path: Optional[str]
    status: str
    elapsed_seconds: float
    metrics: dict[str, Any]
    error: Optional[str] = None
    license_notes: Optional[str] = None
    difficulty_tags: list[str] = None
    failure_category: Optional[str] = None
    severity: str = "ok"


@dataclass
class EvaluationSummary:
    """Aggregated evaluation run results."""

    total_samples: int
    completed_samples: int
    failed_samples: int
    results: list[EvaluationResult]
    metric_summaries: dict[str, Any]
    failure_categories: dict[str, int]
    group_summaries: dict[str, dict[str, Any]]
    skipped_samples: int = 0
    run_metadata: dict[str, Any] = field(default_factory=dict)


def load_manifest(manifest_path: Union[Path, str]) -> list[EvaluationSample]:
    """Load local evaluation samples from a JSON manifest."""

    manifest = Path(manifest_path)
    if not manifest.exists():
        raise EvaluationManifestError(f"Manifest not found: {manifest}")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    samples_data = data.get("samples")
    if not isinstance(samples_data, list):
        raise EvaluationManifestError("Manifest must contain a 'samples' list")

    samples: list[EvaluationSample] = []
    for index, item in enumerate(samples_data):
        if not isinstance(item, dict):
            raise EvaluationManifestError(f"Sample {index} must be an object")

        sample_id = str(item.get("id") or f"sample-{index + 1}")
        input_value = item.get("input")
        truth_value = item.get("ground_truth")
        if not input_value:
            raise EvaluationManifestError(f"Sample {sample_id}: missing input")
        if not truth_value:
            raise EvaluationManifestError(f"Sample {sample_id}: missing ground_truth")

        input_path = _resolve_manifest_path(manifest.parent, input_value)
        ground_truth_path = _resolve_manifest_path(manifest.parent, truth_value)

        if not input_path.exists():
            raise EvaluationManifestError(f"Input file not found for {sample_id}: {input_path}")
        if not ground_truth_path.exists():
            raise EvaluationManifestError(
                f"Ground truth file not found for {sample_id}: {ground_truth_path}"
            )

        input_quality = item.get("input_quality")
        if input_quality is not None and not isinstance(input_quality, dict):
            raise EvaluationManifestError(f"Sample {sample_id}: input_quality must be an object")

        samples.append(
            EvaluationSample(
                sample_id=sample_id,
                input_path=input_path,
                ground_truth_path=ground_truth_path,
                source=str(item.get("source") or "local"),
                first_page=_optional_int(item.get("first_page")),
                last_page=_optional_int(item.get("last_page")),
                license_notes=_optional_str(item.get("license_notes") or item.get("license")),
                difficulty_tags=_string_tuple(item.get("difficulty_tags")),
                input_quality=dict(input_quality) if input_quality else {},
            )
        )

    return samples


def parse_musicxml(path: Union[Path, str]) -> ParseResult:
    """Return whether a MusicXML file can be parsed as XML."""

    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        return ParseResult(ok=False, error=str(exc))
    except OSError as exc:
        return ParseResult(ok=False, error=str(exc))
    root_name = _local_name(root.tag)
    if root_name not in {"score-partwise", "score-timewise"}:
        return ParseResult(ok=False, error="Expected MusicXML score-partwise or score-timewise root")
    if root_name == "score-partwise":
        if root.find("part-list") is None:
            return ParseResult(ok=False, error="MusicXML is missing part-list")
        if not root.findall("part"):
            return ParseResult(ok=False, error="MusicXML has no part elements")
        if not any(part.findall("measure") for part in root.findall("part")):
            return ParseResult(ok=False, error="MusicXML has no measures")
    return ParseResult(ok=True)


def count_musicxml(path: Union[Path, str]) -> MusicXmlCounts:
    """Count a small set of MusicXML structures for fallback comparison."""

    root = ET.parse(str(path)).getroot()
    parts = measures = notes = rests = pitched_notes = 0

    for element in root.iter():
        name = _local_name(element.tag)
        if name == "part":
            parts += 1
        elif name == "measure":
            measures += 1
        elif name == "note":
            notes += 1
            if any(_local_name(child.tag) == "rest" for child in element):
                rests += 1
            if any(_local_name(child.tag) == "pitch" for child in element):
                pitched_notes += 1

    return MusicXmlCounts(
        parts=parts,
        measures=measures,
        notes=notes,
        rests=rests,
        pitched_notes=pitched_notes,
    )


def normalized_difference(predicted: int, expected: int) -> float:
    """Return an absolute count difference normalized by the expected count."""

    if expected == 0:
        return float(abs(predicted))
    return abs(predicted - expected) / expected


def compare_musicxml_files(
    predicted_path: Union[Path, str],
    ground_truth_path: Union[Path, str],
    *,
    use_musicdiff: bool = True,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    notes_only_musicdiff: bool = False,
) -> dict[str, Any]:
    """Compare predicted MusicXML against ground truth with robust fallbacks."""

    predicted = Path(predicted_path)
    ground_truth = Path(ground_truth_path)
    gt_for_compare = ground_truth
    gt_page_scope: Optional[dict[str, Any]] = None
    scoped_gt_path: Optional[Path] = None

    if _page_range_is_limited(first_page, last_page) and predicted.exists():
        predicted_parse_probe = parse_musicxml(predicted)
        if predicted_parse_probe.ok:
            predicted_counts = count_musicxml(predicted)
            scoped_gt_path = predicted.parent / "_gt_page_scoped.musicxml"
            try:
                slice_musicxml_leading_measures(
                    ground_truth,
                    scoped_gt_path,
                    measure_count=max(1, predicted_counts.measures),
                )
                gt_for_compare = scoped_gt_path
                gt_page_scope = {
                    "strategy": "leading_measures",
                    "first_page": first_page,
                    "last_page": last_page,
                    "measure_count": predicted_counts.measures,
                    "path": str(scoped_gt_path),
                }
            except Exception as exc:
                logger.warning("Failed to slice ground truth for page scope: %s", exc)
                gt_page_scope = {
                    "strategy": "full_score_fallback",
                    "first_page": first_page,
                    "last_page": last_page,
                    "error": str(exc),
                }

    predicted_parse = parse_musicxml(predicted)
    ground_truth_parse = parse_musicxml(gt_for_compare)

    result: dict[str, Any] = {
        "predicted_parse_ok": predicted_parse.ok,
        "predicted_parse_error": predicted_parse.error,
        "ground_truth_parse_ok": ground_truth_parse.ok,
        "ground_truth_parse_error": ground_truth_parse.error,
        "library_parse_status": "not_run",
        "library_parse_error": None,
        "musicdiff_status": "disabled" if not use_musicdiff else "not_run",
        "musicdiff_omrned": None,
        "musicdiff_text": None,
        "structural_counts": {},
        "structural_differences": {},
        "failure_categories": [],
        "gt_page_scope": gt_page_scope,
    }

    if predicted_parse.ok and ground_truth_parse.ok:
        library_parse = _parse_with_optional_music_library(predicted)
        result["library_parse_status"] = library_parse["status"]
        result["library_parse_error"] = library_parse["error"]
        if library_parse["status"] == "unavailable":
            result["failure_categories"].append("optional_tool_unavailable")
        elif library_parse["status"] == "failed":
            result["failure_categories"].append("parse/import")

        predicted_counts = count_musicxml(predicted)
        truth_counts = count_musicxml(gt_for_compare)
        result["structural_counts"] = {
            "predicted": asdict(predicted_counts),
            "ground_truth": asdict(truth_counts),
        }
        result["structural_differences"] = {
            field: normalized_difference(
                getattr(predicted_counts, field),
                getattr(truth_counts, field),
            )
            for field in MusicXmlCounts.__dataclass_fields__
        }

        if use_musicdiff:
            result.update(_run_musicdiff(predicted, gt_for_compare))
            if notes_only_musicdiff:
                result.update(_run_musicdiff(predicted, gt_for_compare, notes_only=True))
            if result["musicdiff_status"] == "failed":
                result["failure_categories"].append("metric_unavailable")
            elif (
                result["musicdiff_status"] == "completed"
                and _extract_omr_ned(result.get("musicdiff_omrned")) is None
            ):
                result["failure_categories"].append("metric_unavailable")
    elif use_musicdiff:
        result["musicdiff_status"] = "skipped_parse_failed"
    if not predicted_parse.ok:
        result["failure_categories"].append("parse/import")
    if not ground_truth_parse.ok:
        result["failure_categories"].append("ground_truth_parse")

    # Part topology signal for taxonomy / export diagnostics.
    pred_struct = result.get("structural_counts", {}).get("predicted") or {}
    gt_struct = result.get("structural_counts", {}).get("ground_truth") or {}
    if pred_struct and gt_struct:
        result["predicted_parts"] = pred_struct.get("parts")
        result["gt_parts"] = gt_struct.get("parts")
        result["part_collapse"] = bool(
            (gt_struct.get("parts") or 0) > 1
            and (pred_struct.get("parts") or 0) < (gt_struct.get("parts") or 0)
        )

    return result


def _page_range_is_limited(first_page: Optional[int], last_page: Optional[int]) -> bool:
    if first_page is None and last_page is None:
        return False
    if first_page is not None and first_page > 1:
        return True
    if last_page is not None and (first_page is None or last_page >= first_page):
        # Any explicit last_page (including page-1-only manifests) is treated as scoped.
        return True
    return first_page is not None


def slice_musicxml_leading_measures(
    source: Path,
    destination: Path,
    *,
    measure_count: int,
) -> Path:
    """Write a GT slice keeping the first N measures of each part."""

    tree = ET.parse(str(source))
    root = tree.getroot()
    kept = 0
    for element in list(root.iter()):
        if _local_name(element.tag) != "part":
            continue
        measures = [child for child in list(element) if _local_name(child.tag) == "measure"]
        for index, measure in enumerate(measures):
            if index < measure_count:
                measure.set("number", str(index + 1))
                kept += 1
            else:
                element.remove(measure)
    if kept <= 0:
        raise ValueError(f"No measures kept when slicing {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(destination), encoding="UTF-8", xml_declaration=True)
    return destination


def run_evaluation(
    manifest_path: Union[Path, str],
    output_dir: Union[Path, str],
    *,
    limit: Optional[int] = None,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    use_musicdiff: bool = True,
    musescore_path: Optional[Union[Path, str]] = None,
    model_backend: str = "oemer-stock",
    checkpoint_dir: Optional[Union[Path, str]] = None,
    render_dpi: int = 360,
    oemer_timeout_seconds: int = 900,
    oemer_device: str = "auto",
    oemer_quality_profile: str = "quality",
    allow_untrusted_inputs: bool = False,
    force: bool = False,
) -> EvaluationSummary:
    """Run PDF2Muse on manifest samples and write JSON/Markdown reports."""

    samples = load_manifest(manifest_path)
    if limit is not None:
        samples = samples[: max(0, limit)]

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    run_metadata = _build_run_metadata(
        manifest_path=manifest_path,
        model_backend=model_backend,
        checkpoint_dir=checkpoint_dir,
        render_dpi=render_dpi,
        oemer_timeout_seconds=oemer_timeout_seconds,
        oemer_device=oemer_device,
        oemer_quality_profile=oemer_quality_profile,
        allow_untrusted_inputs=allow_untrusted_inputs,
    )
    run_metadata["force"] = force

    results: list[EvaluationResult] = []
    skipped = 0
    for sample in samples:
        if not sample.trusted_for_accuracy and not allow_untrusted_inputs:
            skipped += 1
            logger.warning(
                "Skipping untrusted sample %s (input_quality.trusted_for_accuracy=false); "
                "pass --allow-untrusted-inputs to evaluate",
                sample.sample_id,
            )
            results.append(
                EvaluationResult(
                    sample_id=sample.sample_id,
                    source=sample.source,
                    input_path=str(sample.input_path),
                    ground_truth_path=str(sample.ground_truth_path),
                    output_path=None,
                    status="skipped",
                    elapsed_seconds=0.0,
                    metrics={"skip_reason": "untrusted_input"},
                    error="Sample input_quality.trusted_for_accuracy is false",
                    license_notes=sample.license_notes,
                    difficulty_tags=list(sample.difficulty_tags),
                    failure_category="untrusted_input",
                    severity="warning",
                )
            )
            continue

        started = time.perf_counter()
        sample_output_dir = output_root / _safe_filename(sample.sample_id)
        sample_output_dir.mkdir(parents=True, exist_ok=True)
        error: Optional[str] = None
        output_path: Optional[Path] = None
        metrics: dict[str, Any] = {}
        failure_category: Optional[str] = None
        status = "failed"
        severity = "high"
        sample_first = first_page if first_page is not None else sample.first_page
        sample_last = last_page if last_page is not None else sample.last_page
        effective_dpi = render_dpi

        try:
            if sample.input_path.suffix.lower() != ".pdf":
                raise RuntimeError(
                    "Phase 2 evaluation supports PDF inputs only; wrap image datasets "
                    "as PDFs or add image-direct evaluation in a later phase."
                )

            if not force and _sample_has_successful_conversion(sample_output_dir):
                comparison_path = sample_output_dir / "combined.musicxml"
                logger.info(
                    "Resuming sample %s from existing conversion at %s",
                    sample.sample_id,
                    comparison_path,
                )
                metrics = compare_musicxml_files(
                    comparison_path,
                    sample.ground_truth_path,
                    use_musicdiff=use_musicdiff,
                    first_page=sample_first,
                    last_page=sample_last,
                    notes_only_musicdiff=use_musicdiff,
                )
                metrics["comparison_path"] = str(comparison_path)
                metrics["resumed"] = True
                metrics.update(_check_musescore_import(comparison_path, musescore_path))
                output_path = comparison_path
                error = metrics.get("predicted_parse_error")
                failure_category = _primary_failure_category(metrics, error)
                status = (
                    "failed" if _metrics_are_failed(metrics, failure_category) else "completed"
                )
                severity = _severity_for_result(status, failure_category)
            else:
                metrics, output_path, error, failure_category, status, severity, effective_dpi = (
                    _convert_and_compare_sample(
                        sample=sample,
                        sample_output_dir=sample_output_dir,
                        sample_first=sample_first,
                        sample_last=sample_last,
                        use_musicdiff=use_musicdiff,
                        musescore_path=musescore_path,
                        model_backend=model_backend,
                        checkpoint_dir=checkpoint_dir,
                        render_dpi=render_dpi,
                        oemer_timeout_seconds=oemer_timeout_seconds,
                        oemer_device=oemer_device,
                        oemer_quality_profile=oemer_quality_profile,
                    )
                )
        except Exception as exc:
            output_path = None
            metrics = _metrics_from_pipeline_exception(exc)
            report_failure = _failure_class_from_conversion_report(sample_output_dir)
            if report_failure:
                metrics["failure_class"] = report_failure
                metrics["oemer_failure_class"] = report_failure
            if _is_errno22_error(exc):
                metrics["failure_class"] = metrics.get("failure_class") or "errno22_infra"
                metrics["oemer_failure_class"] = metrics["failure_class"]
            status = "failed"
            error = str(exc)
            failure_category = report_failure or _primary_failure_category(metrics, error)
            severity = _severity_for_result(status, failure_category)

        results.append(
            EvaluationResult(
                sample_id=sample.sample_id,
                source=sample.source,
                input_path=str(sample.input_path),
                ground_truth_path=str(sample.ground_truth_path),
                output_path=str(output_path) if output_path else None,
                status=status,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                metrics=metrics,
                error=error,
                license_notes=sample.license_notes,
                difficulty_tags=list(sample.difficulty_tags),
                failure_category=failure_category,
                severity=severity,
            )
        )

    summary = EvaluationSummary(
        total_samples=len(results),
        completed_samples=sum(1 for item in results if item.status == "completed"),
        failed_samples=sum(1 for item in results if item.status == "failed"),
        skipped_samples=skipped,
        results=results,
        metric_summaries=_summarize_metrics(results),
        failure_categories=_count_failure_categories(results),
        group_summaries=_summarize_groups(results),
        run_metadata=run_metadata,
    )
    _write_json_report(output_root / "evaluation_results.json", summary)
    _write_markdown_report(output_root / "evaluation_summary.md", summary)
    return summary


def _resolve_manifest_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        raise EvaluationManifestError("difficulty_tags must be a list of strings")
    return tuple(str(item) for item in value)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _run_musicdiff(
    predicted: Path,
    ground_truth: Path,
    *,
    notes_only: bool = False,
) -> dict[str, Any]:
    """Compare scores via the musicdiff Python API (CLI -o nargs=* swallows file paths)."""

    if importlib.util.find_spec("musicdiff") is None:
        return {
            "musicdiff_status": "unavailable",
            "musicdiff_text": "No module named musicdiff",
        }

    import io
    from contextlib import redirect_stdout, redirect_stderr

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        from musicdiff import DetailLevel, diff

        detail = DetailLevel.NotesAndRests if notes_only else DetailLevel.Default
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            # predicted first, ground truth second (musicdiff OMR-NED convention).
            cost = diff(
                str(predicted),
                str(ground_truth),
                visualize_diffs=False,
                print_text_output=True,
                print_omr_ned_output=True,
                detail=detail,
            )
    except Exception as exc:
        tool_output = (stderr_buf.getvalue() or str(exc)).strip()
        lowered = tool_output.lower()
        if "no module named musicdiff" in lowered:
            return {
                "musicdiff_status": "unavailable",
                "musicdiff_text": tool_output,
            }
        return {
            "musicdiff_status": "failed",
            "musicdiff_text": tool_output or str(exc),
        }

    stdout = stdout_buf.getvalue().strip()
    stderr = stderr_buf.getvalue().strip()
    if cost is None:
        return {
            "musicdiff_status": "failed",
            "musicdiff_text": stderr or stdout or "musicdiff returned None (parse failure)",
        }

    omrned = _parse_omr_ned_from_text(stdout)
    if omrned is None and isinstance(cost, (int, float)):
        omrned = {"OMR-ED": str(cost), "OMR-NED": None}

    prefix = "notes_only_" if notes_only else ""
    return {
        f"{prefix}musicdiff_status": "completed",
        f"{prefix}musicdiff_text": stdout or stderr,
        f"{prefix}musicdiff_omrned": omrned,
        f"{prefix}musicdiff_edit_cost": cost,
    }


def _parse_omr_ned_from_text(value: str) -> Optional[Any]:
    """Parse the first JSON object in musicdiff stdout (ignore trailing diff braces)."""

    if not value or not value.strip():
        return None
    parsed = _try_parse_json(value)
    if isinstance(parsed, dict) and _extract_omr_ned(parsed) is not None:
        return parsed
    if isinstance(parsed, dict) and any(k in parsed for k in ("OMR-NED", "omr_ned", "omrned", "OMR-ED")):
        # Header object present even if NED key is null — keep it.
        return parsed

    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(value, index)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (
            _extract_omr_ned(obj) is not None
            or any(k in obj for k in ("OMR-NED", "omr_ned", "omrned", "OMR-ED"))
        ):
            return obj
    return None


def _is_errno22_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 22:
        return True
    text = str(exc).lower()
    return "errno 22" in text or "[errno 22]" in text or "invalid argument" in text


def _clear_sample_output_dir(sample_output_dir: Path) -> None:
    """Remove prior artifacts so a retry cannot inherit an empty/corrupt tree."""

    for child in sample_output_dir.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            continue


def _convert_and_compare_sample(
    *,
    sample: EvaluationSample,
    sample_output_dir: Path,
    sample_first: Optional[int],
    sample_last: Optional[int],
    use_musicdiff: bool,
    musescore_path: Optional[Union[Path, str]],
    model_backend: str,
    checkpoint_dir: Optional[Union[Path, str]],
    render_dpi: int,
    oemer_timeout_seconds: int,
    oemer_device: str,
    oemer_quality_profile: str,
) -> tuple[dict[str, Any], Optional[Path], Optional[str], Optional[str], str, str, int]:
    """Run conversion once, with a single Errno-22 / optional DPI retry."""

    from .oemer_worker_client import reset_oemer_workers

    dpi_attempts = [render_dpi]
    if (
        os.environ.get("PDF2MUSE_OEMER_DPI_RETRY") == "1"
        and render_dpi <= 300
        and 360 not in dpi_attempts
    ):
        dpi_attempts.append(360)

    last_exc: Optional[BaseException] = None
    for dpi_index, dpi in enumerate(dpi_attempts):
        attempts = 1 + (1 if dpi_index == 0 else 0)  # one Errno22 retry on first DPI
        for attempt_index in range(attempts):
            try:
                if attempt_index > 0 or dpi_index > 0:
                    reset_oemer_workers()
                    _clear_sample_output_dir(sample_output_dir)
                    sample_output_dir.mkdir(parents=True, exist_ok=True)

                pipeline = PDF2MusePipeline(
                    pdf_path=str(sample.input_path),
                    output_dir=str(sample_output_dir),
                    first_page=sample_first,
                    last_page=sample_last,
                    strict_musicxml=True,
                    model_backend=model_backend,
                    checkpoint_dir=str(checkpoint_dir) if checkpoint_dir else None,
                    render_dpi=dpi,
                    oemer_timeout_seconds=oemer_timeout_seconds,
                    oemer_device=oemer_device,
                    oemer_quality_profile=oemer_quality_profile,
                )
                output_path = pipeline.run()
                comparison_path = sample_output_dir / "combined.musicxml"
                if not comparison_path.exists():
                    comparison_path = Path(output_path)
                metrics = compare_musicxml_files(
                    comparison_path,
                    sample.ground_truth_path,
                    use_musicdiff=use_musicdiff,
                    first_page=sample_first,
                    last_page=sample_last,
                    notes_only_musicdiff=use_musicdiff,
                )
                metrics["comparison_path"] = str(comparison_path)
                metrics["render_dpi_used"] = dpi
                if attempt_index > 0:
                    metrics["errno22_retried"] = True
                if dpi_index > 0:
                    metrics["dpi_retried"] = True
                metrics.update(_check_musescore_import(comparison_path, musescore_path))
                report_failure = _failure_class_from_conversion_report(sample_output_dir)
                if report_failure:
                    metrics["failure_class"] = report_failure
                    metrics["oemer_failure_class"] = report_failure
                error = metrics.get("predicted_parse_error")
                failure_category = _primary_failure_category(metrics, error)
                status = (
                    "failed" if _metrics_are_failed(metrics, failure_category) else "completed"
                )
                severity = _severity_for_result(status, failure_category)

                # Optional DPI retry only when OMR symbol/staffline empties dominate.
                if (
                    status == "failed"
                    and dpi_index + 1 < len(dpi_attempts)
                    and failure_category
                    in {
                        "symbol_extraction_empty_candidates",
                        "symbol_extraction_failed",
                        "staffline_empty_peaks",
                        "staffline_no_candidates",
                    }
                ):
                    last_exc = RuntimeError(f"retryable OMR failure: {failure_category}")
                    continue
                return metrics, output_path, error, failure_category, status, severity, dpi
            except Exception as exc:
                last_exc = exc
                if _is_errno22_error(exc) and attempt_index + 1 < attempts:
                    logger.warning(
                        "Errno 22 on sample %s; resetting worker and retrying once",
                        sample.sample_id,
                    )
                    reset_oemer_workers()
                    continue
                if (
                    dpi_index + 1 < len(dpi_attempts)
                    and _failure_class_from_conversion_report(sample_output_dir)
                    in {
                        "symbol_extraction_empty_candidates",
                        "symbol_extraction_failed",
                        "staffline_empty_peaks",
                        "staffline_no_candidates",
                    }
                ):
                    continue
                raise

    assert last_exc is not None
    raise last_exc


def _try_parse_json(value: str) -> Optional[Any]:
    value = value.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    for line in reversed(value.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _parse_with_optional_music_library(path: Path) -> dict[str, Optional[str]]:
    if importlib.util.find_spec("music21") is None:
        return {"status": "unavailable", "error": None}

    try:
        from music21 import converter  # type: ignore

        converter.parse(str(path))
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "completed", "error": None}


def _check_musescore_import(
    musicxml_path: Path,
    musescore_path: Optional[Union[Path, str]],
) -> dict[str, Optional[str]]:
    if not musescore_path:
        return {
            "musescore_import_status": "not_configured",
            "musescore_import_error": None,
        }

    output_path = musicxml_path.with_suffix(".import-check.mscx")
    command = [str(musescore_path), "-f", "-o", str(output_path), str(musicxml_path)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return {
            "musescore_import_status": "unavailable",
            "musescore_import_error": str(exc),
        }
    except subprocess.CalledProcessError as exc:
        return {
            "musescore_import_status": "failed",
            "musescore_import_error": (exc.stderr or exc.stdout or str(exc)).strip(),
        }

    return {
        "musescore_import_status": "completed",
        "musescore_import_error": None,
    }


def _primary_failure_category(metrics: dict[str, Any], error: Optional[str]) -> Optional[str]:
    failure_class = metrics.get("failure_class") or metrics.get("oemer_failure_class")
    if failure_class:
        return str(failure_class)
    categories = [item for item in metrics.get("failure_categories", []) if item]
    actionable = [item for item in categories if item != "optional_tool_unavailable"]
    if actionable:
        return str(actionable[0])
    if metrics.get("musicdiff_status") == "failed":
        return "metric_unavailable"
    if metrics.get("musescore_import_status") == "failed":
        return "parse/import"
    if error and _looks_like_parse_failure(error):
        return "parse/import"
    if error:
        return "pipeline"
    return None


def _metrics_are_failed(metrics: dict[str, Any], failure_category: Optional[str]) -> bool:
    if metrics.get("predicted_parse_ok") is False:
        return True
    if metrics.get("ground_truth_parse_ok") is False:
        return True
    if metrics.get("library_parse_status") == "failed":
        return True
    if metrics.get("musescore_import_status") == "failed":
        return True
    if failure_category in {"parse/import", "ground_truth_parse"}:
        return True
    return False


def _metrics_from_pipeline_exception(exc: Exception) -> dict[str, Any]:
    error = str(exc)
    if _looks_like_parse_failure(error):
        return {
            "predicted_parse_ok": False,
            "predicted_parse_error": error,
            "ground_truth_parse_ok": None,
            "ground_truth_parse_error": None,
            "musicdiff_status": "skipped_parse_failed",
            "musicdiff_omrned": None,
            "musicdiff_text": None,
            "structural_counts": {},
            "structural_differences": {},
            "failure_categories": ["parse/import"],
        }
    return {}


def _looks_like_parse_failure(error: str) -> bool:
    lowered = error.lower()
    return (
        "invalid musicxml" in lowered
        or "combined musicxml is invalid" in lowered
        or "parse" in lowered
        or "no element found" in lowered
    )


def _severity_for_result(status: str, failure_category: Optional[str]) -> str:
    if status == "failed":
        return "critical" if failure_category == "parse/import" else "high"
    if failure_category:
        return "warning"
    return "ok"


def _summarize_metrics(results: list[EvaluationResult]) -> dict[str, Any]:
    summary = {
        "predicted_parse_ok": {"passed": 0, "failed": 0},
        "ground_truth_parse_ok": {"passed": 0, "failed": 0},
        "musicdiff_status": {},
        "musescore_import_status": {},
        "omr_ned": {"count": 0, "average": None, "minimum": None, "maximum": None},
        "notes_only_omr_ned": {"count": 0, "average": None, "minimum": None, "maximum": None},
        "part_collapse_samples": 0,
    }
    omr_ned_values: list[float] = []
    notes_only_values: list[float] = []
    for result in results:
        metrics = result.metrics
        for key in ("predicted_parse_ok", "ground_truth_parse_ok"):
            if metrics.get(key) is True:
                summary[key]["passed"] += 1
            elif metrics.get(key) is False:
                summary[key]["failed"] += 1
        for key in ("musicdiff_status", "musescore_import_status"):
            value = str(metrics.get(key, "not_run"))
            summary[key][value] = summary[key].get(value, 0) + 1
        if metrics.get("part_collapse"):
            summary["part_collapse_samples"] += 1
        omr_ned = _ned_from_metrics(metrics)
        if omr_ned is not None:
            omr_ned_values.append(omr_ned)
        notes_only = _extract_omr_ned(metrics.get("notes_only_musicdiff_omrned"))
        if notes_only is None:
            text = metrics.get("notes_only_musicdiff_text")
            if isinstance(text, str):
                notes_only = _extract_omr_ned(_parse_omr_ned_from_text(text))
        if notes_only is not None:
            notes_only_values.append(notes_only)
    if omr_ned_values:
        summary["omr_ned"] = {
            "count": len(omr_ned_values),
            "average": sum(omr_ned_values) / len(omr_ned_values),
            "minimum": min(omr_ned_values),
            "maximum": max(omr_ned_values),
        }
    if notes_only_values:
        summary["notes_only_omr_ned"] = {
            "count": len(notes_only_values),
            "average": sum(notes_only_values) / len(notes_only_values),
            "minimum": min(notes_only_values),
            "maximum": max(notes_only_values),
        }
    return summary


def _ned_from_metrics(metrics: dict[str, Any]) -> Optional[float]:
    omr_ned = _extract_omr_ned(metrics.get("musicdiff_omrned"))
    if omr_ned is not None:
        return omr_ned
    text = metrics.get("musicdiff_text")
    if isinstance(text, str):
        return _extract_omr_ned(_parse_omr_ned_from_text(text))
    return None


def _extract_omr_ned(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            recovered = _parse_omr_ned_from_text(value)
            return _extract_omr_ned(recovered) if recovered is not None else None
    if not isinstance(value, dict):
        return None
    for key in ("omr_ned", "omrned", "OMR-NED"):
        if key not in value:
            continue
        raw = value[key]
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _count_failure_categories(results: list[EvaluationResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if not result.failure_category:
            continue
        counts[result.failure_category] = counts.get(result.failure_category, 0) + 1
    return counts


def _summarize_groups(results: list[EvaluationResult]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {"source": {}, "difficulty_tags": {}}
    for result in results:
        _add_group_result(summaries["source"], result.source, result)
        for tag in result.difficulty_tags or []:
            _add_group_result(summaries["difficulty_tags"], tag, result)
    return summaries


def _add_group_result(groups: dict[str, Any], key: str, result: EvaluationResult) -> None:
    group = groups.setdefault(
        key or "unspecified",
        {
            "total_samples": 0,
            "completed_samples": 0,
            "failed_samples": 0,
            "skipped_samples": 0,
            "omr_ned_values": [],
            "structural_delta_notes": [],
            "structural_delta_measures": [],
            "structural_delta_parts": [],
        },
    )
    group["total_samples"] += 1
    if result.status == "completed":
        group["completed_samples"] += 1
        omr_ned = _extract_omr_ned(result.metrics.get("musicdiff_omrned"))
        if omr_ned is not None:
            group["omr_ned_values"].append(omr_ned)
        deltas = result.metrics.get("structural_differences") or {}
        for field_name, bucket in (
            ("notes", "structural_delta_notes"),
            ("measures", "structural_delta_measures"),
            ("parts", "structural_delta_parts"),
        ):
            value = deltas.get(field_name)
            if isinstance(value, (int, float)):
                group[bucket].append(float(value))
    elif result.status == "skipped":
        group["skipped_samples"] += 1
    elif result.status == "failed":
        group["failed_samples"] += 1
    if group["omr_ned_values"]:
        values = group["omr_ned_values"]
        group["omr_ned_median"] = sorted(values)[len(values) // 2]
        group["omr_ned_average"] = sum(values) / len(values)
    for bucket, median_key, average_key in (
        ("structural_delta_notes", "structural_delta_notes_median", "structural_delta_notes_average"),
        (
            "structural_delta_measures",
            "structural_delta_measures_median",
            "structural_delta_measures_average",
        ),
        ("structural_delta_parts", "structural_delta_parts_median", "structural_delta_parts_average"),
    ):
        values = group.get(bucket) or []
        if values:
            group[median_key] = sorted(values)[len(values) // 2]
            group[average_key] = sum(values) / len(values)


def _format_group_line(name: str, group: dict[str, Any]) -> str:
    parts = [f"{name}: {group['completed_samples']}/{group['total_samples']} completed"]
    if group.get("omr_ned_median") is not None:
        parts.append(f"OMR-NED median={group['omr_ned_median']:.4f}")
    if group.get("structural_delta_notes_median") is not None:
        parts.append(f"notesΔ median={group['structural_delta_notes_median']:.3f}")
    if group.get("structural_delta_measures_median") is not None:
        parts.append(f"measuresΔ median={group['structural_delta_measures_median']:.3f}")
    return "- " + "; ".join(parts)


def _failure_class_from_conversion_report(sample_output_dir: Path) -> Optional[str]:
    report_path = sample_output_dir / "conversion_report.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for page in report.get("pages", []):
        for attempt in page.get("attempts", []):
            failure_class = attempt.get("failure_class")
            if failure_class:
                return str(failure_class)
    return None


def _sample_has_successful_conversion(sample_output_dir: Path) -> bool:
    """True when a prior run left parseable combined MusicXML marked OK."""

    musicxml = sample_output_dir / "combined.musicxml"
    if not musicxml.exists() or musicxml.stat().st_size <= 0:
        return False
    parsed = parse_musicxml(musicxml)
    if not parsed.ok:
        return False
    report_path = sample_output_dir / "conversion_report.json"
    if not report_path.exists():
        return True
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    final_status = (report.get("final_musicxml") or {}).get("status")
    if final_status in {None, "ok"}:
        return True
    join_status = (report.get("join") or {}).get("status")
    return join_status == "ok"


def _build_run_metadata(
    *,
    manifest_path: Union[Path, str],
    model_backend: str,
    checkpoint_dir: Optional[Union[Path, str]],
    render_dpi: int,
    oemer_timeout_seconds: int,
    oemer_device: str,
    oemer_quality_profile: str,
    allow_untrusted_inputs: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "manifest_path": str(Path(manifest_path).resolve()),
        "model_backend": model_backend,
        "checkpoint_dir": str(checkpoint_dir) if checkpoint_dir else None,
        "render_dpi": render_dpi,
        "oemer_timeout_seconds": oemer_timeout_seconds,
        "oemer_device": oemer_device,
        "oemer_quality_profile": oemer_quality_profile,
        "allow_untrusted_inputs": allow_untrusted_inputs,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        if completed.returncode == 0:
            metadata["git_commit"] = completed.stdout.strip()
    except (FileNotFoundError, OSError):
        pass
    return metadata


def _write_json_report(path: Path, summary: EvaluationSummary) -> None:
    path.write_text(
        json.dumps(asdict(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_markdown_report(path: Path, summary: EvaluationSummary) -> None:
    lines = [
        "# PDF2Muse Evaluation Summary",
        "",
        f"- Total samples: {summary.total_samples}",
        f"- Completed samples: {summary.completed_samples}",
        f"- Failed samples: {summary.failed_samples}",
        f"- Skipped samples: {summary.skipped_samples}",
        "",
        "## Metric Summary",
        "",
        f"- Predicted XML parse passed: {summary.metric_summaries['predicted_parse_ok']['passed']}",
        f"- Predicted XML parse failed: {summary.metric_summaries['predicted_parse_ok']['failed']}",
        f"- Musicdiff statuses: {summary.metric_summaries['musicdiff_status']}",
        f"- OMR-NED samples: {summary.metric_summaries['omr_ned']['count']}",
        f"- MuseScore import statuses: {summary.metric_summaries['musescore_import_status']}",
        "",
        "## Failure Categories",
        "",
    ]
    if summary.failure_categories:
        for category, count in sorted(summary.failure_categories.items()):
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Grouped Results",
            "",
            "### By Source",
            "",
        ]
    )
    for source, group in sorted(summary.group_summaries["source"].items()):
        lines.append(_format_group_line(source, group))
    lines.extend(["", "### By Difficulty Tag", ""])
    for tag, group in sorted(summary.group_summaries["difficulty_tags"].items()):
        lines.append(_format_group_line(tag, group))

    lines.extend(
        [
            "",
            "## Ranked Samples",
            "",
            "| Sample | Severity | Category | Status | Error |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    severity_order = {"critical": 0, "high": 1, "warning": 2, "ok": 3}
    for result in sorted(results := summary.results, key=lambda item: severity_order[item.severity]):
        error = (result.error or "").replace("|", "\\|")
        category = result.failure_category or ""
        lines.append(
            f"| `{result.sample_id}` | {result.severity} | {category} | {result.status} | {error} |"
        )

    lines.extend(
        [
            "",
        "## Samples",
        "",
            "| Sample | Source | Tags | License Notes | Status | Error |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for result in summary.results:
        error = (result.error or "").replace("|", "\\|")
        license_notes = (result.license_notes or "").replace("|", "\\|")
        tags = ", ".join(result.difficulty_tags or [])
        lines.append(
            f"| `{result.sample_id}` | {result.source} | {tags} | "
            f"{license_notes} | {result.status} | {error} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return safe or "sample"
