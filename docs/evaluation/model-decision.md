# Model Decision Gate

## Decision

Continue benchmark/rendering and evaluation work before `oemer` fine-tuning or
replacement-model integration.

## Evidence

- The generated clean-typeset smoke baseline did not produce MusicXML.
- At both 300 DPI and 100 DPI, `oemer` timed out after 90 seconds on the first
  generated clean fixture.
- A pre-fix run exposed an ONNX Runtime CUDA provider failure even through the
  CPU wrapper. That has been fixed by forcing `CPUExecutionProvider`.
- A real public-domain Mutopia PDF now completes with a 300-second page timeout
  and produces parseable MusicXML.
- The OpenScore CC0 lane has suitable symbolic ground truth, but local PDF
  rendering is not yet benchmark-quality without MuseScore CLI.
- There is still no measured staff/layout, symbol, rhythm, voice, or MusicXML
  delta evidence on a ground-truth public benchmark.

## Fine-Tuning Status

Do not fine-tune `unet_big` or `seg_net` yet. A fine-tuning run would not be
grounded in benchmark evidence until the stock backend completes on clean
license-cleared samples and failures can be attributed to layout or symbol
recognition.

`oemer-custom` remains a reserved slot for future checkpoint experiments, but it
must not be used for model claims until a no-op copied-checkpoint control proves
that `--checkpoint-dir` actually redirects installed `oemer` inference.

## Replacement Adapter Status

`legato-experimental` should remain non-runnable in normal conversion. A
replacement adapter is worth revisiting only after a clean stock baseline exists
or if `oemer` cannot complete on real clean engraved inputs after runtime
profiling.

## Next Model Gate

Re-open model work when at least one clean benchmark run produces MusicXML and
the top failure categories are known. Choose:

- `unet_big` fine-tuning if staff/layout failures dominate.
- `seg_net` fine-tuning if symbol segmentation failures dominate.
- A replacement adapter if structural, rhythm, or voice errors dominate beyond
  what `oemer` can plausibly represent.
- More pipeline work if runtime, rendering, merge, or import failures dominate.
