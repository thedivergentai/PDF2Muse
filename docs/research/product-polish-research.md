# Product Polish Research: Quality Status

## 5-Bullet Summary

- The README already sets the right expectation: PDF2Muse is an early revived project, output is not quality-proven, and generated notation needs human review.
- The CLI help, command docstrings, package description, and Web UI header still read more like a straightforward converter than an experimental OMR tool with draft-quality output.
- The Web UI has useful status affordances, diagnostics, and MuseScore fallback language, but success states should explicitly say MusicXML/MuseScore outputs are drafts to inspect, not validated transcriptions.
- The strongest low-risk polish path is to centralize honest quality wording and reuse it in CLI help, UI intro/status cards, diagnostics, README/package metadata, and release-facing docs.
- Focused tests should assert that CLI help and UI status copy include the experimental/no-measured-accuracy/human-review message so future polish does not drift into unsupported claims.

## CLI Status Recommendations

- In `src/pdf2muse/cli.py`, update the Typer app help from "Convert PDF sheet music to MusicXML and MuseScore formats" to measured wording such as "Experimentally convert PDF sheet music to draft MusicXML, with optional MuseScore export."
- Add a short quality note to the root CLI help and `convert` command docstring: "PDF2Muse output is not quality-proven yet; inspect generated notation in notation software before use."
- Keep `evaluate` and `degrade` explicitly marked experimental. Their current language is already close to the desired stance and should remain separated from normal conversion.
- Consider printing a one-time quality notice at the start or end of `convert`, especially after successful output generation. This should be informational, not an error or warning that implies conversion failed.
- Keep MuseScore language as optional convenience: MusicXML is the primary output, while `.mscx` depends on a detected or configured MuseScore CLI.

## UI Status Recommendations

- In `src/pdf2muse/ui.py`, revise the header tagline so it does not imply polished conversion. Prefer "Create draft MusicXML from scanned PDF sheet music using experimental OMR."
- Update `_md_success()` to say the files are ready for review, not just ready for download. Example: "MusicXML is ready below. Treat it as a draft and inspect it in notation software before musical use."
- Add a persistent "Quality status" or "What to expect" card near the existing system preparation and recognition quality cards. It should mention no published accuracy numbers, likely failure modes, and human review.
- Rename "Peak recognition quality" to a less certain heading such as "Input tips for better drafts" or "Improve recognition chances." The current heading plus "higher OMR accuracy" is directionally useful but too confident for an unevaluated tool.
- In `run_diagnostics()`, keep dependency checks separate from transcription quality. A passing environment should not be interpreted as validated recognition quality; add a line to that effect if diagnostics become more user-facing.

## Honest Claim Wording

Recommended short claims:

- "Experimental PDF-to-MusicXML conversion for scanned sheet music."
- "Creates draft MusicXML that should be reviewed in notation software."
- "MuseScore `.mscx` export is optional and depends on the MuseScore CLI."
- "No measured accuracy numbers are published yet; evaluation work is ongoing."
- "Works best, when it works, on clean printed Western staff notation."

Avoid or soften:

- Avoid "editable MusicXML and MuseScore files" without "draft" or "review" context.
- Avoid "AI-powered" as the main trust signal; use "open-source OMR" or "oemer-backed OMR" when specificity helps.
- Avoid "best results," "peak recognition quality," "higher accuracy," or "reliable" unless paired with clear limits.
- Avoid package metadata that suggests beta-quality end-user reliability if evaluation reports do not yet support it.

## Key Files And Symbols

- `README.md`: strongest current source of honest status language, especially "Project Status," "What To Expect," and "Troubleshooting."
- `src/pdf2muse/cli.py`: `app` help text, `main()`, `convert()`, `evaluate()`, `degrade()`, and `ui()` are the main CLI-facing copy surfaces.
- `src/pdf2muse/ui.py`: `_md_loading()`, `_md_success()`, `run_diagnostics()`, `download_checkpoints_ui()`, and `create_interface()` define most user-facing UI text.
- `src/pdf2muse/core.py`: `PDF2MusePipeline.run()` may be the right place for pipeline-level success messaging if CLI output is currently mostly delegated there.
- `src/pdf2muse/musicxml.py`: `convert_to_musescore_format()` and `find_musescore_binary()` support optional `.mscx` messaging.
- `pyproject.toml`: `description` and `classifiers` are package-facing claims; "Development Status :: 4 - Beta" may overstate quality for an early revived OMR project.
- `tests/test_cli.py`: existing CLI help and delegation tests are the natural place to assert status wording.
- `tests/test_ui.py`: existing UI handler tests are the natural place to assert success, missing-input, diagnostics, and interface copy.

## Tests To Add

- Add a CLI help test that root help includes "experimental" or "draft" plus "MusicXML" so the quality status appears before users run commands.
- Add a `convert --help` test that asserts human-review language or "not quality-proven" appears in command help.
- Add a UI `_md_success()` or `convert_pdf()` success-path test that asserts the final status says outputs are ready for review, not just ready for download.
- Add a `run_diagnostics()` test that dependency pass/fail language does not imply recognition accuracy has been validated.
- Add a `create_interface()` smoke/content test, if practical with Gradio internals, that checks the persistent quality-status card exists in the rendered Blocks configuration or generated HTML string.
- Add a package metadata check, if metadata is generated in tests, to keep `pyproject.toml` description and classifier aligned with early/experimental status.
