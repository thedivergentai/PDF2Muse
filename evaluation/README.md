# Evaluation Workspace

This directory holds lightweight evaluation manifests and documentation for local
PDF2Muse quality checks.

The evaluation harness is intentionally local-file based. It does not download
datasets for you. Prepare a small set of PDFs and ground-truth MusicXML files,
then describe them in a manifest.

Evaluation reports are regression and quality signals. They do not make the
generated MusicXML production-ready; every converted score still needs human
review in notation software.

## Manifest Format

Each manifest is JSON with a `samples` array:

```json
{
  "samples": [
    {
      "id": "sample-1",
      "input": "../../datasets/raw/example/score.pdf",
      "ground_truth": "../../datasets/raw/example/truth.musicxml",
      "source": "local-example",
      "license_notes": "Public domain source, local transcription",
      "difficulty_tags": ["clean-typeset", "single-staff"],
      "first_page": 1,
      "last_page": 1
    }
  ]
}
```

Paths may be absolute or relative to the manifest file. Phase 2 evaluation
supports PDF inputs. Image-direct evaluation should be designed separately.

## Running A Smoke Evaluation

```bash
venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\smoke.local.json --output evaluation\runs\smoke --limit 3 --no-musicdiff
```

## Running A Clean-Typeset Baseline

Start the quality loop with 20-50 clean printed/typeset PDFs that have trusted
ground-truth MusicXML. Keep raw PDFs and generated run outputs in ignored local
directories unless the source license clearly allows redistribution.

For a legally safe generated local fixture set:

```bash
venv\Scripts\python.exe scripts\clean_typeset_benchmark.py --sample-count 20 --output-dir datasets\cache\clean-typeset-generated --manifest evaluation\manifests\clean-typeset.local.json
```

The generated fixtures are useful for tier-0 pipeline smoke. PDFs are rendered
via MuseScore CLI from paired MusicXML.

```bash
venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\clean-typeset.local.json --output evaluation\runs\clean-typeset --limit 20 --oemer-timeout 900 --oemer-device cuda
```

## Multi-tier evaluation

Runs tier 0 fixtures → tier 1a OpenScore → tier 1b MuseScore.com → tier 2
degraded pairs → tier 3 model benchmark (tier 3 only if tier 1 passes).

```bash
venv\Scripts\python.exe scripts\multi_tier_eval.py --limit 5 --oemer-device cuda
# Resume a previous output directory (skips samples with successful combined.musicxml):
venv\Scripts\python.exe scripts\multi_tier_eval.py --output evaluation\runs\multi-tier-YYYYMMDD-HHMM --full-gates --oemer-device cuda
# Force re-convert everything:
venv\Scripts\python.exe scripts\multi_tier_eval.py --force --full-gates --oemer-device cuda
# Standalone backend compare (does not overwrite docs unless --publish-docs):
venv\Scripts\python.exe scripts\model_benchmark.py --limit 3
venv\Scripts\python.exe scripts\legato_setup.py --verify
```

### Warm oemer worker (CUDA)

On `--oemer-device cuda`, PDF2Muse defaults to a **persistent oemer worker** that
keeps ONNX Runtime sessions warm across pages (`PDF2MUSE_OEMER_WORKER` defaults
on for CUDA). This avoids reloading `unet_big` / `seg_net` for every page and
retry. Disable with `PDF2MUSE_OEMER_WORKER=0` to force the old per-page
subprocess path. CUDA page processing is serial (`max_workers=1`) so one GPU
session is not thrashed.

Stage timings (session_load, inference_*, dewarp, total_page) are printed as
`PDF2MUSE_DIAG stage_timings ...` and stored on attempt metadata when available.
Post-processing remains largely CPU-bound; mid-run GPU util around 50–60% is
often expected (hybrid ORT + CPU postprocess), not proof that CUDA is unused.

VRAM: model weights are small; ORT’s CUDA arena is capped by default
(`PDF2MUSE_ORT_GPU_MEM_LIMIT_MB=4096` **per session**,
`arena_extend_strategy=kSameAsRequested`; two warm nets may approach ~2x).
If a warm worker fails, it is shut down before any cold CUDA subprocess so two
processes do not both hold GPU memory. Optional
`PDF2MUSE_OEMER_SINGLE_MODEL_VRAM=1` keeps only one net resident between passes.
Tile scan density defaults to `step_size=192`, `batch_size=8` for
`balanced`/`fast`. Under `quality`, defaults are denser stock-like
`step_size=128`, `batch_size=16` (override with `PDF2MUSE_OEMER_STEP_SIZE` /
`PDF2MUSE_OEMER_BATCH_SIZE`). Optional `PDF2MUSE_OEMER_DPI_RETRY=1` retries a
failed sample once at 360 DPI after symbol/staffline empties.

OMR-NED uses the installed `musicdiff` Python API (`pip install musicdiff`);
do not rely on `python -m musicdiff -o … files` because argparse `nargs=*` can
swallow the file paths. Page-limited samples compare against a leading-measure
GT slice (`gt_page_scope`) so MuseScore.com page-1 manifests are not scored
against full-score ground truth.

CUDA is the default when the ONNX CUDA ExecutionProvider is available
(`--oemer-device auto`). Pass `--oemer-device cpu` for CI or CPU-only machines.

Note: some UNet `ConvTranspose` nodes still fall back to CPU inside ONNX Runtime
(asymmetric padding limitation). Neural-net layers still use the GPU; oemer
post-processing (dewarp/stafflines/symbols) remains CPU NumPy and now uses more
OpenMP threads when running in CUDA mode.

### Trusted-input policy

Samples may include `input_quality`:

```json
{ "renderer": "musescore-cli", "trusted_for_accuracy": true }
```

Untrusted samples (`trusted_for_accuracy: false`) are skipped unless you pass
`--allow-untrusted-inputs` to `pdf2muse evaluate`. Degraded tier-2 manifests are
marked untrusted; `multi_tier_eval.py` enables the flag only for that tier.

Add `--musescore-path "C:\Program Files\MuseScore 4\bin\MuseScore4.exe"` when
you want the report to include MuseScore import validation.

Use `--render-dpi` to record DPI experiments. Product default is **360 DPI**
(quality matrix winner on MuseScore.com limit-5 vs 300). Keep `--render-dpi 300`
when comparing against older baselines.

Reports distinguish hard conversion failures from lower-similarity outputs:

- XML parseability and optional MusicXML library import status.
- Optional `musicdiff`/OMR-NED status and extracted JSON when available.
- Structural count differences for parts, measures, notes, rests, and pitches.
- Failure categories and ranked samples for manual review.

Outputs are written under `evaluation/runs/`, which is ignored by git.

Expected report files:

- `evaluation_results.json`
- `evaluation_summary.md`

Use small samples first. Full OMR runs can be slow on CPU.

The current generated-fixture smoke baseline is documented at
`docs/evaluation/clean-typeset-baseline-report.md`. It currently records a
runtime timeout before MusicXML output, not recognition accuracy.

A real public-domain PDF smoke using a Mutopia Project score is documented at
`docs/evaluation/public-score-smoke-report.md`. It is also a conversion/runtime
smoke, not an accuracy benchmark, because it does not include trusted MusicXML
ground truth.

The first OpenScore CC0 benchmark-source attempt is documented at
`docs/evaluation/openscore-benchmark-report.md`. OpenScore provides suitable
symbolic ground truth, but this environment still needs MuseScore CLI or another
trusted renderer to create benchmark-quality PDFs from those sources.

## MuseScore.com Paired Benchmark Loop

Use `scripts/musescore_com_benchmark.py` when collecting a local set of
MuseScore.com scores that have matching PDF, MusicXML, and `.mscx` files.
MuseScore.com does not provide a supported public download API, so this loop is
resumable and status-driven: blocked downloads are recorded as acquisition
failures, not PDF2Muse quality failures.

Prepare a local URL list:

```bash
mkdir datasets\benchmark-sources\musescore-com
notepad datasets\benchmark-sources\musescore-com\urls.txt
```

Then prepare or locate MuseScore CLI:

```bash
venv\Scripts\python.exe scripts\musescore_setup.py --setup-portable --tools-dir datasets\tools\musescore
```

Run the collection loop:

```bash
venv\Scripts\python.exe scripts\musescore_com_benchmark.py --urls-file datasets\benchmark-sources\musescore-com\urls.txt --limit 10 --allow-unofficial-downloader --setup-musescore-portable
```

For a logged-in browser workflow where you trigger official MuseScore.com
downloads yourself, use:

```bash
venv\Scripts\python.exe scripts\musescore_com_benchmark.py --urls-file datasets\benchmark-sources\musescore-com\urls.txt --limit 20 --interactive-browser-downloads --setup-musescore-portable
```

The loop writes `datasets/benchmark-sources/musescore-com/collection_status.json`
and `evaluation/manifests/musescore-com.local.json`. Officially downloaded
source `.mscx`, `.mscz`, `.musicxml`, `.xml`, `.mxl`, and PDF files can be placed
inside the per-score sample folders before rerunning the loop.

After at least one complete sample is present:

```bash
venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\musescore-com.local.json --output evaluation\runs\musescore-com-smoke --limit 10 --first-page 1 --last-page 1 --render-dpi 300 --oemer-timeout 900 --musescore-path path\to\MuseScore4.exe
```

Details and caveats are documented at
`docs/evaluation/musescore-com-benchmark.md`.

## Degraded Benchmark Variants

Create degraded PDF manifests only after a clean run completes and the
degradation matches observed failures:

```bash
venv\Scripts\python.exe scripts\degrade_benchmark.py evaluation\manifests\clean-typeset.local.json --output-dir datasets\cache\clean-typeset-low-contrast-light --output-manifest evaluation\manifests\clean-typeset-low-contrast-light.local.json --profile low-contrast --severity light --limit 3
```

Degraded reports are robustness stress tests and should be compared against the
matching clean run with the same ground truth.
