# Model Experiments

PDF2Muse should compare model changes through the evaluation harness before any
model is treated as a product improvement.

## Backend Slots

- `oemer-stock`: the default `oemer` checkpoints installed with or downloaded
  for the package.
- `oemer-custom`: an experimental `oemer` checkpoint directory passed with
  `--checkpoint-dir`, intended for fine-tuned `unet_big` and `seg_net`
  experiments without overwriting package checkpoints. The directory must
  already contain complete `oemer`-compatible checkpoint files; PDF2Muse will
  not populate it with stock weights during an experiment. This is not yet a
  proven runtime override; a no-op copied-checkpoint control must pass before
  using it for model comparisons.
- `legato-experimental`: a placeholder for a future replacement adapter that
  produces ABC or another intermediate format and converts it to MusicXML for
  the same report pipeline. It is listed for planning, but conversion fails
  explicitly until an adapter is implemented.
- `homr`: optional [HOMR](https://github.com/liebharc/homr) backend via
  `pip install 'pdf2muse[homr]'` (AGPL-3.0, Python >= 3.11). Use
  `--model-backend homr`. Not selected by `auto` unless
  `PDF2MUSE_ALLOW_HOMR_AUTO=1`.

Planned custom-checkpoint evaluation, after runtime override validation:

```bash
venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\clean-typeset.local.json --output evaluation\runs\clean-typeset-oemer-custom --model-backend oemer-custom --checkpoint-dir datasets\models\oemer-custom --limit 20
```

## Fine-Tuning Gates

Do not launch fine-tuning until all gates pass:

- The clean-typeset stock baseline is saved and manually reviewed.
- Dataset licenses permit training, derived checkpoints, and any intended
  sharing.
- Train, validation, and held-out test splits are fixed before training.
- The target component is chosen from observed failures: `unet_big` for
  staff/layout problems, `seg_net` for detailed symbol segmentation problems,
  or a replacement adapter for end-to-end structural failures.
- Success is defined by held-out parseability, MuseScore import status,
  structural deltas, and `musicdiff`/OMR-NED where available.

## First Experiment

1. Run `oemer-stock` on the clean-typeset manifest and save the report.
2. Curate 20-50 samples where stock output fails or has large structural
   deltas, while preserving a separate held-out set.
3. Prove that `--checkpoint-dir` actually redirects `oemer` inference using a
   no-op copied-checkpoint control.
4. Train or source an `oemer-custom` checkpoint in a separate ignored directory.
5. Re-run the same manifest with `--model-backend oemer-custom --checkpoint-dir
   <path>`.
6. Compare reports by failure category first, then parseability/import gates,
   then structural deltas and OMR-NED.

Keep replacement-model adapters experimental until they beat stock `oemer` on
the same user-facing outputs: parseable MusicXML, optional MuseScore import, and
notation-aware metrics.
