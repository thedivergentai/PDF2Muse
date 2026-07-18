# PDF2Muse Revival Documentation Plan

This plan records documentation work for the PDF2Muse beta revival. It is intentionally conservative: the project should describe what works, what is experimental, and what evidence exists without making unsupported accuracy claims.

## README Direction

The README should present PDF2Muse as a revived beta project. It should make MusicXML the primary output story and explain that `.mscx` output requires MuseScore CLI support.

Recommended framing:

- Be clear that PDF-to-music conversion remains experimental and score quality varies by source.
- Avoid claims of high accuracy unless tied to a specific reproducible evaluation report.
- Describe setup through the project virtual environment.
- Show narrow, tested commands for CLI conversion and the web UI.
- Include a signed Divergent AI revival note that explains the maintenance context without overstating stability.

## Agent Guide Direction

The agent guide should remain operational and safety-focused:

- Always use the repository virtual environment for installs, tests, CLI runs, and UI runs.
- Keep edits narrow and aligned with the requested task.
- Preserve dirty-tree safety and never revert user changes without explicit permission.
- Provide tests or QA evidence for substantive changes.
- Commit only after a tested plan and explicit user approval.

## Evaluation Documentation

Evaluation docs should stay separate from marketing and setup docs. The dataset, metric, and harness reports under `docs/evaluation` are the durable place for benchmark assumptions, candidate corpora, and planned harness behavior.

Recommended order:

1. Keep dataset candidate notes current as licenses and access terms are verified.
2. Implement parseability-first evaluation before deeper musical metrics.
3. Add structural fallback metrics for regression visibility.
4. Add optional `musicdiff` or OMR-NED integration when available.
5. Introduce tree edit distance only for small curated excerpts after the baseline harness is stable.

## Documentation Standard

Documentation should be concise, durable, and honest about unknowns. Prefer reproducible commands, explicit dependencies, and named limitations over optimistic prose.
