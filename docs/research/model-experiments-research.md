# Model Experiments Research

## 5-Bullet Summary

- PDF2Muse currently delegates recognition to `oemer.ete` through `PDF2MusePipeline.process_image_with_oemer`; model selection is limited to ONNX CPU by default or TensorFlow with `--use-tf`.
- The active checkpoint flow assumes the installed `oemer` package layout: `checkpoints/unet_big` for staff/symbol segmentation and `checkpoints/seg_net` for layered symbol segmentation.
- A checkpoint override is the smallest useful experiment surface, but it should require an external root with the same `unet_big` and `seg_net` subdirectories and should never overwrite the packaged checkpoints by default.
- Fine-tuning `oemer` is possible in principle because the package includes `train.py` and `convert_to_onnx.py`, but it is TensorFlow-era, dataset-specific, and not yet suitable for a PDF2Muse product claim without a reproducible evaluation harness.
- Replacement-model experiments should be run as offline adapters that emit comparable MusicXML, then measured through manifests before any attempt to wire them into the conversion CLI or UI.

## Current Model Path

PDF2Muse converts each PDF page to a PNG, then runs `oemer` in a subprocess. The default path is:

1. `PDF2MusePipeline.run` calls `ensure_checkpoints`.
2. `PDF2MusePipeline.pdf_to_png` renders pages with `pypdfium2`.
3. `PDF2MusePipeline.process_image_with_oemer` runs `python -m pdf2muse._oemer_cpu <page.png>` unless `use_tf=True`, in which case it runs `python -m oemer.ete <page.png> --use-tf`.
4. `_oemer_cpu` monkey-patches ONNX Runtime sessions to use `CPUExecutionProvider`, then executes `oemer.ete`.
5. `oemer.ete.generate_pred` calls `oemer.inference.inference` twice: once with `MODULE_PATH/checkpoints/unet_big`, once with `MODULE_PATH/checkpoints/seg_net`.

This means PDF2Muse does not currently own the actual model API. It owns process orchestration, checkpoint download convenience, CPU-provider pinning, and output collection.

## Key Files And Symbols

- `src/pdf2muse/core.py`: `PDF2MusePipeline`, especially `process_image_with_oemer` and `run`.
- `src/pdf2muse/oemer_utils.py`: `get_checkpoint_dir`, `download_checkpoints`, `ensure_checkpoints`.
- `src/pdf2muse/_oemer_cpu.py`: `_patch_onnxruntime_cpu_provider`, `main`.
- `src/pdf2muse/cli.py`: `convert`, `download_models`, current `--use-tf` and `--save-cache` surface.
- `src/pdf2muse/ui.py`: conversion handlers and model checkpoint manager.
- Installed `oemer.ete`: `generate_pred`, `extract`, `get_parser`, `main`.
- Installed `oemer.inference`: `inference`, ONNX `metadata.pkl` loading, provider selection.
- Installed `oemer.train`: `train_model`, `DataLoader`, `DsDataLoader`.
- Installed `oemer.convert_to_onnx`: `convert`.
- Existing evaluation documents: `docs/evaluation/omr-output-comparison-baseline.md`, `docs/evaluation/omr-datasets-report.md`, and `docs/evaluation/synthetic-degradation-and-finetuning-plan.md`.

Note: this checkout has CLI and test references to `src/pdf2muse/evaluation.py` and `src/pdf2muse/degrade.py`, but those source files were not found during this research pass. Restore or implement the evaluation harness before relying on automated model comparisons.

## Implementation Recommendations

1. Add checkpoint override as the first code experiment, not replacement OMR. The future interface should accept a checkpoint root that contains `unet_big` and `seg_net`, each with the files `oemer.inference` needs for the selected backend. For ONNX this means `model.onnx` and `metadata.pkl`; for TensorFlow this means `arch.json` and `weights.h5`.
2. Keep packaged checkpoints immutable by default. Do not point fine-tuning outputs directly at the installed `oemer/checkpoints` directory. Use an ignored experiment directory such as `evaluation/runs/model-experiments/<run-id>/checkpoints` or a user-supplied external path.
3. Implement override through PDF2Muse-owned orchestration rather than modifying third-party package files. A future `_oemer_cpu` or sibling runner can set an environment variable such as `PDF2MUSE_OEMER_CHECKPOINT_ROOT`, validate the directory, then patch `oemer.MODULE_PATH` before executing `oemer.ete`.
4. Thread model identity through evaluation reports. Every run should record checkpoint root, backend (`onnx` or `tf`), oemer version, whether CPU pinning was used, and dataset/license notes from the manifest.
5. Compare models only through a manifest-based harness. A model run is meaningful only if it produces parseable MusicXML and has the same input pages, page range, deskew setting, and metric stack as the baseline run.
6. Treat `oemer` fine-tuning as a research track. Its training code expects CVC-style staff/symbol data or DeepScores-style segmentation data, uses TensorFlow/TensorFlow Addons, and saves a model that still needs conversion and metadata before ONNX inference.
7. Treat replacement OMR as an adapter contract, not a drop-in checkpoint. A replacement can be compared if it takes page images and writes MusicXML per page, but integration should wait until it beats or complements baseline `oemer` on held-out local samples.

## Dataset And License Gates

- Do not download or commit raw datasets as part of model work. Keep raw data under ignored local paths such as `datasets/raw/` and generated variants under `datasets/cache/` or `evaluation/runs/`.
- Record license notes in manifests before any training or public comparison. Dataset candidates already flagged for license review include DoReMi and some OpenScore-derived material.
- Do not train on a dataset until its terms allow training, derived checkpoints, local caching, and any intended publication of metrics.
- Keep train/validation/test splits explicit. Do not evaluate a fine-tuned checkpoint on the same pages or derived degradation variants used for training.
- Start with small, inspectable subsets from datasets with page images and symbolic ground truth. Debussy, MusiCorpus, CollabScore, and OpenScore-derived samples are practical candidates, but each still needs documented access and terms.
- Report generated MusicXML as requiring human review. Parseability and structural similarity are regression signals, not proof of musical correctness.

## Model Comparison Path

Use a three-tier comparison:

1. Baseline packaged `oemer` checkpoints with the current ONNX CPU path.
2. Same `oemer` architecture with external checkpoint roots, first using copied baseline checkpoints as a no-op override control, then fine-tuned candidates.
3. Replacement OMR adapters that produce page-level MusicXML and can be compared with the same manifest and metrics.

The no-op override control is important. If copied baseline checkpoints do not match packaged baseline output, the override mechanism is not trustworthy enough for model conclusions.

## Checkpoint Override Path

Recommended future validation:

- Require a checkpoint root path.
- Require `unet_big/` and `seg_net/`.
- For ONNX, require `model.onnx` and `metadata.pkl` in each subdirectory.
- For TensorFlow, require `arch.json` and `weights.h5` in each subdirectory.
- Record file hashes for all model artifacts used in an experiment.
- Fail fast on missing files instead of silently downloading or falling back.

The current `download_checkpoints` helper downloads `model.onnx` and `weights.h5` names, while installed `oemer.inference` expects `metadata.pkl` for ONNX and `arch.json` plus `weights.h5` for TensorFlow. Before adding override support, verify the installed checkpoint directories and update validation around the files actually required by the selected backend.

## Oemer Fine-Tuning Path

The installed `oemer` package includes training utilities, but they are not wrapped by PDF2Muse. Important constraints:

- `train_model(data_model="segnet")` uses DeepScores-style `images/` plus `segmentation/` inputs and produces a 4-channel segmentation model.
- The non-`segnet` path uses CVC-MUSCIMA distortion-style directories with `image`, `gt`, and `symbol` files and produces a 3-class staff/symbol model.
- Fine-tuning both `unet_big` and `seg_net` may be necessary because `oemer.ete.generate_pred` uses both outputs downstream.
- ONNX inference needs converted model artifacts plus metadata from `oemer.convert_to_onnx.convert`.
- PDF2Muse should not claim fine-tuning improvements until held-out MusicXML comparisons improve and parseability does not regress.

## Replacement-Model Experiment Path

Replacement-model work should stay outside the production converter until there is evidence. The cleanest experiment boundary is:

1. Render PDF pages with the same PDF2Muse page rendering settings.
2. Run the replacement model into per-page MusicXML in an experiment output directory.
3. Join or compare per-page MusicXML consistently with the baseline.
4. Use the same manifest, page ranges, parseability checks, and structural/musicdiff metrics.
5. Promote only the adapter contract after a replacement wins on clear target cases.

This keeps replacement evaluation separate from UI and CLI complexity, while still making results comparable to current `oemer` output.

## First Experiment Proposal

Run a no-op checkpoint override control before any training:

1. Select 3 to 5 local one-page samples with documented license notes and ground-truth MusicXML.
2. Run baseline PDF2Muse with packaged `oemer` ONNX CPU checkpoints and save reports under `evaluation/runs/model-experiments/baseline`.
3. Copy the installed `oemer/checkpoints` tree to an ignored experiment directory.
4. Run the same samples through a temporary override runner using the copied checkpoint root.
5. Compare file hashes or normalized MusicXML outputs, parseability, structural metrics, and runtime.

Success criteria: copied-checkpoint override output matches baseline closely enough that later differences can be attributed to checkpoint changes. If this fails, fix the override mechanism before attempting fine-tuning or replacement-model comparisons.
