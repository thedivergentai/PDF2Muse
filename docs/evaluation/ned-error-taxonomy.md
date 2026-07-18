# NED error taxonomy

Source: `evaluation\runs\multi-tier-quality-v1\tier1b-musescore-com\evaluation_results.json`

| Bucket | Count | Avg OMR-NED | Samples |
|--------|-------|-------------|---------|
| `pitch_rhythm` | 11 | 0.679 | `musescore-manual-chopin-nocturne-op-9-no-2-e-flat-major`, `musescore-manual-clair-de-lune-debussy`, `musescore-manual-etude-s-1413-in-g-minor-la-campanella-liszt`, `musescore-manual-fur-elise-beethoven`, `musescore-manual-liebestraum-s-541-no-3-in-a-major-liszt`, `musescore-manual-piano-sonata-no-11-k-331-3rd-movement-rondo-alla-turca`, `musescore-manual-prelude-i-in-c-major-bwv-846-well-tempered-clavier-first-book`, `musescore-manual-sonate-no-14-moonlight-1st-movement`, `musescore-manual-sonate-no-14-moonlight-3rd-movement`, `musescore-manual-wa-mozart-marche-turque-turkish-march-fingered`, `musescore-manual-waltz-in-a-minorchopin` |
| `part_collapse` | 2 | 0.829 | `musescore-manual-g-minor-bach`, `musescore-manual-the-entertainer-scott-joplin` |
| `sparse_ok` | 2 | 0.283 | `musescore-manual-canon-in-d-johann-pachelbel`, `musescore-manual-gymnopedie-no-1-satie` |

## Per-sample

| Sample | Bucket | OMR-NED | Parts pred/GT | notes_rel |
|--------|--------|---------|---------------|-----------|
| `musescore-manual-canon-in-d-johann-pachelbel` | `sparse_ok` | 0.232 | 1/1 | 0.00847457627118644 |
| `musescore-manual-chopin-nocturne-op-9-no-2-e-flat-major` | `pitch_rhythm` | 0.693 | 1/1 | 0.04 |
| `musescore-manual-clair-de-lune-debussy` | `pitch_rhythm` | 0.621 | 1/1 | 0.00819672131147541 |
| `musescore-manual-etude-s-1413-in-g-minor-la-campanella-liszt` | `pitch_rhythm` | 0.778 | 1/1 | 0.005597014925373134 |
| `musescore-manual-fur-elise-beethoven` | `pitch_rhythm` | 0.674 | 1/1 | 0.03299492385786802 |
| `musescore-manual-g-minor-bach` | `part_collapse` | 0.979 | 1/2 | 0.01569506726457399 |
| `musescore-manual-gymnopedie-no-1-satie` | `sparse_ok` | 0.334 | 1/1 | 0.01775147928994083 |
| `musescore-manual-liebestraum-s-541-no-3-in-a-major-liszt` | `pitch_rhythm` | 0.568 | 1/1 | 0.0858085808580858 |
| `musescore-manual-piano-sonata-no-11-k-331-3rd-movement-rondo-alla-turca` | `pitch_rhythm` | 0.538 | 1/1 | 0.03678929765886288 |
| `musescore-manual-prelude-i-in-c-major-bwv-846-well-tempered-clavier-first-book` | `pitch_rhythm` | 0.752 | 1/1 | 0.05303030303030303 |
| `musescore-manual-sonate-no-14-moonlight-1st-movement` | `pitch_rhythm` | 0.912 | 1/1 | 0.0436241610738255 |
| `musescore-manual-sonate-no-14-moonlight-3rd-movement` | `pitch_rhythm` | 0.896 | 1/1 | 0.11464968152866242 |
| `musescore-manual-the-entertainer-scott-joplin` | `part_collapse` | 0.679 | 1/2 | 0.010416666666666666 |
| `musescore-manual-wa-mozart-marche-turque-turkish-march-fingered` | `pitch_rhythm` | 0.535 | 1/1 | 0.05519480519480519 |
| `musescore-manual-waltz-in-a-minorchopin` | `pitch_rhythm` | 0.505 | 1/1 | 0.038461538461538464 |

## Interpretation

- `part_collapse`: GT has more parts/staves than OMR output; full NED is inflated.
- `pitch_rhythm`: note counts nearly match but NED is high → symbol-level errors.
- `high_edit_dense`: dense scores with very high edit distance.
- `sparse_ok`: relatively low NED on simpler pages.
- `metric_null`: musicdiff completed without a recoverable OMR-NED value.

## OpenScore (tier1a) note

All 3 OpenScore lieder samples are `part_collapse` (OMR 1 part vs GT 2; avg OMR-NED **0.872** after re-aggregation). Notes-only musicdiff on one sample dropped full NED 0.849 → 0.771 — still high; topology is not the only gap.
