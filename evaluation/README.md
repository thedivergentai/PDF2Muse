# Evaluation Workspace

This directory holds lightweight evaluation manifests and documentation for local
PDF2Muse quality checks.

The evaluation harness is intentionally local-file based. It does not download
datasets for you. Prepare a small set of PDFs and ground-truth MusicXML files,
then describe them in a manifest.

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

Outputs are written under `evaluation/runs/`, which is ignored by git.

Expected report files:

- `evaluation_results.json`
- `evaluation_summary.md`

Use small samples first. Full OMR runs can be slow on CPU.
