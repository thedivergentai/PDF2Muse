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
    assert "Convert PDF sheet music" in result.stdout

def test_convert_help():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "PDF_PATH" in result.stdout
    assert "--output" in result.stdout
