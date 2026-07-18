# Degradation Robustness Loop

## Current Gate

Do not use degraded benchmark results as quality claims until the clean
clean-typeset baseline produces MusicXML. The current generated clean smoke
sample times out before page-level MusicXML is produced, so degraded runs would
only measure the same runtime blocker.

## Tooling Added

`scripts/degrade_benchmark.py` creates degraded-PDF manifests from an existing
evaluation manifest:

```powershell
venv\Scripts\python.exe scripts\degrade_benchmark.py evaluation\manifests\clean-typeset.local.json --output-dir datasets\cache\clean-typeset-low-contrast-light --output-manifest evaluation\manifests\clean-typeset-low-contrast-light.local.json --profile low-contrast --severity light --limit 3
```

The script:

- Renders the first page of each source PDF.
- Applies one deterministic degradation profile.
- Wraps the degraded image back into a PDF.
- Reuses the original ground-truth MusicXML.
- Adds `degraded-<profile>` and `severity-<severity>` tags to the manifest.

## When To Run It

Run this loop only after a clean benchmark sample completes successfully, and
only for observed real-world failure modes such as low contrast, scan noise,
shadowing, JPEG artifacts, or skew.

The degraded run should be compared against the matching clean run with the same
ground truth. Reports should label degraded output as a robustness stress test,
not an accuracy guarantee.
