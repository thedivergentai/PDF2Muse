import re
from unittest.mock import patch

from typer.testing import CliRunner

from pdf2muse.cli import app
from pdf2muse import __version__

runner = CliRunner()
# Rich's option highlighter emits a reset between the two dashes when color is
# forced (GitHub Actions). Compare help text after stripping those codes.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    stdout = _plain(result.stdout)
    assert "PDF2Muse" in stdout
    assert "Generate draft MusicXML" in stdout
    for option in ("--output", "--no-deskew", "--use-tf", "--save-cache", "--verbose"):
        assert option in stdout

def test_convert_help():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    help_text = _plain(result.stdout).lower()
    assert "pdf_path" in help_text or "pdf-path" in help_text
    assert "--output" in help_text
    assert "--render-dpi" in help_text
    assert "--oemer-timeout" in help_text
    assert "--model-backend" in help_text
    assert "--checkpoint-dir" in help_text
    assert "--header-lock" in help_text
    assert "--preview" in help_text
    assert "homr" in help_text
    assert "homr-experimental" in help_text


def test_evaluate_help():
    result = runner.invoke(app, ["evaluate", "--help"])
    assert result.exit_code == 0
    help_text = _plain(result.stdout).lower()
    assert "manifest" in help_text
    assert "--output" in help_text
    assert "--no-musicdiff" in help_text
    assert "--musescore-path" in help_text
    assert "--render-dpi" in help_text
    assert "--oemer-timeout" in help_text
    assert "--oemer-device" in help_text


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
    help_text = _plain(result.stdout).lower()
    assert "input_dir" in help_text or "input-dir" in help_text
    assert "output_dir" in help_text or "output-dir" in help_text
    assert "--profile" in help_text
    assert "--severity" in help_text
    assert "--seed" in help_text


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
