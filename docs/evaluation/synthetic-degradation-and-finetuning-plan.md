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
pdf2muse degrade datasets/raw/example/images datasets/cache/example-scan-noise --profile scan-noise --seed 123
```

Profiles:

- `scan-noise`: low contrast grayscale, sparse salt/pepper noise, light blur.
- `blur`: Gaussian blur.
- `low-contrast`: reduced contrast.
- `shadow`: simple vertical lighting gradient.

These profiles are intentionally modest. They should be expanded only after
baseline reports show which image conditions hurt recognition most.

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
