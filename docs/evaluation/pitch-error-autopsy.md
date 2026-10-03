# Pitch error autopsy

Measured subclass attribution for OMR pitch/rhythm disagreements.
This is diagnostic, not a claim of production pitch accuracy.

- Run: `D:\Divergent AI\Development\PDF2Muse\evaluation\runs\multi-tier-quality-v1\tier1b-musescore-com`
- Samples: 15
- Attributed samples: 14 (93%)
- ≥70% attribution gate: PASS

## Dominant subclasses

- `insert_delete`: 13
- `clef_context`: 1
- `other`: 1

## Subclass event totals

- `insert_delete`: 4016
- `duration_beam`: 1294
- `clef_context`: 1051
- `other`: 859
- `staff_off_by_one`: 377
- `accidental`: 181
- `part_mismatch`: 6

## Interpretation for next work

Observed mix on this run:

- Sample-majority labels skew to `insert_delete` (alignment / missing-extra notes).
- Event totals still show large `clef_context`, plus `staff_off_by_one` and `accidental`.
- Therefore: prefer **grand-staff topology repair + layout-aware backends (HOMR-class)** and
  **symbolic spellcheck** for residual drafts; keep **`seg_net` FT gated** (see
  `segnet-ft-gate.md`) after no-op checkpoint control — do not treat DPI/tiling as the
  primary remaining lever.

Generic guide:

- If `staff_off_by_one` / `accidental` dominate → consider `seg_net` FT with segmentation labels (after no-op checkpoint control).
- If `clef_context` / `part_mismatch` dominate → prefer grand-staff topology repair and/or layout-aware backends (homr-class), not DPI.
- If `duration_beam` dominates → builder/heuristics and symbolic spellcheck.

