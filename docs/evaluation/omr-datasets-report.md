# OMR Dataset Candidates

This note captures practical dataset options for evaluating PDF2Muse OMR output during the beta revival. Prefer datasets with accessible page images and ground-truth symbolic files, then expand to specialized corpora as the harness matures.

## Primary Candidates

### DoReMi

- Source: GitHub `steinbergmedia/DoReMi`.
- Scale: about 5,218 release pages and about 6,432 reported images.
- Formats: PNG, MusicXML, MEI, MIDI, and OMR XML.
- Strengths: large, modern, multi-format corpus with page-level assets.
- Risks: license status is unclear and must be resolved before redistribution or formal benchmarking.

### OpenScore Lieder and StringQuartets

- Source: OpenScore-derived MusicXML, PDF, MuseScore, and rendered page images.
- Scale: StringQuartets includes 252 page examples.
- License: derived assets are described as CC BY 4.0; StringQuartets access requires accepting Hugging Face terms.
- Strengths: useful for engraved-score tests and MusicXML alignment.
- Risks: verify exact dataset terms before automation or public reports.

### Debussy Full-Page Handwritten

- Source: Hugging Face `HugoSchtr/debussy-omr-fullpage-lvl`.
- Scale: 101 JPEG pages, test split, about 239 MB.
- Formats: JPEG page images and MusicXML ground truth.
- Strengths: small, easy to inspect in the HF viewer, and suitable for quick handwritten smoke tests.
- Risks: narrow composer/style coverage.

### MusiCorpus

- Scale: 1,309 historical and handwritten pages.
- Formats: `image.jpg`, `transcription.musicxml`, and COCO annotations.
- Strengths: stable handle, mixed historical material, and useful annotations beyond MusicXML.
- Risks: historical notation may need curated subsets before comparing against modern OMR output.

### CollabScore

- Scale: 199 pages.
- Formats: IIIF images and MEI ground truth.
- Strengths: includes OMR comparison tooling and MEI references.
- Risks: requires MEI-aware evaluation or conversion when comparing against MusicXML output.

### zzsi/openscore

- Source: rendered OpenScore pages with per-page MusicXML.
- Strengths: straightforward page-to-MusicXML evaluation candidate.
- Risks: confirm provenance, licensing, and data splits before treating results as benchmark numbers.

## Secondary Specialized Options

- GrandStaff-LMX: useful for staff-focused or layout-aware experiments.
- PrIMuS and Camera-PrIMuS: useful for monophonic or camera-degraded notation tasks.
- DeepScoresV2: useful for large-scale symbol and detection-oriented evaluation.
- MUSCIMA++: useful for handwritten symbol and staff/object analysis.

## Recommended Use

Start with small, inspectable subsets from Debussy, MusiCorpus, CollabScore, and OpenScore-derived material. Keep DoReMi as a high-value candidate once licensing is clarified. Report all results as beta evaluation signals, not accuracy claims.
