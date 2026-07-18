# OpenScore CC0 Benchmark Report

## Scope

This report records the first OpenScore CC0 benchmark attempt. OpenScore Lieder
is the preferred source for public clean-typeset samples with symbolic ground
truth because the GitHub repository is licensed CC0-1.0 and provides `.mxl`
files.

## Assets

- Manifest: `evaluation/manifests/clean-typeset-openscore.local.json`
- Local source root: `datasets/benchmark-sources/clean-typeset/openscore-lieder/`
- Samples generated: 3
- Source repository: `https://github.com/OpenScore/Lieder`
- License: CC0-1.0
- Ground truth: plain `.musicxml` extracted from OpenScore `.mxl` files.

## Rendering Status

The benchmark builder at `scripts/openscore_benchmark.py` can download OpenScore
MXL files and extract MusicXML ground truth. Rendering suitable PDF inputs is
still gated by renderer quality:

- MuseScore CLI is not installed in this environment.
- MuseScore.com direct PDF downloads are blocked by browser verification.
- Verovio plus SVG-to-PDF conversion produced unsuitable cropped/oversized page
  images for the tested Lieder sample.

Because of that, OpenScore is currently ready as a source/ground-truth lane but
not yet a trustworthy PDF benchmark lane in this local environment.

## Baseline Attempt

Command:

```powershell
venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\clean-typeset-openscore.local.json --output evaluation\runs\clean-typeset-openscore-stock-smoke --limit 1 --no-musicdiff --render-dpi 200 --oemer-timeout 300
```

Result:

- 0/1 completed.
- `oemer` model inference completed, but upstream staff extraction failed with
  `ValueError: max() iterable argument is empty`.
- Manual preview showed the generated PDF was not a normal score page, so this
  failure is attributed to the local PDF rendering path, not yet to recognition
  accuracy.

## Next Step

Install or provide MuseScore CLI and regenerate the OpenScore PDFs from the same
MXL sources. Then rerun the same manifest before drawing quality conclusions.
