# Synthetic Degradation And Fine-Tuning Plan

PDF2Muse should not jump straight to fine-tuning. The first priority is to
measure current output quality against trusted ground truth, then use observed
failure modes to decide which synthetic data is worth generating.

## Baseline First

Before expanding synthetic data:

1. Run `pdf2muse evaluate` on a small local manifest.
2. Record parseability failures.
3. Record structural differences for parts, measures, notes, rests, and pitched
   notes.
4. Run `musicdiff`/OMR-NED where dependencies and file parseability allow it.
5. Inspect representative failures manually.

## Initial Degradation Profiles

The first deterministic degradation command supports small, image-level
experiments:

```bash
pdf2muse degrade datasets/raw/example/images datasets/cache/example-scan-noise --profile scan-noise --severity medium --seed 123
```

Profiles:

- `scan-noise`: low contrast grayscale, sparse salt/pepper noise, light blur.
- `blur`: Gaussian blur.
- `low-contrast`: reduced contrast.
- `shadow`: simple vertical lighting gradient.
- `jpeg-artifacts`: lossy compression artifacts from scanned or shared files.
- `skew`: small page rotation.
- `uneven-lighting`: lighting gradient alias for scan-like shadows.

Severity levels:

- `light`: mild stress case for clean printed pages.
- `medium`: default stress case for routine robustness checks.
- `heavy`: manual-review stress case; do not use it as evidence of product
  quality unless real samples show comparable damage.

These profiles are intentionally modest. They should be expanded only after
baseline reports show which image conditions hurt recognition most.

Each run writes `degradation_metadata.json` with the profile, severity, seed,
profile parameters, and per-file parameters. Keep this metadata with the
evaluation report so any degraded sample can be reproduced exactly.

## Evaluation Bridge

Use degraded variants as paired stress tests:

1. Run the clean PDF baseline and save the report.
2. Generate degraded page images from the same source pages.
3. Wrap degraded page images back into local PDFs, or create a separate
   image-direct harness later.
4. Create a second manifest that points to the degraded inputs but keeps the
   same ground-truth MusicXML and sample identifiers with a suffix such as
   `-scan-noise-medium`.
5. Run `pdf2muse evaluate` on the degraded manifest and compare failure
   categories, parseability, structural differences, and OMR-NED against the
   clean report.

Do not promote a degradation profile to benchmark status until it maps to an
observed real failure class from clean or scanned samples.

## Fine-Tuning Gates

Write a separate fine-tuning plan only if all gates pass:

- The target model and training path are understood for `oemer` or a replacement
  OMR model.
- Dataset licenses allow training and derived artifacts.
- The target representation is chosen: MusicXML, Linearized MusicXML, MEI, MIDI,
  Humdrum, or an OMR-model-native intermediate format.
- The evaluation harness can measure improvements on held-out samples.
- Compute requirements are realistic for the maintainer workflow.

Until these gates pass, synthetic degradation should be used for robustness
experiments and evaluation stress tests, not as a claim of model improvement.
