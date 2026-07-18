import json

import pytest

from pdf2muse.evaluation import load_manifest
from scripts.clean_typeset_benchmark import create_clean_typeset_benchmark
from scripts.degrade_benchmark import create_degraded_benchmark


def test_create_degraded_benchmark_writes_pdf_manifest(tmp_path, mock_musescore):
    clean_manifest = tmp_path / "manifests" / "clean.json"
    create_clean_typeset_benchmark(
        output_dir=tmp_path / "clean",
        manifest_path=clean_manifest,
        sample_count=2,
    )
    degraded_manifest = tmp_path / "manifests" / "degraded.json"

    count = create_degraded_benchmark(
        manifest_path=clean_manifest,
        output_dir=tmp_path / "degraded",
        output_manifest=degraded_manifest,
        profile="low-contrast",
        severity="light",
        seed=123,
        render_dpi=100,
        limit=1,
    )

    assert count == 1
    samples = load_manifest(degraded_manifest)
    assert len(samples) == 1
    assert samples[0].input_path.exists()
    assert samples[0].input_path.suffix == ".pdf"
    assert samples[0].ground_truth_path.exists()
    assert "degraded-low-contrast" in samples[0].difficulty_tags
    assert "severity-light" in samples[0].difficulty_tags
    assert samples[0].trusted_for_accuracy is False
    assert samples[0].input_quality["renderer"] == "degraded-from-trusted"


def test_create_degraded_benchmark_rejects_multi_page_samples(tmp_path, mock_musescore):
    clean_manifest = tmp_path / "manifests" / "clean.json"
    create_clean_typeset_benchmark(
        output_dir=tmp_path / "clean",
        manifest_path=clean_manifest,
        sample_count=1,
    )
    data = json.loads(clean_manifest.read_text(encoding="utf-8"))
    data["samples"][0]["last_page"] = 2
    clean_manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="single-page"):
        create_degraded_benchmark(
            manifest_path=clean_manifest,
            output_dir=tmp_path / "degraded",
            output_manifest=tmp_path / "manifests" / "degraded.json",
            profile="low-contrast",
            severity="light",
        )
