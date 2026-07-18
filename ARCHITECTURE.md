# PDF2Muse architecture (rebuild/vision-v1)

## Layers

1. **Engine** (`src/pdf2muse/`) — Python library and CLI
   - `PDF2MusePipeline` — single orchestration path for CLI, UI, API
   - `adapters/` — pluggable OMR backends (oemer, Legato)
   - `musicxml.py` — gates, music21 join v2, MuseScore export
   - `evaluation.py` — manifest benchmarks (separate from production path)

2. **Sidecar API** (`pdf2muse.api`) — FastAPI on `127.0.0.1:8765`
   - `POST /jobs`, `GET /jobs/{id}`, WebSocket progress
   - Start with `pdf2muse serve-api`

3. **Desktop shell** (`packages/desktop/`) — Tauri 2 + React + OSMD
   - Talks to sidecar; renders `combined.musicxml`

## Backend cascade

`model_backend=auto` selects Legato when GPU + repo are configured, else oemer quality path.

## Quality

- Structural MusicXML gates at page, join, and export
- `conversion_report.json` on every run
- UI Quality Scorecard from report metrics
