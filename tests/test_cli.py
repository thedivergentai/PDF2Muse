from unittest.mock import patch

from typer.testing import CliRunner

from pdf2muse.cli import app
from pdf2muse import __version__

runner = CliRunner()

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "PDF2Muse" in result.stdout
    assert "Generate draft MusicXML" in result.stdout
    for option in ("--output", "--no-deskew", "--use-tf", "--save-cache", "--verbose"):
        assert option in result.stdout

def test_convert_help():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "PDF_PATH" in result.stdout
    assert "--output" in result.stdout
    assert "--render-dpi" in result.stdout
    assert "--oemer-timeout" in result.stdout
    assert "--model-backend" in result.stdout
    assert "--checkpoint-dir" in result.stdout
    assert "--preview" in result.stdout


def test_evaluate_help():
    result = runner.invoke(app, ["evaluate", "--help"])
    assert result.exit_code == 0
    assert "MANIFEST" in result.stdout
    assert "--output" in result.stdout
    assert "--no-musicdiff" in result.stdout
    assert "--musescore-path" in result.stdout
    assert "--render-dpi" in result.stdout
    assert "--oemer-timeout" in result.stdout
    assert "--oemer-device" in result.stdout


@patch("pdf2muse.cli.run_evaluation")
def test_evaluate_delegates_to_runner(mock_run, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"samples": []}', encoding="utf-8")
    output = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "evaluate",
            str(manifest),
            "--output",
            str(output),
            "--limit",
            "2",
            "--render-dpi",
            "400",
            "--oemer-timeout",
            "30",
            "--oemer-device",
            "cuda",
            "--no-musicdiff",
        ],
    )

    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        manifest_path=manifest,
        output_dir=output,
        limit=2,
        first_page=None,
        last_page=None,
        use_musicdiff=False,
        musescore_path=None,
        model_backend="auto",
        checkpoint_dir=None,
        render_dpi=400,
        oemer_timeout_seconds=30,
        oemer_device="cuda",
        oemer_quality_profile="quality",
        allow_untrusted_inputs=False,
        force=False,
    )


def test_degrade_help():
    result = runner.invoke(app, ["degrade", "--help"])
    assert result.exit_code == 0
    assert "INPUT_DIR" in result.stdout
    assert "OUTPUT_DIR" in result.stdout
    assert "--profile" in result.stdout
    assert "--severity" in result.stdout
    assert "--seed" in result.stdout


@patch("pdf2muse.cli.degrade_directory")
def test_degrade_delegates_to_runner(mock_degrade, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "degrade",
            str(input_dir),
            str(output_dir),
            "--profile",
            "scan-noise",
            "--severity",
            "heavy",
            "--seed",
            "42",
        ],
    )

    assert result.exit_code == 0
    mock_degrade.assert_called_once_with(
        input_dir=input_dir,
        output_dir=output_dir,
        profile="scan-noise",
        severity="heavy",
        seed=42,
    )
