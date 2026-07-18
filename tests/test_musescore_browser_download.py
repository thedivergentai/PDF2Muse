from pathlib import Path

from scripts.musescore_browser_download import (
    BrowserDownloadResult,
    collect_browser_downloads,
    download_score_interactively,
)


class FakeDownload:
    def __init__(self, filename: str):
        self.suggested_filename = filename
        self.saved_to = None

    def save_as(self, target):
        self.saved_to = Path(target)
        self.saved_to.write_bytes(b"downloaded")


class FakePage:
    def __init__(self):
        self.handlers = {}
        self.visited = []

    def on(self, event, handler):
        self.handlers[event] = handler

    def goto(self, url, wait_until=None, timeout=None):
        self.visited.append((url, wait_until, timeout))

    def emit_download(self, filename):
        self.handlers["download"](FakeDownload(filename))


def test_download_score_interactively_saves_page_downloads(tmp_path):
    page = FakePage()

    def prompt(_message):
        page.emit_download("score.pdf")
        page.emit_download("score.musicxml")
        page.emit_download("score.mscx")
        return ""

    result = download_score_interactively(
        page=page,
        url="https://musescore.com/user/1/scores/111",
        sample_dir=tmp_path,
        prompt=prompt,
    )

    assert isinstance(result, BrowserDownloadResult)
    assert result.status == "downloads_recorded"
    assert sorted(path.name for path in result.downloaded_paths) == [
        "score.mscx",
        "score.musicxml",
        "score.pdf",
    ]
    assert page.visited[0][0] == "https://musescore.com/user/1/scores/111"


def test_download_score_interactively_reports_no_downloads(tmp_path):
    page = FakePage()

    result = download_score_interactively(
        page=page,
        url="https://musescore.com/user/1/scores/111",
        sample_dir=tmp_path,
        prompt=lambda _message: "",
    )

    assert result.status == "no_downloads"
    assert "No downloads" in result.message


def test_collect_browser_downloads_uses_persistent_profile(tmp_path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://musescore.com/user/1/scores/111\n", encoding="utf-8")
    calls = []

    class FakeContext:
        def __init__(self):
            self.page = FakePage()

        def new_page(self):
            return self.page

        def close(self):
            calls.append("closed")

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            calls.append((Path(user_data_dir), kwargs))
            return FakeContext()

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_playwright_factory():
        return FakePlaywright()

    results = collect_browser_downloads(
        urls_file=urls_file,
        output_dir=tmp_path / "samples",
        user_data_dir=tmp_path / "profile",
        limit=1,
        prompt=lambda _message: "",
        playwright_factory=fake_playwright_factory,
    )

    assert calls[0][0] == tmp_path / "profile"
    assert calls[0][1]["headless"] is False
    assert calls[0][1]["accept_downloads"] is True
    assert calls[-1] == "closed"
    assert results[0].sample_id == "musescore-111"


def test_collect_browser_downloads_can_launch_installed_chrome_profile(tmp_path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://musescore.com/user/1/scores/111\n", encoding="utf-8")
    calls = []

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            calls.append((Path(user_data_dir), kwargs))
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    results = collect_browser_downloads(
        urls_file=urls_file,
        output_dir=tmp_path / "samples",
        user_data_dir=tmp_path / "chrome-user-data",
        limit=1,
        prompt=lambda _message: "",
        playwright_factory=lambda: FakePlaywright(),
        chrome_executable=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        chrome_profile_directory="Profile 2",
    )

    assert calls[0][0] == tmp_path / "chrome-user-data"
    assert calls[0][1]["executable_path"] == r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    assert calls[0][1]["args"] == ["--profile-directory=Profile 2"]
    assert results[0].status == "no_downloads"
