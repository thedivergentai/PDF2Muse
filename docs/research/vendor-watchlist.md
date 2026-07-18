# PDF2Muse vendor watchlist

Quarterly review of upstream OMR, notation, and inference dependencies. Last updated: 2026-07-03.

## OMR engines

| Vendor | URL | Review focus |
|--------|-----|--------------|
| oemer | https://github.com/BreezeWhite/oemer | Checkpoint releases, ONNX compatibility |
| Legato | https://github.com/guang-yng/legato | GPU inference, ABC→MusicXML utils |
| Legato weights | https://huggingface.co/guangyangmusic/legato | Model size, license (MIT) |
| Transcoda | https://github.com/btrkeks/transcoda | OMR-NED benchmarks, `**kern` bridge |
| Audiveris | https://github.com/Audiveris/audiveris | MusicXML 4.0 export, AGPL implications |
| SMT++ | https://huggingface.co/PRAIG/smt-fp-grandstaff | Pianoform baseline comparator |

## Notation / UI

| Vendor | URL | Review focus |
|--------|-----|--------------|
| OpenSheetMusicDisplay | https://github.com/opensheetmusicdisplay/opensheetmusicdisplay | MusicXML render, TS API |
| Verovio | https://github.com/rism-digital/verovio | MEI/MusicXML, wasm toolkit |
| music21 | https://github.com/cuthbertLab/music21 | Join/validation helpers |
| musicdiff | https://github.com/guang-yng/musicdiff | OMR-NED evaluation |

## Inference runtime

| Vendor | URL | Review focus |
|--------|-----|--------------|
| ONNX Runtime | https://onnxruntime.ai/ | CPU/GPU wheels for Windows |
| pypdfium2 | https://github.com/pypdfium2-team/pypdfium2 | PDF render stability |

## Datasets

| Vendor | URL | Review focus |
|--------|-----|--------------|
| PDMX | https://github.com/sheetrock-ai/PDMX | License-cleared MusicXML |
| OpenScore | https://github.com/OpenScore/Lieder | CC0 ground truth |

## Cadence

- **Monthly:** oemer, ONNX Runtime security advisories
- **Quarterly:** full table review after clean-typeset benchmark run
- **Before backend swap:** run manifest evaluation and update `docs/evaluation/*-report-v2.md`
