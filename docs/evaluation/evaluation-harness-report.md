# Evaluation Harness Report

This report describes the intended evaluation harness for PDF2Muse. The harness should stay separate from the conversion pipeline so `PDF2MusePipeline` remains focused on producing output, while evaluation code handles manifests, metrics, and reports.

## Proposed Integration

Add `src/pdf2muse/evaluation.py` with:

- Dataclasses for evaluation cases, metric results, and report summaries.
- A manifest loader for mapping input pages, candidate outputs, references, dataset names, and expected formats.
- Parseability checks for XML and optionally MusicXML.
- Structural metrics for parts, measures, notes, rests, pitches, and normalized count differences.
- Optional `musicdiff` subprocess support when installed.
- Report writing in durable markdown or JSON.
- `run_evaluation` as the public orchestration function.

Add a CLI command in `src/pdf2muse/cli.py` that delegates to `evaluation.run_evaluation`. The CLI should expose manifest path, output report path, optional metric tools, and strict/non-strict behavior for optional dependencies.

Add focused tests:

- `tests/test_evaluation.py` for manifest loading, parseability gates, structural metrics, unavailable optional tools, and report writing.
- `tests/test_cli.py` for the CLI command delegating to the evaluation module with expected arguments.

## Harness Boundaries

Keep conversion and evaluation loosely coupled. The evaluation harness should consume files produced by the pipeline, not become part of conversion. This keeps normal user conversion paths simple and makes benchmark runs reproducible.

## Minimum Viable Report

Each run should record:

- Manifest path and case count.
- Dataset and case identifiers.
- Candidate and reference paths.
- Parseability result.
- Optional external metric result or unavailable status.
- Structural count differences.
- Tool errors that affect evaluation.

## Early QA Strategy

Start with small manifests that use known-good local fixtures. Add public dataset subsets only after licenses and access terms are documented. Treat every score as a regression signal until the metric implementation and dataset assumptions are stable.
