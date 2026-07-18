# OMR model benchmark report

Generated: 2026-07-05T06:14:33.601907+00:00

## Variants

| Variant | Backend | Device | Quality | Completed | Failed | Notes |
|---------|---------|--------|---------|-----------|--------|-------|
| oemer-cpu-quality | oemer-stock | cpu | quality | 3/3 | 0 | oemer_failed |
| oemer-cuda-quality | oemer-stock | cuda | quality | 2/3 | 1 | oemer_failed |
| oemer-cuda-balanced | oemer-stock | cuda | balanced | 3/3 | 0 | oemer_failed |
| legato-small | legato-experimental | cuda | quality | 0/3 | 3 | no conversion_report failure_class |

## Recommended settings

- **Best variant in this run:** `oemer-cpu-quality` (3/3 completed)
- Use `--model-backend oemer-stock --oemer-device cpu --oemer-quality-profile quality` for CLI/UI.

## Raw summaries

### oemer-cpu-quality

```json
{
  "variant": "oemer-cpu-quality",
  "model_backend": "oemer-stock",
  "oemer_device": "cpu",
  "oemer_quality_profile": "quality",
  "exit_code": 0,
  "total_samples": 3,
  "completed_samples": 3,
  "failed_samples": 0,
  "skipped_samples": 0,
  "failure_categories": {},
  "metric_summaries": {
    "ground_truth_parse_ok": {
      "failed": 0,
      "passed": 3
    },
    "musescore_import_status": {
      "not_configured": 3
    },
    "musicdiff_status": {
      "disabled": 3
    },
    "omr_ned": {
      "average": null,
      "count": 0,
      "maximum": null,
      "minimum": null
    },
    "predicted_parse_ok": {
      "failed": 0,
      "passed": 3
    }
  },
  "median_omr_ned": null,
  "dominant_failure_class": "oemer_failed"
}
```

### oemer-cuda-quality

```json
{
  "variant": "oemer-cuda-quality",
  "model_backend": "oemer-stock",
  "oemer_device": "cuda",
  "oemer_quality_profile": "quality",
  "exit_code": 0,
  "total_samples": 3,
  "completed_samples": 2,
  "failed_samples": 1,
  "skipped_samples": 0,
  "failure_categories": {
    "timeout": 1
  },
  "metric_summaries": {
    "ground_truth_parse_ok": {
      "failed": 0,
      "passed": 2
    },
    "musescore_import_status": {
      "not_configured": 2,
      "not_run": 1
    },
    "musicdiff_status": {
      "disabled": 2,
      "not_run": 1
    },
    "omr_ned": {
      "average": null,
      "count": 0,
      "maximum": null,
      "minimum": null
    },
    "predicted_parse_ok": {
      "failed": 0,
      "passed": 2
    }
  },
  "median_omr_ned": null,
  "dominant_failure_class": "oemer_failed"
}
```

### oemer-cuda-balanced

```json
{
  "variant": "oemer-cuda-balanced",
  "model_backend": "oemer-stock",
  "oemer_device": "cuda",
  "oemer_quality_profile": "balanced",
  "exit_code": 0,
  "total_samples": 3,
  "completed_samples": 3,
  "failed_samples": 0,
  "skipped_samples": 0,
  "failure_categories": {},
  "metric_summaries": {
    "ground_truth_parse_ok": {
      "failed": 0,
      "passed": 3
    },
    "musescore_import_status": {
      "not_configured": 3
    },
    "musicdiff_status": {
      "disabled": 3
    },
    "omr_ned": {
      "average": null,
      "count": 0,
      "maximum": null,
      "minimum": null
    },
    "predicted_parse_ok": {
      "failed": 0,
      "passed": 3
    }
  },
  "median_omr_ned": null,
  "dominant_failure_class": "oemer_failed"
}
```

### legato-small

```json
{
  "variant": "legato-small",
  "model_backend": "legato-experimental",
  "oemer_device": "cuda",
  "oemer_quality_profile": "quality",
  "exit_code": 0,
  "total_samples": 3,
  "completed_samples": 0,
  "failed_samples": 3,
  "skipped_samples": 0,
  "failure_categories": {
    "pipeline": 3
  },
  "metric_summaries": {
    "ground_truth_parse_ok": {
      "failed": 0,
      "passed": 0
    },
    "musescore_import_status": {
      "not_run": 3
    },
    "musicdiff_status": {
      "not_run": 3
    },
    "omr_ned": {
      "average": null,
      "count": 0,
      "maximum": null,
      "minimum": null
    },
    "predicted_parse_ok": {
      "failed": 0,
      "passed": 0
    }
  },
  "median_omr_ned": null,
  "dominant_failure_class": "no conversion_report failure_class"
}
```
