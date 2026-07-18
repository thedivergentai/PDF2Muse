# Clean-typeset baseline report (v2)

Date: 2026-07-18  
Branch: `rebuild/vision-v1`  
Primary manifests: `evaluation/manifests/clean-typeset-openscore.local.json`, `evaluation/manifests/musescore-com-manual.local.json`  
Fixture smoke: `evaluation/manifests/clean-typeset.local.json`  
Latest run: `evaluation/runs/multi-tier-quality-v1/`

## Configuration

- Pipeline: unified `PDF2MusePipeline.run()` with `oemer_quality_profile=quality`
- Default per-page timeout: **900 seconds**
- Trusted PDF inputs: MuseScore CLI rendering (`input_quality.trusted_for_accuracy: true`)
- Join engine: music21 with etree/single-page fallback (strict join no longer drops valid page XML)
- Structural MusicXML gates: enabled at page, join, and export
- Production default backend: `oemer-stock` (`model_backend=auto` stays on oemer unless `PDF2MUSE_ALLOW_LEGATO_AUTO=1`)
- Device for this run: `cuda` with `PDF2MUSE_OEMER_WORKER=1`

## How to reproduce

```powershell
cd <repo-root>
$env:PDF2MUSE_OEMER_WORKER='1'
.\venv\Scripts\python.exe scripts\multi_tier_eval.py --full-gates --oemer-device cuda `
  --tiers tier0-fixtures tier1a-openscore tier1b-musescore-com `
  --output evaluation\runs\multi-tier-quality-v1
```

## Release gates

| Tier | Manifest | Gate |
|------|----------|------|
| 0 fixtures | `clean-typeset.local.json` | ≥1 sample produces parseable MusicXML |
| 1a OpenScore | `clean-typeset-openscore.local.json` | ≥80% parse success |
| 1b MuseScore.com | `musescore-com-manual.local.json` | ≥80% parse success |

Reports: `evaluation/runs/multi-tier-quality-v1/` and `docs/evaluation/multi-tier-eval-report.md`

## Observed metrics (2026-07-18 CUDA full-gates, `multi-tier-quality-v1`)

| Metric | Target | Observed |
|--------|--------|----------|
| Tier 0 parse success | ≥1 fixture | **3/3 (100%) — gate pass** |
| Tier 1a parse success (OpenScore) | ≥ 80% | **3/3 (100%) — gate pass** |
| Tier 1b parse success (MuseScore.com) | ≥ 80% | **15/15 (100%) — gate pass** |
| Overall release gate | tier0 ∧ tier1 | **pass** |
| musicdiff on completions | completed | tier0 3/3; tier1a 3/3; tier1b 15/15 |
| Avg OMR-NED (musicdiff, re-aggregated) | report only | tier0 **0.221** (n=3); tier1a **0.872** (n=3, recovered); tier1b **0.646** (n=15, 3 recovered) |
| Failure taxonomy (join / errno22 / OMR) | — | **empty** (0 failed samples) |
| NED error buckets (tier1b) | — | see `docs/evaluation/ned-error-taxonomy.md` (mostly `pitch_rhythm`; some `part_collapse`) |

**Release status:** parse gates **met**. Do not read parse rate as note accuracy: tier1b OMR-NED averages ~0.65 after fixing NED aggregation (lower is better; 0 = identical), so generated scores still need human review. P2 (Legato bake-off / fine-tune) remains gated on recognition/matrix results — see `docs/evaluation/p2-deferral-note.md` and `docs/evaluation/ned-model-gate.md`.

## Notes

- Generated fixtures use MuseScore-rendered PDFs from paired MusicXML.
- Page-limited MuseScore.com samples compare against a leading-measure GT slice (`gt_page_scope`) so full-score GT is not scored blindly against page-1 OMR.
- Legato remains experimental; promote only if a later held-out taxonomy shows model-limited (not pipeline) failures.
- Avoid production-quality claims from parse rate alone.
