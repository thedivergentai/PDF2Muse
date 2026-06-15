"""Experimental evaluation helpers for PDF2Muse OMR output."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Union

from .core import PDF2MusePipeline


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


@dataclass
class EvaluationSummary:
    """Aggregated evaluation run results."""

    total_samples: int
    completed_samples: int
    failed_samples: int
    results: list[EvaluationResult]


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

        samples.append(
            EvaluationSample(
                sample_id=sample_id,
                input_path=input_path,
                ground_truth_path=ground_truth_path,
                source=str(item.get("source") or "local"),
                first_page=_optional_int(item.get("first_page")),
                last_page=_optional_int(item.get("last_page")),
            )
        )

    return samples


def parse_musicxml(path: Union[Path, str]) -> ParseResult:
    """Return whether a MusicXML file can be parsed as XML."""

    try:
        ET.parse(str(path))
    except ET.ParseError as exc:
        return ParseResult(ok=False, error=str(exc))
    except OSError as exc:
        return ParseResult(ok=False, error=str(exc))
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
) -> dict[str, Any]:
    """Compare predicted MusicXML against ground truth with robust fallbacks."""

    predicted = Path(predicted_path)
    ground_truth = Path(ground_truth_path)
    predicted_parse = parse_musicxml(predicted)
    ground_truth_parse = parse_musicxml(ground_truth)

    result: dict[str, Any] = {
        "predicted_parse_ok": predicted_parse.ok,
        "predicted_parse_error": predicted_parse.error,
        "ground_truth_parse_ok": ground_truth_parse.ok,
        "ground_truth_parse_error": ground_truth_parse.error,
        "musicdiff_status": "disabled" if not use_musicdiff else "not_run",
        "musicdiff_omrned": None,
        "musicdiff_text": None,
        "structural_counts": {},
        "structural_differences": {},
    }

    if predicted_parse.ok and ground_truth_parse.ok:
        predicted_counts = count_musicxml(predicted)
        truth_counts = count_musicxml(ground_truth)
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
            result.update(_run_musicdiff(predicted, ground_truth))
    elif use_musicdiff:
        result["musicdiff_status"] = "skipped_parse_failed"

    return result


def run_evaluation(
    manifest_path: Union[Path, str],
    output_dir: Union[Path, str],
    *,
    limit: Optional[int] = None,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    use_musicdiff: bool = True,
) -> EvaluationSummary:
    """Run PDF2Muse on manifest samples and write JSON/Markdown reports."""

    samples = load_manifest(manifest_path)
    if limit is not None:
        samples = samples[: max(0, limit)]

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    results: list[EvaluationResult] = []
    for sample in samples:
        started = time.perf_counter()
        sample_output_dir = output_root / _safe_filename(sample.sample_id)
        sample_output_dir.mkdir(parents=True, exist_ok=True)

        try:
            if sample.input_path.suffix.lower() != ".pdf":
                raise RuntimeError(
                    "Phase 2 evaluation supports PDF inputs only; wrap image datasets "
                    "as PDFs or add image-direct evaluation in a later phase."
                )

            pipeline = PDF2MusePipeline(
                pdf_path=str(sample.input_path),
                output_dir=str(sample_output_dir),
                first_page=first_page if first_page is not None else sample.first_page,
                last_page=last_page if last_page is not None else sample.last_page,
            )
            output_path = pipeline.run()
            comparison_path = sample_output_dir / "combined.musicxml"
            if not comparison_path.exists():
                comparison_path = Path(output_path)
            metrics = compare_musicxml_files(
                comparison_path,
                sample.ground_truth_path,
                use_musicdiff=use_musicdiff,
            )
            metrics["comparison_path"] = str(comparison_path)
            status = "completed" if metrics["predicted_parse_ok"] else "failed"
            error = metrics.get("predicted_parse_error")
        except Exception as exc:
            output_path = None
            metrics = {}
            status = "failed"
            error = str(exc)

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
            )
        )

    summary = EvaluationSummary(
        total_samples=len(results),
        completed_samples=sum(1 for item in results if item.status == "completed"),
        failed_samples=sum(1 for item in results if item.status == "failed"),
        results=results,
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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _run_musicdiff(predicted: Path, ground_truth: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "musicdiff",
        "-o",
        "omrned",
        "text",
        str(predicted),
        str(ground_truth),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {"musicdiff_status": "unavailable"}
    except subprocess.CalledProcessError as exc:
        tool_output = (exc.stderr or exc.stdout or "").strip()
        lowered_output = tool_output.lower()
        if "no module named musicdiff" in lowered_output or "not found" in lowered_output:
            return {
                "musicdiff_status": "unavailable",
                "musicdiff_text": tool_output,
            }
        return {
            "musicdiff_status": "failed",
            "musicdiff_text": tool_output,
        }

    stdout = completed.stdout.strip()
    return {
        "musicdiff_status": "completed",
        "musicdiff_text": stdout,
        "musicdiff_omrned": _try_parse_json(stdout),
    }


def _try_parse_json(value: str) -> Optional[Any]:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


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
        "",
        "## Samples",
        "",
        "| Sample | Source | Status | Error |",
        "| --- | --- | --- | --- |",
    ]
    for result in summary.results:
        error = (result.error or "").replace("|", "\\|")
        lines.append(
            f"| `{result.sample_id}` | {result.source} | {result.status} | {error} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in value)
    return safe or "sample"
