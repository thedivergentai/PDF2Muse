# NED model gate (post matrix)

Date: 2026-07-18  
Inputs: `docs/evaluation/ned-error-taxonomy.md`, `docs/evaluation/quality-matrix-ned-report.md`

## Checkpoint redirect

`PDF2MUSE_OEMER_CHECKPOINT_DIR` / `--checkpoint-dir` is proven to rewrite stock oemer model paths at inference time (`tests/test_checkpoint_redirect.py` + `_patch_oemer_checkpoint_dir` in `_oemer_common.py`). Safe to use for a future one-net experiment.

## Taxonomy → model choice

Tier1b buckets (re-aggregated quality-v1):

- **`pitch_rhythm` dominant (11/15)** — note counts nearly match; pitch/rhythm/symbol edits drive NED
- **`part_collapse` (2/15)** — multi-part GT vs single-part OMR; notes-only NED is lower but still high (OpenScore smoke: full 0.85 → notes-only 0.77)
- **`sparse_ok` (2/15)** — simple pages already nearer GT

## Decision (no training in this delivery)

| Option | Verdict |
|--------|---------|
| Lock DPI/tiling winners | **Done** (360 DPI + quality step 128) |
| Legato bake-off now | **Defer** — prior bake-off 0/3 parse; taxonomy is oemer symbol-level, not “need another backend first” |
| Fine-tune | **Candidate: `seg_net` only** (symbol/pitch class), after licensed held-out labels exist — **not** `unet_big` first (staff not dominant) |
| Start FT training now | **No** — matrix winner still leaves avg NED ~0.58 vs target ≤0.45; next step is a scoped `seg_net` FT plan with licenses/splits, not an unguided run |

## Revisit when

- A `seg_net` FT experiment with cleared licenses and held-out NED beats stock `dpi360-quality-step128`, or
- Part topology improves enough that notes-only and full NED both drop below 0.45 on tier1b.
