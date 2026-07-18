import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.legato_convert_wrapper import convert_abc_json_to_xml


def test_convert_abc_json_to_xml_writes_xml_json(tmp_path, monkeypatch):
    repo = tmp_path / "legato"
    (repo / "utils").mkdir(parents=True)
    abc2xml = repo / "utils" / "abc2xml.py"
    abc2xml.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("PDF2MUSE_LEGATO_REPO", str(repo))
    monkeypatch.setenv("PDF2MUSE_LEGATO_PYTHON", "python")

    abc_json = tmp_path / "page_single_abc.json"
    abc_json.write_text(
        json.dumps({"abc_transcription": ["X:1\nK:C\nC"]}),
        encoding="utf-8",
    )
    fake_xml = b'<?xml version="1.0"?><score-partwise></score-partwise>'

    with patch("scripts.legato_convert_wrapper.find_musescore_binary", return_value=None):
        with patch("scripts.legato_convert_wrapper.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_xml, stderr=b"")
            out = convert_abc_json_to_xml(abc_json, tmp_path / "tmp")

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0].startswith("<?xml")
    mock_run.assert_called_once()
