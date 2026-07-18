# Clean-Typeset Baseline Report

## Scope

This report records the first local clean-typeset benchmark pass after adding
the quality harness. The benchmark currently uses generated local fixtures,
not a public corpus. These results are regression signals only; they do not
establish production-level recognition quality.

## Fixture Set

- Manifest: `evaluation/manifests/clean-typeset.local.json`
- Generated files: `datasets/cache/clean-typeset-generated/`
- Samples generated: 20
- Source: generated locally by `scripts/clean_typeset_benchmark.py`
- License notes: no third-party score source; fixture PDFs and ground-truth
  MusicXML are generated locally.

## Runs

Stock smoke, 300 DPI:

`venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\clean-typeset.local.json --output evaluation\runs\clean-typeset-stock-smoke --limit 1 --no-musicdiff --oemer-timeout 90`

Result: 0/1 completed; `oemer` timed out after 90 seconds.

Stock smoke, 100 DPI:

`venv\Scripts\python.exe -m pdf2muse.cli evaluate evaluation\manifests\clean-typeset.local.json --output evaluation\runs\clean-typeset-stock-smoke-100dpi --limit 1 --no-musicdiff --render-dpi 100 --oemer-timeout 90`

Result: 0/1 completed; `oemer` timed out after 90 seconds.

Before the CPU-wrapper fix, the same smoke path failed with an ONNX Runtime CUDA
provider load error. The wrapper now forces `CPUExecutionProvider` even when
`oemer` requests providers explicitly, so this failure is now a reportable
runtime timeout instead of a provider crash.

## Failure Taxonomy

- Highest-impact current class: `pipeline` runtime failure.
- Observed symptom: no page-level MusicXML is produced before the timeout.
- Not yet measured: parseability rate, MuseScore import status, structural
  deltas, pitch/symbol accuracy, rhythm/voice accuracy, and OMR-NED.
- Degradation tests are not quality claims at this stage because the clean
  smoke sample has not completed successfully.

## Decisions

- First non-model fix accepted: force CPU execution in the `oemer` wrapper and
  add per-page `oemer` timeout reporting.
- First benchmark control accepted: expose `--render-dpi` so 200/300/400 DPI
  experiments can be recorded in conversion reports.
- First model decision: do not fine-tune yet. The current blocker is runtime
  completion on the clean generated fixture, so training would not be grounded
  in recognition-error evidence.

## Next Evidence Needed

- Run the same manifest on at least one real clean engraved score from a
  license-cleared source.
- If generated fixtures continue to time out but real engraved PDFs complete,
  treat the generated drawing style as an unsuitable benchmark input and keep it
  only as a pipeline stress fixture.
- If real engraved PDFs also time out, profile `oemer` page execution before
  changing model checkpoints.
