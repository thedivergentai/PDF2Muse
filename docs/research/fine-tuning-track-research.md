# Fine-Tuning Track Research

## 5-Bullet Summary

- PDF2Muse currently runs `oemer` as a subprocess per rendered page; it owns PDF rendering, checkpoint convenience helpers, CPU-provider pinning, output collection, and evaluation reports, but not the model API itself.
- The active Oemer recognition path has two target components: `unet_big` for staffline/background/symbol segmentation and `seg_net` for detailed symbol-layer segmentation used by the downstream rule-based MusicXML builder.
- `oemer-custom` and `--checkpoint-dir` exist in the repo, but the installed `oemer.ete` still resolves models from `oemer.MODULE_PATH/checkpoints`; the environment variable currently validates alternate directories in PDF2Muse but does not by itself redirect Oemer inference.
- Practical fine-tuning should start as an evaluation-only track: prove a no-op copied-checkpoint override first, then train or source candidate `unet_big`/`seg_net` artifacts outside the production converter and score them through the existing manifest harness.
- Replacement-model work should be treated as an adapter experiment that accepts page images and emits comparable per-page MusicXML or a model-native intermediate that can be converted and measured against the same reports before any product integration.

## Current Oemer Integration

The production path is:

1. `PDF2MusePipeline.run()` calls `ensure_checkpoints()`.
2. `pdf_to_png()` renders PDF pages to PNG with `pypdfium2`.
3. `process_image_with_oemer()` runs either `python -m pdf2muse._oemer_cpu <page.png>` for ONNX CPU or `python -m oemer.ete <page.png> --use-tf` for TensorFlow.
4. `_oemer_cpu` patches implicit ONNX Runtime sessions to use `CPUExecutionProvider`, then runs `oemer.ete`.
5. Installed `oemer.ete.generate_pred()` calls `oemer.inference.inference()` on `MODULE_PATH/checkpoints/unet_big` and `MODULE_PATH/checkpoints/seg_net`.

The repo exposes model experiment controls in both `convert` and `evaluate`:

- `--model-backend oemer-stock` uses package-local/default Oemer checkpoints.
- `--model-backend oemer-custom --checkpoint-dir <path>` records an experimental custom checkpoint directory and disables automatic stock downloads for that path.
- `legato-experimental` is listed as a future replacement-adapter placeholder and intentionally fails conversion today.

Important implementation gap: `PDF2MUSE_OEMER_CHECKPOINT_DIR` is read by PDF2Muse's `get_checkpoint_dir()` and used for validation, but installed Oemer does not read that environment variable. Unless PDF2Muse patches `oemer.MODULE_PATH`, wraps `oemer.ete.generate_pred()`, or implements a direct adapter, `--checkpoint-dir` should not be treated as a proven runtime override.

## Target Components

### `unet_big`

Purpose: first-stage segmentation for stafflines and coarse symbols. Installed `oemer.ete.generate_pred()` converts its class map into:

- `staff`: pixels where class map equals `1`.
- `symbols`: pixels where class map equals `2`.

Training path: installed `oemer.train.train_model(data_model != "segnet")` uses CVC-MUSCIMA distortion-style folders with `image`, `gt`, and `symbol` files, builds 3-class labels, and trains `semantic_segmentation(win_size=256, out_class=3)`.

Use when baseline reports show staffline extraction, layout, deskew/dewarp, or coarse symbol/background separation failures.

### `seg_net`

Purpose: second-stage detailed symbol-layer segmentation. Installed `oemer.ete.generate_pred()` maps its class output into:

- `stems_rests`: class map equals `1`.
- `notehead`: class map equals `2`.
- `clefs_keys`: class map equals `3`.

Training path: installed `oemer.train.train_model(data_model="segnet")` uses DeepScores-style `images/` and `segmentation/` inputs, converts dense segmentation colors through `build_label()`, and trains `u_net(win_size=288, out_class=CHANNEL_NUM)`.

Use when baseline reports show notehead, rest, stem, clef, key, or other detailed symbol errors while staff/layout extraction is acceptable.

## Checkpoint Artifact Requirements

Installed `oemer.inference.inference()` requires different file sets by backend:

- ONNX: `model.onnx` and `metadata.pkl` in each model directory.
- TensorFlow: `arch.json` and `weights.h5` in each model directory.

The current PDF2Muse downloader saves GitHub release assets as `model.onnx` and `weights.h5` under both `unet_big/` and `seg_net/`. Before relying on custom checkpoints, validate the actual installed/default checkpoint contents and align PDF2Muse checks with the backend in use. For ONNX experiments, missing `metadata.pkl` should be a hard failure. For TensorFlow experiments, missing `arch.json` should be a hard failure.

Expected experiment layout:

```text
<checkpoint-root>/
  unet_big/
    model.onnx
    metadata.pkl
  seg_net/
    model.onnx
    metadata.pkl
```

or, for TensorFlow:

```text
<checkpoint-root>/
  unet_big/
    arch.json
    weights.h5
  seg_net/
    arch.json
    weights.h5
```

## Dataset And License Gates

- License gate: do not train, redistribute checkpoints, or publish benchmark claims until each dataset's terms allow training, derived model artifacts, local caching, and the intended form of metric publication.
- Provenance gate: manifests should record source, local path, license notes, split, page range, and difficulty tags; raw datasets and generated variants should stay in ignored local directories.
- Split gate: fix train, validation, and held-out test samples before training. Do not evaluate a fine-tuned checkpoint on pages, works, or synthetic variants used in training.
- Representation gate: decide whether training targets Oemer-native segmentation masks, MusicXML, MEI, ABC, MIDI, Humdrum, or another intermediate; `unet_big` and `seg_net` require segmentation labels, not MusicXML alone.
- Evaluation gate: candidate models must improve held-out parseability, MuseScore import status where configured, structural deltas, and optional `musicdiff`/OMR-NED without increasing critical failures.
- Dataset candidates from existing notes include Debussy, MusiCorpus, CollabScore, OpenScore-derived samples, DoReMi, DeepScoresV2, and MUSCIMA++; each still needs documented access and terms before use.

## First Experiment Proposal

Run a no-op copied-checkpoint control before any fine-tuning.

1. Select 3-5 one-page local PDF samples with ground-truth MusicXML and recorded license notes.
2. Run the stock baseline through `pdf2muse evaluate` with `--model-backend oemer-stock`, saving JSON/Markdown reports.
3. Copy the installed/default Oemer checkpoint tree into an ignored experiment directory using the backend-correct files for both `unet_big` and `seg_net`.
4. Run the same manifest with a temporary runtime override that actually redirects `oemer.ete.generate_pred()` to the copied checkpoint root.
5. Compare parseability, MusicXML output, structural metrics, optional OMR-NED, and runtime against the stock baseline.

Success criterion: copied-checkpoint output matches stock output closely enough that later differences can be attributed to model artifacts rather than override mechanics. If this fails, fix the override/adapter path before training.

After the control passes, the first real candidate should target only one component chosen from observed baseline failures:

- Choose `unet_big` if failures cluster around staff/layout/coarse symbol segmentation.
- Choose `seg_net` if failures cluster around symbol-layer detail after staff extraction succeeds.
- Keep the other component at stock weights for the first candidate so the source of behavior changes is easier to isolate.

## Replacement-Model Path

A replacement model should not pretend to fit the two-checkpoint Oemer layout unless it really does. Use an adapter contract instead:

- Input: the same rendered page PNGs produced by PDF2Muse.
- Output: per-page MusicXML, or a documented intermediate that PDF2Muse can convert to per-page MusicXML.
- Report fields: adapter ID, model artifact hashes, source/license notes, runtime, parseability, structural metrics, optional `musicdiff`/OMR-NED, and manual review notes.
- Promotion gate: only wire it into `convert`/UI after it beats or complements stock `oemer` on the same held-out reports.

## Risks

- The current custom-checkpoint path is only partially wired: PDF2Muse can validate alternate directories, but installed Oemer still uses package-local `MODULE_PATH/checkpoints` unless runtime redirection is added.
- The repo's checkpoint validation currently checks `model.onnx` and `weights.h5`, while installed ONNX inference requires `metadata.pkl`; this can produce false confidence in a custom checkpoint directory.
- Oemer fine-tuning depends on older TensorFlow/TensorFlow Addons-era code and dataset-specific label formats, so environment setup may be more work than the PDF2Muse wrapper changes.
- Training `unet_big` and `seg_net` requires segmentation labels, not just score-level MusicXML; many useful OMR datasets may need conversion, filtering, or may be unsuitable for direct Oemer training.
- Replacement models may produce structurally different outputs that need adapter-specific normalization before comparisons are fair.
- CPU OMR runs are slow, so experiments need small smoke manifests, page limits, cached artifacts, and clear runtime reporting.
- Small positive results are useful plumbing evidence, but not broad accuracy evidence; generated MusicXML should continue to be described as requiring human review.
