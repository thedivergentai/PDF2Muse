# Pipeline Hardening and MusicXML Gates

## 5-Bullet Summary

- Add lightweight MusicXML gates in the conversion path: per-page parseability after `oemer`, join-time structural checks, and final combined-output validation before MuseScore export or user download.
- Treat malformed MusicXML as a failed page, not as a successful OMR result; preserve page-level error messages so CLI/UI users can see whether failures came from OMR, XML parsing, joining, or MuseScore export.
- Make `join_musicxml_files()` fail loudly when no valid inputs remain or when the combined output is not parseable, instead of silently returning or skipping parse failures without a machine-readable result.
- Keep quality gates separate from benchmark scoring: reuse the evaluation module's parse/count patterns for production safety checks, but leave ground-truth comparison, `musicdiff`, and reports in `pdf2muse.evaluation`.
- Preserve MusicXML as the primary output and MuseScore `.mscx` as an optional export; MuseScore failures should remain fallback warnings only after the combined MusicXML has passed the gate.

## Files/Symbols Involved

- `src/pdf2muse/core.py`: `PDF2MusePipeline.process_image_with_oemer()`, `PDF2MusePipeline.run()`.
- `src/pdf2muse/musicxml.py`: `join_musicxml_files()`, `convert_to_musescore_format()`, proposed `validate_musicxml_file()` / `MusicXmlValidationResult`.
- `src/pdf2muse/ui.py`: `_orchestrate_pipeline()`, `convert_pdf()`, `convert_batch_pdfs()` should use the same gates as CLI conversion.
- `src/pdf2muse/evaluation.py`: `parse_musicxml()`, `count_musicxml()`, `MusicXmlCounts` provide patterns to reuse or extract without importing benchmark orchestration into production conversion.
- `tests/test_pipeline.py`, `tests/test_ui.py`, `tests/test_evaluation.py`: current coverage already mocks OMR and MuseScore paths; new tests should target validation outcomes and user-visible failure modes.

## Recommended Implementation Details

Add a small production-facing validation helper in `musicxml.py`, returning a typed result with `ok`, `error`, and structural counts for parts, measures, notes, rests, and pitched notes. It should use `xml.etree.ElementTree`, handle namespaces via local-name matching, reject malformed XML, reject roots that are not MusicXML-like score documents, and reject outputs with no `part` or no `measure`. Avoid `musicdiff` and ground-truth metrics in this helper.

Call the helper at three points. First, in `process_image_with_oemer()`, validate the copied per-page `.musicxml` before returning it; return `(None, "...")` with the parse or structural error when it fails. Second, in `join_musicxml_files()`, validate each candidate before joining, skip invalid non-base pages only if the caller has opted into partial results, and return or raise structured information about skipped files. Third, after writing `combined.musicxml`, validate it before calling `convert_to_musescore_format()` or exposing it in UI downloads.

Harden `join_musicxml_files()` so it no longer silently returns when there are no inputs. Prefer raising `RuntimeError` or a domain-specific `MusicXmlGateError` for no inputs, invalid first input, all inputs invalid, or combined output invalid. If partial conversion remains allowed, make it explicit through a flag such as `allow_partial_pages=True` and include counts like `pages_rendered`, `pages_omr_ok`, `pages_xml_valid`, and `pages_joined` in logs or returned metadata.

Unify CLI and UI orchestration around the same gate behavior. Today `PDF2MusePipeline.run()` and `ui._orchestrate_pipeline()` duplicate the same processing stages, so a shared internal method or result object would reduce drift. At minimum, both paths should call the same `musicxml.py` validation helper and surface the same page failure categories.

Keep MuseScore export as a post-gate optional conversion. `convert_to_musescore_format()` should still raise on missing binaries or CLI failures, and callers can continue falling back to `combined.musicxml`; however, fallback should happen only for MuseScore problems, not for invalid MusicXML.

## Tests to Add

- `tests/test_pipeline.py`: `process_image_with_oemer()` returns an error when `oemer` writes malformed XML, empty XML, or structurally empty MusicXML.
- `tests/test_pipeline.py`: `PDF2MusePipeline.run()` fails when some pages produce invalid MusicXML under strict behavior, and reports all page-level OMR/XML errors when no valid pages remain.
- `tests/test_pipeline.py`: `join_musicxml_files()` raises on an empty directory, invalid first file, all invalid files, and invalid combined output; it preserves page order for valid files.
- `tests/test_ui.py`: `_orchestrate_pipeline()` surfaces validation failures instead of offering downloads for malformed `combined.musicxml`.
- `tests/test_evaluation.py` or a new focused MusicXML test file: validation helper handles namespaces, valid minimal `score-partwise`, parse errors, missing parts, and missing measures.

## Risks

- Stricter gates may turn current partial conversions into failures; this is safer for quality reporting but could surprise users who currently receive a best-effort file.
- A minimal structural gate cannot prove musical correctness; it only prevents malformed or clearly empty MusicXML from being treated as successful output.
- Duplicated CLI/UI orchestration increases the chance one path enforces gates differently unless the implementation centralizes the shared stages.
- Namespace and MusicXML variant handling needs care so valid `score-timewise` or namespaced files are not rejected accidentally.
- Evaluation helpers are tempting to reuse directly, but production gates should stay lightweight and avoid importing benchmark-only dependencies or report semantics.
