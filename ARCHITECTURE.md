# PDF2Muse architecture (rebuild/vision-v1)

## Layers

1. **Engine** (`src/pdf2muse/`) — Python library and CLI
   - `PDF2MusePipeline` — single orchestration path for CLI, UI, API
   - `adapters/` — pluggable OMR backends (oemer, HOMR, Legato)
   - `musicxml.py` — gates, music21 join v2, MuseScore export
   - `evaluation.py` — manifest benchmarks (separate from production path)

2. **Sidecar API** (`pdf2muse.api`) — FastAPI on `127.0.0.1:8765`
   - `POST /jobs`, `GET /jobs/{id}`, WebSocket progress
   - Start with `pdf2muse serve-api`

3. **Desktop shell** (`packages/desktop/`) — Tauri 2 + React + OSMD
   - Talks to sidecar; renders `combined.musicxml`

## Backend cascade

`model_backend=auto` selects Legato when `PDF2MUSE_ALLOW_LEGATO_AUTO=1` and GPU + repo are configured; otherwise HOMR when `PDF2MUSE_ALLOW_HOMR_AUTO=1` and `pdf2muse[homr]` is installed; otherwise oemer-stock.

Supported backends: `oemer-stock` (default), `oemer-custom`, `homr` (optional AGPL extra), `legato-experimental`.

## Post-join headers

By default, mid-score key/time/tempo changes are preserved. Pass `--header-lock` to force a single voted header across the score (OMR cleanup for simple scores).

## Quality

- Structural MusicXML gates at page, join, and export
- `conversion_report.json` on every run
- UI Quality Scorecard from report metrics
