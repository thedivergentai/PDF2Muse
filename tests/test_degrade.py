import json

from PIL import Image, ImageDraw

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

    degrade_directory(input_dir, output_dir, profile="low-contrast", seed=99)

    metadata = json.loads((output_dir / "degradation_metadata.json").read_text(encoding="utf-8"))
    assert metadata["profile"] == "low-contrast"
    assert metadata["seed"] == 99
    assert metadata["files"][0]["input"] == "score.png"
    assert metadata["files"][0]["output"] == "score.png"
