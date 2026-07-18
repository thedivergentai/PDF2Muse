# Public Score Smoke Report

## Asset

- Source: Mutopia Project
- Piece page: `https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=75`
- PDF: `https://www.mutopiaproject.org/ftp/BachJS/BWVAnh114/anna-magdalena-04/anna-magdalena-04-a4.pdf`
- Copyright status on source page: Public Domain
- Local path: `datasets/raw/public-scores/mutopia-bach-menuet-75/anna-magdalena-04-a4.pdf`

This is a public PDF smoke test only. It does not include trusted MusicXML
ground truth, so it cannot produce structural accuracy or OMR-NED scores.

## Command

```powershell
venv\Scripts\python.exe -m pdf2muse.cli convert datasets\raw\public-scores\mutopia-bach-menuet-75\anna-magdalena-04-a4.pdf --output evaluation\runs\public-score-smoke\mutopia-bach-menuet-75 --first-page 1 --last-page 1 --render-dpi 200 --oemer-timeout 120
```

## Result

- The 120-second smoke timed out after reaching late `oemer` extraction stages.
- The 300-second bounded run completed and wrote parseable MusicXML.
- Conversion report: `evaluation/runs/public-score-smoke/mutopia-bach-menuet-75-300s/conversion_report.json`
- Output: `evaluation/runs/public-score-smoke/mutopia-bach-menuet-75-300s/combined.musicxml`
- Structural counts from the generated MusicXML: 1 part, 33 measures, 221 notes,
  17 rests, and 204 pitched notes.
- MuseScore `.mscx` export was skipped because MuseScore CLI is not installed in
  this environment.

## Interpretation

The real public score smoke shows that stock `oemer` can complete on a clean
public PDF when the page timeout is high enough. The generated fixture timeout
was not enough evidence to reject `oemer`; the immediate runtime fix is to keep
diagnostics enabled and use realistic page timeouts for CPU runs.

This is still not an accuracy benchmark because this Mutopia PDF does not have
trusted MusicXML ground truth attached in the local manifest.
