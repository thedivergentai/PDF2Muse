# Degradation Calibration Research Note

## 5-Bullet Summary

- Current degradation support is deterministic and useful for smoke-level robustness experiments, but profile strength is fixed inside `degrade_image`.
- Calibration should introduce explicit severity levels while keeping the existing `profile` and `seed` model stable and reproducible.
- Recommended profiles should map to realistic scan conditions: clean scan variance, scanner noise, camera blur, low contrast, uneven illumination, and compression artifacts.
- Metadata should record resolved numeric parameters per output image so evaluation results can be traced back to exact degradation settings.
- Tests should focus on determinism, parameter validation, CLI delegation, metadata shape, and profile/severity behavior without running slow OMR conversion.

## Existing Behavior

`src/pdf2muse/degrade.py` exposes `degrade_directory(input_dir, output_dir, profile="scan-noise", seed=0)` and `degrade_image(image, profile, seed)`. `degrade_directory` walks supported image extensions recursively, derives a stable per-image seed from the user seed and relative path, writes transformed images to the matching output path, and writes `degradation_metadata.json` with `profile`, `seed`, and input/output relative paths.

The current profiles are fixed presets:

- `scan-noise`: grayscale conversion, contrast reduced to `0.85`, sparse salt/pepper pixels at about 1.25% of pixels, and Gaussian blur radius `0.25`.
- `blur`: Gaussian blur radius `1.1`.
- `low-contrast`: contrast reduced to `0.45`.
- `shadow`: vertical lighting gradient from `0.65` at the top to `1.0` at the bottom.

The CLI command `pdf2muse degrade INPUT_DIR OUTPUT_DIR --profile scan-noise --seed 123` delegates directly to `degrade_directory`. Current CLI tests cover help output and delegation arguments, but there are no direct tests for image output determinism, metadata contents, unsupported profiles, recursive paths, or realistic scan calibration.

The docs already frame degradation as experimental and advise using baseline evaluation results before expanding synthetic data. That framing should stay: degraded data is for robustness experiments and evaluation stress tests, not evidence of model improvement by itself.

## Recommended Deterministic Parameter/Severity Design

Keep the public model simple: `profile`, `severity`, and `seed`. Add `severity` as an enum such as `mild`, `moderate`, and `severe`, with `moderate` as the default only after confirming compatibility expectations for existing users. If compatibility matters more, keep current behavior as `legacy` or retain current constants for `scan-noise` without a severity argument.

Represent each profile as a deterministic parameter resolver:

- Inputs: `profile`, `severity`, image dimensions, and derived per-image seed.
- Output: a frozen parameter object containing all numeric values used for the transform.
- Metadata: include `profile`, `severity`, top-level `seed`, per-file derived seed, and resolved per-file parameters.

This design keeps stochastic-looking degradation reproducible and makes evaluation reports auditable. The seed should continue to be derived from the relative path so adding one file does not change all other outputs.

Suggested first-pass severity table:

| Profile | Mild | Moderate | Severe |
| --- | --- | --- | --- |
| `scan-noise` | contrast `0.9`, noise `0.25%`, blur `0.15` | contrast `0.8`, noise `0.75%`, blur `0.35` | contrast `0.65`, noise `1.5%`, blur `0.6` |
| `blur` | radius `0.4` | radius `0.9` | radius `1.5` |
| `low-contrast` | contrast `0.75` | contrast `0.55` | contrast `0.35` |
| `shadow` | gradient `0.85..1.0` | gradient `0.7..1.0` | gradient `0.55..1.0` |
| `jpeg-compression` | quality `85` | quality `65` | quality `45` |
| `camera-soft` | blur `0.35`, rotation <= `0.25 deg` | blur `0.7`, rotation <= `0.5 deg` | blur `1.1`, rotation <= `1.0 deg` |

Realistic scan profiles should be compositional presets rather than arbitrary image filters. For example:

- `scanner-office`: mild contrast loss, light salt/pepper noise, small blur.
- `scanner-aged-paper`: yellowed background or low contrast plus uneven illumination.
- `phone-flat`: mild perspective or rotation, camera blur, JPEG compression.
- `phone-shadow`: uneven lighting gradient, local dark banding, moderate blur.
- `photocopy`: reduced contrast, threshold-like tonal compression, sparse speckles.

Do not add all profiles at once. Start with severity for existing profiles, then add one or two realistic composites after baseline evaluation identifies common failure modes.

## Tests To Add

- Unit tests for `degrade_image` showing the same image, profile, severity, and seed produce byte-identical output.
- Unit tests that different severities produce measurably different outputs for each supported profile.
- Unit tests for invalid `profile` and invalid `severity` errors with clear messages.
- Directory tests verifying recursive input preservation, metadata contents, sorted processing, per-file derived seeds, and exact resolved parameters.
- CLI tests covering `--severity`, default behavior, invalid option handling, and delegation to `degrade_directory`.
- Regression tests with tiny synthetic images for `scan-noise`, `blur`, `low-contrast`, and `shadow`; keep fixtures small and avoid running full OMR conversion.
- Documentation tests or snapshot checks only if the project already adopts that pattern; otherwise keep docs manually reviewed.

## Risks

- Artificial degradation can overfit evaluation to synthetic artifacts instead of real scanner and camera failure modes.
- Severe blur, shadow, or compression can produce images that no longer represent plausible sheet-music scans.
- Adding many profiles before baseline evaluation may create maintenance cost without improving measurement quality.
- Metadata schema changes can break downstream scripts if consumers start depending on the current minimal JSON shape.
- Randomized transforms can become non-reproducible if any operation depends on global RNG state, filesystem ordering, library version-specific behavior, or unstated image mode conversions.
- Degraded images should not be used to claim conversion accuracy improvements unless measured against held-out ground truth with documented evaluation reports.
