# MuseScore.com Local Benchmark Loop

This workflow builds a local benchmark from MuseScore.com score pages where you
can obtain matching PDF, MusicXML, and MuseScore-native files. It is intended for
quality measurement and regression checks, not for redistributing downloaded
assets.

## Why This Exists

Earlier PDF smoke checks proved that PDF2Muse can produce parseable MusicXML for
at least one public score with a longer `oemer` timeout, but they did not provide
paired symbolic ground truth. A MuseScore.com triplet gives us:

- `input.pdf` as the same print-style input a user would upload.
- `ground_truth.musicxml` as the symbolic comparison target.
- `source.mscx` as a MuseScore-native validation target.

The benchmark still does not prove broad accuracy by itself. It provides a
repeatable way to measure current behavior on a small, inspectable set of clean
typeset scores.

## Access Constraints

MuseScore.com does not expose a supported public download API. Direct automated
fetches can return HTTP 403, and unofficial downloader tools may fail when the
site changes or bot detection appears. The collection script therefore separates
acquisition status from OMR status:

- `complete` means local PDF, MusicXML, and `.mscx` files are present and the
  MusicXML parses.
- `pdf_blocked` means PDF acquisition failed before PDF2Muse ran.
- `incomplete` means one or more of PDF, MusicXML, or `.mscx` is missing.
- `ground_truth_parse_failed` means the source MusicXML is not usable as truth.
- `mscx_validation_failed` means MuseScore CLI could not load/export the source
  `.mscx`.

Only complete samples are written to `evaluation/manifests/musescore-com.local.json`.

## Setup

Use the project virtual environment:

```powershell
.\venv\Scripts\python.exe scripts\musescore_setup.py --setup-portable --tools-dir datasets\tools\musescore
```

If the helper only downloads `MuseScorePortable_4.6.5.paf.exe`, run or install
the portable package into `datasets\tools\musescore`, then rerun the setup
helper. You can also pass an existing executable directly to later commands with
`--musescore-path`.

For browser-assisted MuseScore.com downloads, install the evaluation extras and
Playwright browser runtime:

```powershell
.\venv\Scripts\pip.exe install -e ".[eval]"
.\venv\Scripts\python.exe -m playwright install chromium
```

## Collect About 10 Scores

Create a URL list:

```powershell
New-Item -ItemType Directory -Force datasets\benchmark-sources\musescore-com
notepad datasets\benchmark-sources\musescore-com\urls.txt
```

Put one MuseScore.com score URL per line. Prefer public-domain or original work
scores where you can legally access the download formats.

Run the loop:

```powershell
.\venv\Scripts\python.exe scripts\musescore_com_benchmark.py --urls-file datasets\benchmark-sources\musescore-com\urls.txt --limit 10 --allow-unofficial-downloader --setup-musescore-portable
```

For each score, the script creates a folder named like
`datasets\benchmark-sources\musescore-com\musescore-123456`. If official browser
downloads are needed, place the downloaded files in that folder and rerun the
same command. The script recognizes `.pdf`, `.musicxml`, `.xml`, `.mxl`,
`.mscx`, and `.mscz` files.

## Interactive Browser Login

To use a real MuseScore.com login without sharing credentials with an agent, run
the browser-assisted loop:

```powershell
.\venv\Scripts\python.exe scripts\musescore_com_benchmark.py --urls-file datasets\benchmark-sources\musescore-com\urls.txt --limit 20 --interactive-browser-downloads --setup-musescore-portable
```

The script opens a persistent local Chromium profile under
`datasets\tools\musescore-browser-profile`. Log into MuseScore.com in that
browser window. For each score page, use the site's download menu to download
PDF, MusicXML or MXL, and MSCX or MSCZ. When those downloads finish, press Enter
in the terminal and the script advances to the next URL.

The browser helper records page downloads and saves them in the matching sample
folder. Rerunning the command reuses the same browser profile and validates any
files already collected.

## Outputs

The collection loop writes:

- `datasets/benchmark-sources/musescore-com/collection_status.json`
- `datasets/benchmark-sources/musescore-com/browser_download_status.json`
- `evaluation/manifests/musescore-com.local.json`

Downloaded assets and generated manifests are local benchmark data. They are
ignored by git and should not be committed unless the redistribution license is
clear.

## Run PDF2Muse Evaluation

After the manifest contains complete samples:

```powershell
.\venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\musescore-com.local.json --output evaluation\runs\musescore-com-smoke --limit 10 --first-page 1 --last-page 1 --render-dpi 300 --oemer-timeout 900 --musescore-path path\to\MuseScore4.exe
```

The report records parseability, structural count differences, optional
`musicdiff`/OMR-NED results, and MuseScore import status for PDF2Muse's
predicted MusicXML. The generated output should still be reviewed manually in
MuseScore or another notation editor.
