# Product Polish Research Note

## 5-Bullet Summary

- The README already sets the right quality posture: early revived project, no measured accuracy yet, MusicXML as primary output, `.mscx` as optional MuseScore-dependent export, and manual review required.
- CLI help in `src/pdf2muse/cli.py` is mostly neutral, but the top-level and command descriptions could better surface that conversion output is experimental and may need notation-editor review.
- UI messaging in `src/pdf2muse/ui.py` is the main overclaim risk: "AI-powered," "best results," "Peak recognition quality," and "higher OMR accuracy" read more polished than the verified quality status supports.
- The UI should add persistent quality-status copy near upload/results areas so users understand generated files are drafts, not validated transcriptions.
- Documentation should preserve the current evidence-first tone and align UI/CLI wording with README sections that explain quality limits and human-review expectations.

## Files / Symbols Involved

- `src/pdf2muse/cli.py`
  - `app = typer.Typer(...)`: top-level help currently says "Convert PDF sheet music to MusicXML and MuseScore formats."
  - `main()`: callback docstring repeats the neutral converter positioning.
  - `convert()`: command docstring describes OMR conversion but does not warn that output quality is experimental.
  - `evaluate()`: already framed as experimental local OMR evaluation.
  - `ui()`: describes the Gradio interface as converting PDFs to MusicXML and MuseScore formats.
- `src/pdf2muse/ui.py`
  - `_md_loading()`: already notes CPU runtime; could also mention draft-quality output during long-running conversion.
  - `_md_success()`: confirms output availability but does not remind users to inspect generated notation.
  - `convert_pdf()` / `convert_batch_pdfs()`: status messages and completion summaries are useful insertion points for review expectations.
  - `run_diagnostics()`: "PASS," "OK," and "READY" refer to environment readiness, not output quality; this distinction should stay explicit.
  - `create_interface()`: header, requirement card, and quality tip card contain the strongest user-facing claim language.
- `README.md`
  - `Project Status`, `What To Expect`, `Quality Roadmap`, and `Troubleshooting` provide good source language for UI/CLI copy.

## Recommended UI / CLI Messaging

- UI header: replace "AI-powered optical music recognition" with measured wording such as "open-source optical music recognition" or "experimental optical music recognition."
- UI upload/status area: add a short persistent note: "Quality status: experimental. Generated MusicXML/MuseScore files are drafts and should be reviewed in notation software."
- UI success state: update `_md_success()` to say downloads are ready and remind users to inspect and correct the score before use.
- UI quality tips: rename "Peak recognition quality" to "Input tips for better draft output" and replace "For higher OMR accuracy" with "For the best chance of usable results."
- CLI help/docstrings: add one concise sentence to `convert` help or epilog-style text: "Output quality is not yet measured; inspect generated notation before using it for performance, teaching, publication, or archival work."

## Docs Updates

- Keep README's conservative project status language as the canonical product-quality statement.
- Add a "Quality status in the UI/CLI" note to user docs or README troubleshooting once implementation changes are made, so UI/CLI wording is not maintained separately from docs.
- Document that diagnostics and checkpoint readiness only confirm environment setup, not transcription quality.
- Keep `.mscx` described as optional convenience export, with MusicXML as the primary fallback when MuseScore is unavailable.
- Avoid adding screenshots or marketing copy that labels the tool as polished, reliable, high-accuracy, or production-ready before evaluation reports support those claims.

## Risks Around Overclaiming

- "AI-powered" can imply modern product-grade model quality; "open-source OMR" or "experimental OMR" better matches the current evidence.
- "Peak recognition quality" and "higher OMR accuracy" imply optimization toward known accuracy, but the project does not publish measured accuracy yet.
- Environment diagnostics can be mistaken for quality diagnostics if "PASS," "OK," and "READY" are not clearly scoped to dependencies and checkpoints.
- Successful file generation can be mistaken for successful transcription; completion messages should separate "files generated" from "score is musically correct."
- Any future release notes, screenshots, package descriptions, or landing-page copy should repeat the README's human-review requirement until reproducible evaluation reports justify stronger claims.
