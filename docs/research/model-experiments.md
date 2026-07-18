# Model Experiments Research Note

## 5-Bullet Summary

- PDF2Muse currently treats `oemer` as the only OMR engine, with two expected checkpoints, `unet_big` and `seg_net`, downloaded into the installed `oemer/checkpoints` directory.
- The production pipeline shells out to `oemer.ete` or the local CPU wrapper per rendered page, so model comparison can be introduced by changing process environment and experiment metadata before changing conversion behavior.
- The evaluation harness is the right first integration point because it already owns manifests, per-sample output directories, parseability checks, structural metrics, and optional `musicdiff`/OMR-NED comparison.
- A model registry should describe model variants explicitly instead of relying on ad hoc checkpoint paths; each entry should record engine, checkpoint locations, backend, source, license notes, and expected outputs.
- The first fine-tuning or replacement experiment should be a small baseline-vs-candidate evaluation on licensed, inspectable samples, not a claim of improved accuracy.

## Files And Symbols Involved

- `src/pdf2muse/oemer_utils.py`
  - `get_checkpoint_dir()` locates the installed `oemer/checkpoints` directory.
  - `download_checkpoints(force=False)` downloads GitHub release assets into `unet_big/model.onnx`, `unet_big/weights.h5`, `seg_net/model.onnx`, and `seg_net/weights.h5`.
  - `ensure_checkpoints()` verifies those four files and downloads missing defaults.
- `src/pdf2muse/core.py`
  - `PDF2MusePipeline.__init__()` exposes `use_tf` and `save_cache`, but no checkpoint or model selector.
  - `PDF2MusePipeline.process_image_with_oemer()` chooses `oemer.ete` for TensorFlow or `pdf2muse._oemer_cpu` for ONNX CPU, then runs it in a per-page output directory.
  - `PDF2MusePipeline.run()` calls `ensure_checkpoints()` before rendering and OMR.
- `src/pdf2muse/_oemer_cpu.py`
  - `_patch_onnxruntime_cpu_provider()` pins implicit ONNX Runtime sessions to `CPUExecutionProvider`.
  - `main()` runs `oemer.ete` through `runpy` after patching ONNX Runtime.
- `src/pdf2muse/evaluation.py`
  - `EvaluationSample` and `load_manifest()` define the sample-level evaluation input shape.
  - `run_evaluation()` creates one `PDF2MusePipeline` per sample and writes JSON/Markdown results.
  - `compare_musicxml_files()` provides parseability, structural count, and optional `musicdiff` metrics for model comparisons.
- `src/pdf2muse/cli.py`
  - `convert()` passes user conversion flags to `PDF2MusePipeline`.
  - `evaluate()` is the preferred place to add experiment-only model selector flags.
  - `download_models()` delegates to `download_checkpoints()`.
- `src/pdf2muse/ui.py`
  - Pre-flight diagnostics and the model checkpoint manager assume only `unet_big` and `seg_net`.
- `pyproject.toml`
  - Runtime dependency is `oemer>=0.1.8`.
  - Evaluation extras are optional under `eval`.
- `docs/evaluation/*`
  - Existing notes require baseline-first evaluation, parseability reporting, structural metrics, license checks, and no unsupported quality claims.

## Checkpoint Override Strategy

The safest first override is process-local and evaluation-only: prepare an alternate checkpoint directory with the same internal layout expected by `oemer`, then run each model variant in a subprocess with an explicit override environment variable consumed by PDF2Muse-owned launch code. The experiment runner should copy or symlink the selected registry entry into an isolated temporary `checkpoints` tree shaped as:

```text
checkpoints/
  unet_big/
    model.onnx
    weights.h5
  seg_net/
    model.onnx
    weights.h5
```

This avoids mutating the installed `oemer` package, keeps concurrent comparisons isolated, and allows a baseline run to use the existing `ensure_checkpoints()` path unchanged. If `oemer` does not expose a documented checkpoint path override, PDF2Muse should avoid monkey-patching global installed files; instead, add a small experiment runner that creates a temporary package/checkpoint view or runs a replacement engine adapter with explicit paths.

Recommended implementation order:

1. Add registry parsing and validation under evaluation/experiment code, not normal conversion.
2. Add an internal `model_variant` or `checkpoint_set` argument to evaluation orchestration only.
3. Have the evaluation runner materialize the selected checkpoint set into an isolated temporary directory before invoking page OMR.
4. Record the registry entry ID and resolved artifact hashes in `evaluation_results.json`.
5. Promote a conversion-level flag only after the experiment path is stable and documented.

## Model Registry Recommendation

Use a small checked-in registry file for metadata and ignored local artifact directories for weights. A good first shape is a JSON or TOML file such as `evaluation/model_registry.example.json` with entries like:

```json
{
  "models": [
    {
      "id": "oemer-default-0.1.8",
      "engine": "oemer",
      "backend": "onnx",
      "checkpoint_layout": "oemer-two-stage",
      "unet_big": "local-or-hub-uri",
      "seg_net": "local-or-hub-uri",
      "license": "verify before publishing results",
      "notes": "Default upstream oemer checkpoints"
    }
  ]
}
```

Keep the registry responsible for metadata, path resolution, and provenance; keep large model files out of git. Each entry should include stable ID, engine adapter, backend, checkpoint layout, artifact URIs or local paths, expected hashes when available, training data/license notes, and compatibility notes. The evaluation report should include the model ID for every result so baseline-vs-candidate comparisons remain reproducible.

## First Fine-Tuning Or Replacement Experiment Plan

Start with a replacement-path comparison before training. Pick a tiny licensed subset with page images/PDFs and MusicXML ground truth, such as an OpenScore-derived sample after terms are verified, plus one degraded copy generated with the existing `degrade` command. Run the current `oemer` baseline through `pdf2muse evaluate`, then run one candidate registry entry through the same manifest and compare parseability, structural differences, optional `musicdiff`/OMR-NED, elapsed time, and manual inspection notes.

If pursuing fine-tuning, use the first run only to prove the loop:

1. Choose one model stage to target first, preferably the stage whose failure mode is visible in baseline reports.
2. Use only data with confirmed training rights and a held-out split.
3. Train or adapt outside the production pipeline and export artifacts into the registry layout.
4. Run the same evaluation manifest against baseline and candidate.
5. Accept the experiment only if it improves held-out metrics without increasing parseability failures.

For replacement models, define an adapter contract around "page image in, MusicXML or model-native intermediate out" and keep the existing MusicXML comparison harness as the common scoring surface.

## Risks

- `oemer` checkpoint discovery appears tied to package-local `checkpoints`; unsupported overrides may require wrapper work or upstream source inspection before implementation.
- The two-stage `unet_big`/`seg_net` layout may not map cleanly to replacement OMR models, so the registry needs an engine/layout field from the start.
- Existing evaluation supports PDF inputs only, while many datasets provide page images; image-direct evaluation or image-to-PDF wrapping may be needed for fair experiments.
- Dataset licensing remains a gate for training, redistribution, and public benchmark claims.
- Small samples can be useful for plumbing but are not evidence of broad model quality.
- OMR runs are slow on CPU, so model comparison jobs need page limits, cached artifacts, and clear reporting of runtime.
