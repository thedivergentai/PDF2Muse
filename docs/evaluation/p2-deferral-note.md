# P2 deferral (post quality gates)

Date: 2026-07-18  
Gate run: `evaluation/runs/multi-tier-quality-v1/`

## Decision

**Defer Legato bake-off and fine-tuning.** Tier0/1a/1b full-gates passed with **0 failed samples** and an empty failure taxonomy (no join/errno/OMR class dominance to chase).

## Why not P2 now

- Prior 2333 failures were largely **pipeline** (music21 join write, Errno 22 cascades). Those are addressed; parse is 21/21 across the three gate tiers.
- Remaining quality gap is **measured note disagreement** (tier1b OMR-NED avg ~0.61 on 12 scores), not “no MusicXML.” That is an accuracy ceiling problem, but P2 backends/FT should wait for a held-out taxonomy that attributes errors to symbol vs staffline (or similar), with licenses cleared — not jump from a green parse gate.

## Revisit when

- A gate run shows sustained `symbol_*` / `staffline_*` failures after P0/P1 defaults, or
- OMR-NED plateaus with clear per-class evidence on licensed held-out GT.
