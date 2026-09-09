# Pitch accuracy and multi-staff quality

Research-backed notes for attacking PDF2Muse’s remaining quality ceiling
(~0.58–0.65 OMR-NED on held-out MuseScore.com). Recognition levers (DPI /
tiling / quality profile) are mostly exhausted; further gains need different
failure loci.

This document captures the roadmap implemented under the pitch/multi-staff
plan. It is **not** a claim of production pitch accuracy.

## Measured taxonomy (baseline)

| Bucket | Meaning |
|--------|---------|
| `pitch_rhythm` | Note counts ≈ GT; pitches / rhythms / beams disagree |
| `part_collapse` | Pred 1 part vs GT 2+; NED inflated and musically wrong |
| `sparse_ok` | Simple piano pages nearer GT (~0.28) |

## Why pitch goes wrong

In oemer (classical OMR), pitch is a cascade: staff geometry → notehead Y →
clef → key signature → accidentals → MIDI. Failures include off-by-one staff
position, wrong clef/track, missed accidentals, dense polyphony association,
and rule-based builder limits.

## Why multi-staff / multi-instrument fails

Oemer track/group inference breaks on lyrics between staves (see oemer#59) and
on OpenScore lieder / dense piano. Export can also serialize hands as sequential
unrelated parts.

External layout-aware systems (HOMR / TrOMR-class, SMT++) target this better;
HOMR is AGPL and stays **experimental** unless licensing is cleared.

## Phase status (this repo)

### Phase 1 — Pitch autopsy (done)

- Module: `src/pdf2muse/pitch_autopsy.py`
- Script: `scripts/pitch_error_autopsy.py`
- Report: `docs/evaluation/pitch-error-autopsy.md`
- Subclasses: `staff_off_by_one`, `accidental`, `clef_context`, `duration_beam`,
  `insert_delete`, `part_mismatch`

Observed on `multi-tier-quality-v1` tier1b: attribution gate **≥70% PASS**.
Event totals show large `insert_delete` / `duration_beam` plus substantial
`clef_context`, `staff_off_by_one`, and `accidental` after music21 merge —
supporting **topology repair + layout backends** first, with **seg_net FT**
gated (not blocked) for pitch-local errors.

### Phase 2 — Grand-staff topology repair (done)

- Module: `src/pdf2muse/topology.py`
- Wired after MusicXML join in `PDF2MusePipeline`
- Remeasure: `scripts/remeasure_topology_repair.py`

Heuristics merge G+F (or high/low register) part pairs into one grand-staff
part with `staff` 1/2. Does **not** invent missing notes.

### Phase 3 — HOMR experimental adapter (scaffold)

- Adapter: `src/pdf2muse/adapters/homr.py`
- Backend name: `homr-experimental` (never auto-selected)
- Bake-off scaffold: `scripts/homr_bakeoff.py`
- License: **AGPL-3.0** — not a product default

### Phase 4 — Symbolic spellcheck prototype (done)

- Module: `src/pdf2muse/spellcheck.py`
- Script: `scripts/symbolic_spellcheck.py`
- Synthetic corrupt↔GT pairs + melodic-leap flagger for UI review aids

### Phase 5 — seg_net FT gate (decision)

See `docs/evaluation/segnet-ft-gate.md`. Autopsy warrants a **gated** FT path
(no-op checkpoint control first), not immediate training: clef/layout and
insert/duration dominate sample majority votes; pitch-local subclasses are
present but secondary.

## Explicit non-goals

- Claiming SOTA or review-free output
- Making AGPL HOMR the default converter without a license decision
- More DPI/tiling sweeps as the primary quality bet
- Soft-passing empty/invalid MusicXML

## Commands

```powershell
.\venv\Scripts\python.exe scripts\pitch_error_autopsy.py
.\venv\Scripts\python.exe scripts\remeasure_topology_repair.py
.\venv\Scripts\python.exe scripts\homr_bakeoff.py
.\venv\Scripts\python.exe scripts\symbolic_spellcheck.py
```
