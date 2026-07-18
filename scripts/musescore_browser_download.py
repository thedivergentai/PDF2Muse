"""Interactive browser-assisted MuseScore.com downloads.

This helper opens a persistent browser profile so the user can log into
MuseScore.com locally. It records downloads triggered by the user and saves them
into the matching benchmark sample directory.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from scripts.musescore_com_benchmark import load_score_urls, sample_id_for_url


Prompt = Callable[[str], str]


@dataclass
class BrowserDownloadResult:
    sample_id: str
    url: str
    sample_dir: Path
    status: str
    downloaded_paths: list[Path]
    message: str = ""


def download_score_interactively(
    *,
    page,
    url: str,
    sample_dir: Path,
    prompt: Prompt = input,
    goto_timeout_ms: int = 120_000,
) -> BrowserDownloadResult:
    """Open one score page and save user-triggered downloads into sample_dir."""

    sample_dir = Path(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_id = sample_id_for_url(url)
    downloaded_paths: list[Path] = []

    def handle_download(download) -> None:
        target = _unique_target(sample_dir / download.suggested_filename)
        download.save_as(target)
        downloaded_paths.append(target)

    page.on("download", handle_download)
    page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
    prompt(
        "\n".join(
            [
                f"Opened {url}",
                "Log in if needed, then use MuseScore.com's download menu.",
                "Download PDF, MusicXML/MXL, and MSCX/MSCZ for this score.",
                f"Files will be saved under: {sample_dir}",
                "Press Enter here after downloads finish.",
            ]
        )
    )

    if not downloaded_paths:
        return BrowserDownloadResult(
            sample_id=sample_id,
            url=url,
            sample_dir=sample_dir,
            status="no_downloads",
            downloaded_paths=[],
            message="No downloads were recorded for this score.",
        )
    return BrowserDownloadResult(
        sample_id=sample_id,
        url=url,
        sample_dir=sample_dir,
        status="downloads_recorded",
        downloaded_paths=downloaded_paths,
    )


def collect_browser_downloads(
    *,
    urls_file: Path,
    output_dir: Path,
    user_data_dir: Path = Path("datasets/tools/musescore-browser-profile"),
    limit: Optional[int] = None,
    prompt: Prompt = input,
    wait_seconds: Optional[int] = None,
    chrome_executable: Optional[Path] = None,
    chrome_profile_directory: Optional[str] = None,
    playwright_factory=None,
) -> list[BrowserDownloadResult]:
    """Open a persistent browser and collect downloads for each score URL."""

    urls = load_score_urls(urls_file, limit=limit)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir = Path(user_data_dir)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    if playwright_factory is None:
        playwright_factory = _sync_playwright
    if wait_seconds is not None:
        prompt = _timed_prompt(wait_seconds)

    results: list[BrowserDownloadResult] = []
    with playwright_factory() as playwright:
        launch_options = {
            "headless": False,
            "accept_downloads": True,
        }
        if chrome_executable:
            launch_options["executable_path"] = str(chrome_executable)
        if chrome_profile_directory:
            launch_options["args"] = [f"--profile-directory={chrome_profile_directory}"]
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            **launch_options,
        )
        try:
            page = context.new_page()
            for url in urls:
                sample_id = sample_id_for_url(url)
                result = download_score_interactively(
                    page=page,
                    url=url,
                    sample_dir=output_dir / sample_id,
                    prompt=prompt,
                )
                results.append(result)
                _write_browser_status(output_dir, results)
        finally:
            context.close()
    return results


def _timed_prompt(wait_seconds: int) -> Prompt:
    def prompt(message: str) -> str:
        print(message)
        print(f"Waiting {wait_seconds} seconds before advancing to the next score...")
        time.sleep(max(0, wait_seconds))
        return ""

    return prompt


def _sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install evaluation dependencies and run "
            "`python -m playwright install chromium` before using browser downloads."
        ) from exc
    return sync_playwright()


def _unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not choose a unique download path for {path}")


def _write_browser_status(output_dir: Path, results: list[BrowserDownloadResult]) -> None:
    status_path = output_dir / "browser_download_status.json"
    status_path.write_text(
        json.dumps(
            {"samples": [_jsonable_result(result, output_dir) for result in results]},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _jsonable_result(result: BrowserDownloadResult, base_dir: Path) -> dict[str, object]:
    data = asdict(result)
    data["sample_dir"] = _relative(base_dir / "browser_download_status.json", result.sample_dir)
    data["downloaded_paths"] = [
        _relative(base_dir / "browser_download_status.json", path)
        for path in result.downloaded_paths
    ]
    return data


def _relative(base_file: Path, target: Path) -> str:
    return Path(os.path.relpath(Path(target).resolve(), Path(base_file).parent.resolve())).as_posix()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--urls-file",
        type=Path,
        default=Path("datasets/benchmark-sources/musescore-com/urls.txt"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/benchmark-sources/musescore-com"),
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=Path("datasets/tools/musescore-browser-profile"),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--chrome-executable", type=Path)
    parser.add_argument("--chrome-profile-directory")
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=None,
        help="Automatically advance after this many seconds instead of waiting for Enter.",
    )
    args = parser.parse_args(argv)

    results = collect_browser_downloads(
        urls_file=args.urls_file,
        output_dir=args.output_dir,
        user_data_dir=args.user_data_dir,
        limit=args.limit,
        wait_seconds=args.wait_seconds,
        chrome_executable=args.chrome_executable,
        chrome_profile_directory=args.chrome_profile_directory,
    )
    recorded = sum(1 for result in results if result.status == "downloads_recorded")
    print(f"Recorded downloads for {recorded}/{len(results)} MuseScore.com scores")
    print(f"Status: {args.output_dir / 'browser_download_status.json'}")
    return 0 if recorded else 1


if __name__ == "__main__":
    raise SystemExit(main())
