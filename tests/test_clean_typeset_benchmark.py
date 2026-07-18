import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pdf2muse.evaluation import load_manifest, parse_musicxml
from scripts.clean_typeset_benchmark import create_clean_typeset_benchmark


def test_create_clean_typeset_benchmark_writes_manifest_and_samples(tmp_path, mock_musescore):
    output_dir = tmp_path / "generated"
    manifest = tmp_path / "manifests" / "clean-typeset.local.json"

    samples = create_clean_typeset_benchmark(
        output_dir=output_dir,
        manifest_path=manifest,
        sample_count=3,
    )

    assert len(samples) == 3
    assert manifest.exists()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(manifest_data["samples"]) == 3
    assert manifest_data["samples"][0]["source"] == "generated-local-clean-typeset"
    assert "generated-fixture" in manifest_data["samples"][0]["difficulty_tags"]
    assert "musescore-rendered" in manifest_data["samples"][0]["difficulty_tags"]
    assert "oemer-smoke" in manifest_data["samples"][0]["difficulty_tags"]
    assert "multi-measure" in manifest_data["samples"][0]["difficulty_tags"]
    assert manifest_data["samples"][0]["input_quality"]["trusted_for_accuracy"] is True
    assert samples[0].pdf_path.exists()
    assert samples[0].musicxml_path.exists()
    assert parse_musicxml(samples[0].musicxml_path).ok is True
    tree = ET.parse(samples[0].musicxml_path)
    measures = tree.findall(".//measure")
    assert len(measures) >= 12
    notes = tree.findall(".//note")
    assert len(notes) >= 48
    assert tree.find(".//octave").text in {"4", "5"}
    assert tree.find(".//type").text in {"quarter", "eighth", "half", "whole"}


def test_create_clean_typeset_benchmark_manifest_loads(tmp_path, mock_musescore):
    output_dir = tmp_path / "generated"
    manifest = tmp_path / "manifests" / "clean-typeset.local.json"

    create_clean_typeset_benchmark(
        output_dir=output_dir,
        manifest_path=manifest,
        sample_count=2,
    )

    loaded = load_manifest(manifest)

    assert len(loaded) == 2
    assert loaded[0].input_path.exists()
    assert loaded[0].ground_truth_path.exists()
    assert loaded[0].trusted_for_accuracy is True


def test_create_clean_typeset_benchmark_requires_musescore(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.clean_typeset_benchmark.find_musescore_binary",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(RuntimeError, match="MuseScore CLI is required"):
        create_clean_typeset_benchmark(
            output_dir=tmp_path / "generated",
            manifest_path=tmp_path / "manifest.json",
            sample_count=1,
        )
