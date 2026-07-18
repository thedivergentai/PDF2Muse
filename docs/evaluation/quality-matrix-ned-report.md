# Quality matrix (NED-ranked)

Date: 2026-07-18  
Run: `evaluation/runs/quality-matrix-ned-v1/`  
Manifest: `evaluation/manifests/musescore-com-manual.local.json` (limit 5)  
Device: CUDA, warm worker

## Results

| Cell | Parse | OMR-NED avg |
|------|-------|-------------|
| `dpi360-quality-step128` | 5/5 | **0.576** (winner) |
| `dpi360-balanced-step192` | 5/5 | 0.582 |
| `dpi300-balanced-step128` | 5/5 | 0.584 |
| `dpi300-quality-step128` | 5/5 | 0.600 |
| `dpi300-quality-step192` | 5/5 | 0.600 |

## Decision

- Winner **beats** prior quality@300@128 on this held-out slice (0.576 vs 0.600).
- Locked product defaults: **`render_dpi=360`**, quality profile keeps denser tiling **`step_size=128` / `batch_size=16`**.
- Still **above** the plan target of ≤0.45 OMR-NED — recognition defaults alone do not close the gap.

## Reproduce

```powershell
$env:PDF2MUSE_OEMER_WORKER='1'
.\venv\Scripts\python.exe scripts\quality_matrix.py `
  --manifest evaluation\manifests\musescore-com-manual.local.json `
  --output evaluation\runs\quality-matrix-ned-v1 --limit 5 --oemer-device cuda
```
