import json

from PIL import Image, ImageDraw

import pytest

from pdf2muse.degrade import degrade_directory


def create_score_like_image(path):
    image = Image.new("RGB", (80, 40), "white")
    draw = ImageDraw.Draw(image)
    for y in (8, 12, 16, 20, 24):
        draw.line((5, y, 75, y), fill="black", width=1)
    draw.ellipse((20, 13, 28, 21), fill="black")
    draw.line((28, 13, 28, 5), fill="black", width=1)
    image.save(path)


def test_degrade_directory_is_deterministic_for_same_seed(tmp_path):
    input_dir = tmp_path / "input"
    first_output = tmp_path / "out-a"
    second_output = tmp_path / "out-b"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    degrade_directory(input_dir, first_output, profile="scan-noise", seed=123)
    degrade_directory(input_dir, second_output, profile="scan-noise", seed=123)

    assert (first_output / "score.png").read_bytes() == (second_output / "score.png").read_bytes()


def test_degrade_directory_profiles_produce_different_outputs(tmp_path):
    input_dir = tmp_path / "input"
    noise_output = tmp_path / "noise"
    blur_output = tmp_path / "blur"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    degrade_directory(input_dir, noise_output, profile="scan-noise", seed=123)
    degrade_directory(input_dir, blur_output, profile="blur", seed=123)

    assert (noise_output / "score.png").read_bytes() != (blur_output / "score.png").read_bytes()


def test_degrade_directory_writes_metadata(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    degrade_directory(input_dir, output_dir, profile="low-contrast", seed=99, severity="heavy")

    metadata = json.loads((output_dir / "degradation_metadata.json").read_text(encoding="utf-8"))
    assert metadata["profile"] == "low-contrast"
    assert metadata["severity"] == "heavy"
    assert metadata["seed"] == 99
    assert metadata["profile_parameters"]["contrast_factor"] == 0.3
    assert metadata["files"][0]["input"] == "score.png"
    assert metadata["files"][0]["output"] == "score.png"
    assert metadata["files"][0]["parameters"]["contrast_factor"] == 0.3
    assert isinstance(metadata["files"][0]["parameters"]["seed"], int)


def test_degrade_directory_severity_changes_output(tmp_path):
    input_dir = tmp_path / "input"
    light_output = tmp_path / "light"
    heavy_output = tmp_path / "heavy"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    degrade_directory(input_dir, light_output, profile="blur", seed=7, severity="light")
    degrade_directory(input_dir, heavy_output, profile="blur", seed=7, severity="heavy")

    assert (light_output / "score.png").read_bytes() != (heavy_output / "score.png").read_bytes()


def test_degrade_directory_rejects_invalid_severity(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    with pytest.raises(ValueError, match="Unknown severity"):
        degrade_directory(input_dir, tmp_path / "out", profile="blur", severity="extreme")


def test_realistic_scan_profiles_are_deterministic(tmp_path):
    input_dir = tmp_path / "input"
    first_output = tmp_path / "out-a"
    second_output = tmp_path / "out-b"
    input_dir.mkdir()
    create_score_like_image(input_dir / "score.png")

    degrade_directory(input_dir, first_output, profile="jpeg-artifacts", seed=123, severity="medium")
    degrade_directory(input_dir, second_output, profile="jpeg-artifacts", seed=123, severity="medium")

    assert (first_output / "score.png").read_bytes() == (second_output / "score.png").read_bytes()
