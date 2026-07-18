# PDF2Muse Desktop (Tauri + React + OSMD)

Scaffold for the local-first desktop shell described in the rebuild plan.

## Prerequisites

- Node.js 20+
- Rust toolchain (for Tauri builds)
- Python venv with `pip install -e ".[api,ui]"`

## Development

```bash
cd packages/desktop
npm install
npm run dev
```

In another terminal, start the Python sidecar:

```powershell
.\venv\Scripts\python.exe -m uvicorn pdf2muse.api:app --host 127.0.0.1 --port 8765
```

## Tauri

```bash
npm run tauri dev
```

The React app loads MusicXML in **OpenSheetMusicDisplay** after a sidecar job completes.
