# OMR Output Comparison Baseline

PDF2Muse should evaluate OMR output in layers. The first layer answers whether an output can be consumed at all. Later layers compare musical structure and, where practical, edit distance against reference encodings.

## Baseline Gates

1. XML parseability: the output must be well-formed XML before any musical comparison is attempted.
2. MusicXML parseability: when the expected format is MusicXML, parse it with a symbolic-music library such as `music21` when available.
3. MuseScore import: optionally verify that MuseScore CLI can import the file, especially when producing `.mscx` or checking user-facing compatibility.

Failures at these gates should be reported separately from score quality. A non-parseable file is a conversion failure, not a low-similarity result.

## Practical Similarity Metrics

Use `musicdiff` or OMR-NED when available. These provide the most practical near-term comparison for symbolic OMR output because they operate closer to the musical structure than raw text diffs.

Recommended reporting:

- Parseability status for candidate and reference.
- `musicdiff` or OMR-NED score when the tool is installed and inputs are supported.
- Tool name, version if available, and command exit status.
- A clear "metric unavailable" status when optional dependencies are absent.

## Structural Fallbacks

When specialized metrics are unavailable, compare normalized structural counts:

- Parts.
- Measures.
- Notes.
- Rests.
- Pitches.

For each count, report candidate value, reference value, absolute difference, and normalized difference. These numbers are coarse and should be framed as regression signals, not musical accuracy.

## Later Metrics

Tree edit distance, including TEDn-style comparisons, is a later-stage option for small curated excerpts. It is best introduced after the harness has stable parsing, fixture manifests, and a few trusted reference pairs.

## Baseline Position

The project should publish evaluation output as reproducible evidence. Avoid high-accuracy claims until datasets, licensing, metrics, and conversion assumptions are all documented and repeatable.
