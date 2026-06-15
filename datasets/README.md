# Local Dataset Workspace

Use this directory for local Optical Music Recognition datasets that are too
large or license-sensitive to commit.

Tracked files in this directory should stay small and instructional. Raw data,
download caches, third-party score images, and generated dataset variants belong
under ignored paths:

- `datasets/raw/`
- `datasets/cache/`

Recommended workflow:

1. Read `docs/evaluation/omr-datasets-report.md`.
2. Download or prepare a small local subset outside git.
3. Store raw files under `datasets/raw/<dataset-name>/`.
4. Create a local manifest under `evaluation/manifests/`.
5. Run `pdf2muse evaluate` with a small `--limit` before attempting larger runs.

Do not commit raw dataset files unless the license is clear and the repository
intentionally includes them.
