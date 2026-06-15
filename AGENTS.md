# PDF2Muse — agent guide

Instructions for AI agents and contributors working in this repository.

## Repository operating principle

PDF2Muse is an early revived OMR project. Be honest about the current quality
limits: do not describe the converter as high-accuracy, production-ready, or
reliably useful until evaluation reports prove those claims.

Prefer measured language in docs, issues, and release notes:

- Say what the tool currently does.
- Say what is experimental.
- Say what still needs evaluation.
- Separate roadmap goals from verified behavior.

## Python virtual environment

### Location

| Layout | Path (from repo root) | Notes |
|--------|------------------------|--------|
| **Primary (this repo)** | `venv/` | Use this when it exists. Not committed to git (see `.gitignore`). |
| **Installer default** | `.venv/` | Created by `install.bat` / `install.sh` if no env exists yet. |

**Always use the project venv** for installs, tests, CLI, and the Web UI. Do not rely on system `python` or a global environment unless the user explicitly asks.

### Activation

**Windows (PowerShell / CMD)**

```powershell
cd <repo-root>
.\venv\Scripts\activate
```

**Windows (without activating — preferred for scripts/agents)**

```powershell
.\venv\Scripts\python.exe -m pytest tests/
.\venv\Scripts\python.exe -m pdf2muse.cli --version
.\venv\Scripts\python.exe -m pdf2muse.cli ui
```

**macOS / Linux**

```bash
source venv/bin/activate
# or
./venv/bin/python -m pytest tests/
```

### Creating or refreshing the environment

If `venv/` is missing:

```powershell
# Windows
python -m venv venv
.\venv\Scripts\pip.exe install -e ".[ui,dev]"
```

```bash
# macOS / Linux
python3 -m venv venv
./venv/bin/pip install -e ".[ui,dev]"
```

Alternatively, run `install.bat` (Windows) or `install.sh` (Unix). Those scripts create **`.venv/`** by default; `run-ui.bat` accepts either `venv\` or `.venv\`.

### Common commands (use venv Python)

| Task | Command |
|------|---------|
| Run tests | `venv\Scripts\python.exe -m pytest tests/ -v` |
| CLI convert | `venv\Scripts\python.exe -m pdf2muse.cli convert <file.pdf> -o output` |
| Web UI | `venv\Scripts\python.exe -m pdf2muse.cli ui` or `run-ui.bat` |
| Download OMR models | `venv\Scripts\python.exe -m pdf2muse.cli download-models` |
| Debug smoke (env check) | `venv\Scripts\python.exe scripts\debug_smoke.py` |

On Unix, replace `venv\Scripts\python.exe` with `venv/bin/python`.

### Package layout

- Source: `src/pdf2muse/`
- Tests: `tests/`
- Editable install (`pip install -e .`) puts `pdf2muse` on the venv’s path; pytest and `python -m pdf2muse.cli` should be run **with venv’s interpreter**, not bare `pytest` from PATH.

### Pitfalls for agents

1. **`run-ui.bat` / `install.bat` mismatch** — This workspace may have `venv/` while fresh installs create `.venv/`. Prefer the directory that exists; `run-ui.bat` checks `venv\` first, then `.venv\`.
2. **PowerShell** — Use `;` instead of `&&` between commands, or invoke `venv\Scripts\python.exe` directly.
3. **Do not** run `pip install` without the venv interpreter (e.g. use `venv\Scripts\pip.exe`, not global `pip`).
4. **OMR runs are slow** — Full PDF conversion can take minutes per page on CPU; use `--first-page` / `--last-page` for quick checks.

## Planning, QA, and commits

For non-trivial work, create or follow an accepted implementation plan before
editing. Keep implementation scoped to the files named by that plan unless new
evidence requires an update.

Before marking a task complete:

1. Run focused tests for the files or behavior changed.
2. Run broader tests when CLI, packaging, core pipeline, UI, or shared helpers
   are touched.
3. Report the exact commands and outcomes.
4. Review the diff for unsupported quality claims, unrelated churn, and
   accidental large artifacts.

Commit changes at the end of a completed, tested plan when the user has
requested or approved committing. Each commit should contain only the files that
belong to that completed plan. Do not bundle unrelated dirty-tree changes.

## Dirty tree safety

Assume unrelated modifications belong to the user. Do not revert or reformat
files outside the current task. If a task must touch a file that already has
unrelated edits, preserve them and stage only the intended changes.

Never commit secrets, raw datasets, generated OMR outputs, downloaded model
checkpoints, or large third-party score files unless the user explicitly asks and
the licensing status is clear.

## Documentation claim standards

Documentation should reflect observed behavior. Avoid terms such as "high
precision", "state-of-the-art", "production-ready", or "fully reliable" unless
the claim is backed by current evaluation results in the repository.

When discussing output quality, remind readers that generated MusicXML/MuseScore
files require human review. Mention that `.mscx` export depends on MuseScore CLI
availability and that MusicXML is the primary fallback output.

## Evaluation work

Keep evaluation code separate from the production conversion pipeline. The core
pipeline should continue to convert PDFs; evaluation modules should own
manifests, metrics, reports, and baseline orchestration.

Dataset guidance:

- Keep raw downloads under ignored local directories.
- Track only small manifests, docs, and legally redistributable fixtures.
- Use tiny curated samples for automated tests.
- Gate slow OMR runs and dataset downloads behind explicit manual commands.
- Record parseability failures as evaluation failures, not skipped cases.

## Project entry points

- **CLI**: `pdf2muse` console script → `pdf2muse.cli:app` (Typer)
- **Pipeline API**: `pdf2muse.core.PDF2MusePipeline`
- **Web UI**: `pdf2muse.ui.create_interface()` via `pdf2muse ui`

## Debug logging (when active)

Session debug logs may be written to `debug-aa02ea.log` at the repo root during instrumented runs. Clear that file before a new debug run; do not delete other `debug-*.log` files from other sessions.
