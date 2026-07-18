# Pipeline Hardening and MusicXML Quality Gates Research

## 5-Bullet Summary

- Add lightweight MusicXML gates inside the production conversion path at page-output, combined-output, and optional MuseScore-export boundaries; keep benchmark scoring in `pdf2muse.evaluation`.
- Promote XML parseability from an evaluation-only concern into a shared `musicxml` utility so `PDF2MusePipeline` and the Gradio UI can reject malformed generated files before joining or offering downloads.
- Make partial-page success explicit: today failed pages are collected only for total failure, so a conversion can silently produce an incomplete score when at least one page succeeds.
- Treat MuseScore conversion as a second quality gate, not just an export convenience: the pipeline should keep MusicXML as the primary fallback but record/import-check failures clearly.
- Add focused unit tests using mocked OMR and MuseScore subprocesses before attempting slow end-to-end OMR cases; reserve dataset-level quality thresholds for the evaluation harness.

## Current Pipeline Observations

- `PDF2MusePipeline.run()` renders PDF pages, runs OMR concurrently, joins page MusicXML files, then tries `.mscx` export with `convert_to_musescore_format()`.
- `PDF2MusePipeline.process_image_with_oemer()` checks only that at least one `*.musicxml` file exists in the per-page OMR directory; it does not parse or structurally inspect the file before returning success.
- `join_musicxml_files()` parses the first MusicXML file without catching parse errors, but skips parse failures for later files. This creates asymmetric behavior: malformed first page aborts, malformed later pages are silently omitted except for a console warning.
- `PDF2MusePipeline.run()` raises if no pages generate MusicXML, but does not surface a warning or failure status when some pages fail and others succeed.
- `src/pdf2muse/evaluation.py` already contains reusable concepts for `parse_musicxml()`, `count_musicxml()`, `compare_musicxml_files()`, optional `musicdiff`, and report-level parse status, but those helpers currently live in the evaluation boundary.
- The UI duplicates much of `PDF2MusePipeline.run()` orchestration in `_orchestrate_pipeline()`, so quality-gate behavior should either be shared at utility level or centralized before adding UI-specific checks.

## Specific Implementation Recommendations

1. Introduce shared MusicXML validation primitives in `src/pdf2muse/musicxml.py`.
   - Move or mirror the evaluation XML parse helper as `validate_musicxml_parse(path: Path) -> MusicXmlValidationResult`.
   - Keep the first version intentionally lightweight: file exists, non-empty, XML parseable, root local name is `score-partwise` or another explicitly supported MusicXML root.
   - Avoid `music21` or `converter21` in the production path unless the dependency is optional and failures are reported as unavailable rather than fatal.

2. Validate each page output before marking OMR success.
   - In `PDF2MusePipeline.process_image_with_oemer()`, after selecting `actual_file`, parse it before copying/returning.
   - Return `(None, "Invalid MusicXML for page_000.png: ...")` for malformed output so the existing `page_errors` path can collect it.
   - This catches the common bad case earlier than `join_musicxml_files()` and avoids joining partial corrupt data.

3. Replace implicit partial success with an explicit policy.
   - Add an internal `page_success_count`, `page_failure_count`, and `page_errors` summary after OMR completion.
   - Default behavior can remain permissive for now to avoid breaking current CLI/UI users, but the console/UI should state that the output is partial when any page failed.
   - Later CLI flags could expose `--strict-pages/--allow-partial` if product requirements need hard failures.

4. Harden `join_musicxml_files()` around deterministic failure reporting.
   - Parse and validate every candidate, including the first, before mutating the combined tree.
   - Return or raise a structured result for skipped files instead of only printing warnings.
   - Preserve page order by using the existing sorted filenames, but gate on validated page files only.

5. Validate the combined MusicXML before MuseScore export and before returning a final path.
   - After `join_musicxml_files()`, parse the combined file and ensure it contains at least one part, measure, and note/rest structure.
   - If combined validation fails, raise a clear `RuntimeError` rather than attempting MuseScore export.
   - Keep `.musicxml` as the fallback when MuseScore is unavailable, but do not call malformed XML a successful conversion.

6. Treat MuseScore CLI conversion as an import/export quality signal.
   - `convert_to_musescore_format()` should continue to raise when MuseScore is missing or fails.
   - Pipeline/UI should distinguish missing MuseScore from import failure due to invalid MusicXML where possible, because missing MuseScore is an environment limitation while import failure is an output-quality gate.
   - Evaluation can record this as `musescore_import_status`; production can surface a concise warning without requiring MuseScore for success.

7. Keep benchmark scoring separate from conversion gates.
   - Do not add `musicdiff`, ground-truth comparisons, or dataset threshold enforcement to `PDF2MusePipeline.run()`.
   - Continue to use `run_evaluation()` for structural differences, OMR-NED, grouped reports, and dataset-driven pass/fail decisions.

## Key Files and Symbols

- `src/pdf2muse/core.py`
  - `PDF2MusePipeline`
  - `PDF2MusePipeline.process_image_with_oemer()`
  - `PDF2MusePipeline.run()`
- `src/pdf2muse/musicxml.py`
  - `join_musicxml_files()`
  - `convert_to_musescore_format()`
  - `find_musescore_binary()`
- `src/pdf2muse/evaluation.py`
  - `ParseResult`
  - `parse_musicxml()`
  - `MusicXmlCounts`
  - `count_musicxml()`
  - `compare_musicxml_files()`
  - `run_evaluation()`
- `src/pdf2muse/ui.py`
  - `_orchestrate_pipeline()`
  - `convert_pdf()`
  - batch conversion flow that mirrors the core pipeline
- `tests/test_pipeline.py`
  - `test_process_image_with_oemer()`
  - `test_join_musicxml_files()`
  - `test_pipeline_run_success()`
  - `test_pipeline_run_fallback_if_musescore_missing()`
- `tests/test_evaluation.py`
  - `test_parse_musicxml_reports_valid_and_malformed()`
  - `test_count_musicxml_collects_structural_counts()`
  - `test_run_evaluation_compares_combined_musicxml_when_mscx_is_primary()`

## Test Cases To Add

- `test_process_image_with_oemer_rejects_malformed_musicxml`: mock OMR to write a malformed `page_000.musicxml`; assert the method returns no path and a validation error.
- `test_process_image_with_oemer_rejects_empty_musicxml`: mock OMR to write an empty file; assert it is treated as invalid rather than successful.
- `test_join_musicxml_files_reports_invalid_first_file`: put malformed `001.musicxml` before valid `002.musicxml`; assert deterministic failure or structured skipped-file reporting instead of an uncaught parse crash.
- `test_join_musicxml_files_skips_or_reports_invalid_later_file`: preserve current permissive behavior if chosen, but assert the skipped file is visible to callers.
- `test_pipeline_run_reports_partial_page_failures`: mock two rendered pages where one returns valid MusicXML and one returns an error; assert the result is marked partial or warns through the chosen result/status mechanism.
- `test_pipeline_run_fails_when_combined_musicxml_invalid`: mock `join_musicxml_files()` to write malformed combined XML; assert MuseScore conversion is not attempted.
- `test_pipeline_run_validates_combined_musicxml_before_musescore`: assert `convert_to_musescore_format()` is called only after combined validation passes.
- `test_ui_orchestrate_pipeline_surfaces_partial_output`: cover the duplicated UI path so UI users see the same partial-conversion warning as CLI users.
- `test_evaluation_records_musescore_import_failure`: when MuseScore exists but conversion/import fails, assert the evaluation report marks the import gate as failed without hiding parseability results.

## Risks

- Strict validation can turn previously "successful" partial conversions into warnings or failures; introduce policy carefully and document that OMR output still requires human review.
- MusicXML has legal variants and namespace/version differences, so root-name and structure checks should be conservative and namespace-aware.
- `music21`, `converter21`, and `musicdiff` are optional evaluation dependencies; adding them to the production path would increase install weight and platform failure modes.
- The UI and core pipeline currently duplicate orchestration; implementing gates in only one path would create inconsistent CLI/UI behavior.
- Joining per-page MusicXML by appending measures may still produce musically questionable structure even when XML is parseable; parse gates catch corruption, not notation accuracy.
- MuseScore CLI behavior differs by version and platform, so tests should mock subprocess behavior and keep real MuseScore import checks optional/manual.
