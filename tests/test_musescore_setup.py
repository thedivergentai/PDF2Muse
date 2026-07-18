import subprocess
from pathlib import Path

from scripts.musescore_setup import (
    MuseScoreSetupResult,
    find_musescore_executable,
    setup_musescore_portable,
    validate_musescore_can_export,
)


def test_find_musescore_executable_prefers_custom_path(tmp_path):
    custom = tmp_path / "MuseScore4.exe"
    custom.write_text("fake executable", encoding="utf-8")

    assert find_musescore_executable(custom_path=custom) == custom


def test_find_musescore_executable_searches_portable_tools_dir(tmp_path, monkeypatch):
    portable = tmp_path / "MuseScorePortable" / "App" / "MuseScore" / "bin" / "MuseScore4.exe"
    portable.parent.mkdir(parents=True)
    portable.write_text("fake executable", encoding="utf-8")
    monkeypatch.setattr("scripts.musescore_setup.find_existing_musescore_binary", lambda _: None)

    assert find_musescore_executable(tools_dir=tmp_path) == portable


def test_setup_musescore_portable_downloads_installer_when_missing(tmp_path, monkeypatch):
    downloads = []

    def fake_download(url, target):
        downloads.append((url, target))
        target.write_bytes(b"installer")

    monkeypatch.setattr("scripts.musescore_setup.find_musescore_executable", lambda **_: None)
    monkeypatch.setattr("scripts.musescore_setup._download_file", fake_download)
    monkeypatch.setattr("scripts.musescore_setup.subprocess.run", lambda *_, **__: None)

    result = setup_musescore_portable(tools_dir=tmp_path)

    assert isinstance(result, MuseScoreSetupResult)
    assert result.status == "installer_downloaded"
    assert result.installer_path == tmp_path / "MuseScorePortable_4.6.5.paf.exe"
    assert downloads[0][1] == result.installer_path


def test_setup_musescore_portable_reports_installer_failure(tmp_path, monkeypatch):
    installer = tmp_path / "MuseScorePortable_4.6.5.paf.exe"
    installer.write_bytes(b"installer")
    monkeypatch.setattr("scripts.musescore_setup.find_musescore_executable", lambda **_: None)

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="install failed")

    monkeypatch.setattr("scripts.musescore_setup.subprocess.run", fake_run)

    result = setup_musescore_portable(tools_dir=tmp_path, run_installer=True)

    assert result.status == "installer_failed"
    assert "install failed" in result.message


def test_validate_musescore_can_export_uses_output_before_input(tmp_path, monkeypatch):
    musescore = tmp_path / "MuseScore4.exe"
    source = tmp_path / "source.mscx"
    target = tmp_path / "target.musicxml"
    musescore.write_text("fake executable", encoding="utf-8")
    source.write_text("<museScore></museScore>", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        target.write_text("<score-partwise><part-list/><part/></score-partwise>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("scripts.musescore_setup.subprocess.run", fake_run)

    validate_musescore_can_export(musescore, source, target)

    assert calls == [[str(musescore), "-o", str(target), str(source)]]
