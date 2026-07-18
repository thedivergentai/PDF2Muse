# NED error taxonomy

Source: `evaluation\runs\multi-tier-quality-v1\tier1a-openscore\evaluation_results.json`

| Bucket | Count | Avg OMR-NED | Samples |
|--------|-------|-------------|---------|
| `part_collapse` | 3 | 0.872 | `openscore-lieder-just-for-today`, `openscore-lieder-think-of-today`, `openscore-lieder-crazy-jane` |

## Per-sample

| Sample | Bucket | OMR-NED | Parts pred/GT | notes_rel |
|--------|--------|---------|---------------|-----------|
| `openscore-lieder-just-for-today` | `part_collapse` | 0.849 | 1/2 | 0.10580204778156997 |
| `openscore-lieder-think-of-today` | `part_collapse` | 0.900 | 1/2 | 0.08626198083067092 |
| `openscore-lieder-crazy-jane` | `part_collapse` | 0.867 | 1/2 | 0.04177545691906005 |

## Interpretation

- `part_collapse`: GT has more parts/staves than OMR output; full NED is inflated.
- `pitch_rhythm`: note counts nearly match but NED is high → symbol-level errors.
- `high_edit_dense`: dense scores with very high edit distance.
- `sparse_ok`: relatively low NED on simpler pages.
- `metric_null`: musicdiff completed without a recoverable OMR-NED value.
