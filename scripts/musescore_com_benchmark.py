"""Collect local MuseScore.com benchmark triplets for PDF2Muse evaluation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from pdf2muse.evaluation import parse_musicxml
from scripts.musescore_setup import (
    find_musescore_executable,
    setup_musescore_portable as setup_portable_musescore,
    validate_musescore_can_export,
)
from scripts.openscore_benchmark import extract_musicxml_from_mxl


def collect_browser_downloads(**kwargs):
    """Lazy wrapper so Playwright is only required for browser-assisted downloads."""

    from scripts.musescore_browser_download import collect_browser_downloads as collect

    return collect(**kwargs)


@dataclass
class MuseScoreComSample:
    sample_id: str = ""
    url: str = ""
    sample_dir: Optional[Path] = None
    status: str = "pending"
    pdf_path: Optional[Path] = None
    musicxml_path: Optional[Path] = None
    mscx_path: Optional[Path] = None
    message: str = ""


def load_score_urls(urls_file: Path, *, limit: Optional[int] = None) -> list[str]:
    """Load MuseScore.com score URLs from a newline-delimited file."""

    urls = []
    for line in Path(urls_file).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    if limit is not None:
        return urls[: max(0, limit)]
    return urls


def sample_id_for_url(url: str) -> str:
    """Create a stable local sample id from a MuseScore.com score URL."""

    match = re.search(r"/scores/(\d+)", url)
    if match:
        return f"musescore-{match.group(1)}"
    fallback = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-").lower()
    return f"musescore-{fallback[-48:]}"


def download_pdf_with_librescore(url: str, sample_dir: Path) -> MuseScoreComSample:
    """Attempt a PDF download through the unofficial dl-librescore CLI."""

    sample_dir = Path(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)
    before = set(sample_dir.glob("*.pdf"))
    command = [
        "npx",
        "dl-librescore@latest",
        "-i",
        url,
        "-t",
        "pdf",
        "-o",
        str(sample_dir),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return MuseScoreComSample(
            sample_id=sample_id_for_url(url),
            url=url,
            sample_dir=sample_dir,
            status="pdf_downloader_unavailable",
            message=str(exc),
        )
    except subprocess.CalledProcessError as exc:
        return MuseScoreComSample(
            sample_id=sample_id_for_url(url),
            url=url,
            sample_dir=sample_dir,
            status="pdf_blocked",
            message=(exc.stderr or exc.stdout or str(exc)).strip(),
        )

    created = [path for path in sample_dir.glob("*.pdf") if path not in before]
    pdf_path = created[0] if created else _first_file(sample_dir, (".pdf",))
    if not pdf_path:
        return MuseScoreComSample(
            sample_id=sample_id_for_url(url),
            url=url,
            sample_dir=sample_dir,
            status="pdf_missing",
            message="dl-librescore completed without writing a PDF.",
        )
    return MuseScoreComSample(
        sample_id=sample_id_for_url(url),
        url=url,
        sample_dir=sample_dir,
        status="pdf_downloaded",
        pdf_path=pdf_path,
    )


def normalize_sample_sources(
    sample_dir: Path,
    *,
    sample_id: Optional[str] = None,
    url: str = "",
    musescore_path: Optional[Path] = None,
) -> MuseScoreComSample:
    """Normalize local official downloads into PDF, MusicXML, and MSCX paths."""

    sample_dir = Path(sample_dir)
    sample_id = sample_id or sample_dir.name
    pdf_path = _first_file(sample_dir, (".pdf",))
    musicxml_path = _first_file(sample_dir, (".musicxml", ".xml"))
    mxl_path = _first_file(sample_dir, (".mxl",))
    mscx_path = _first_file(sample_dir, (".mscx",))
    mscz_path = _first_file(sample_dir, (".mscz",))

    if not musicxml_path and mxl_path:
        musicxml_path = sample_dir / "ground_truth.musicxml"
        extract_musicxml_from_mxl(mxl_path, musicxml_path)
    if not musicxml_path and musescore_path and (mscx_path or mscz_path):
        musicxml_path = sample_dir / "ground_truth.musicxml"
        validate_musescore_can_export(musescore_path, mscx_path or mscz_path, musicxml_path)
    if not mscx_path and musescore_path and mscz_path:
        mscx_path = sample_dir / "source.mscx"
        validate_musescore_can_export(musescore_path, mscz_path, mscx_path)
    if not pdf_path and musescore_path and (mscx_path or mscz_path):
        pdf_path = sample_dir / "input.pdf"
        validate_musescore_can_export(musescore_path, mscx_path or mscz_path, pdf_path)

    missing = []
    if not pdf_path:
        missing.append("pdf")
    if not musicxml_path:
        missing.append("musicxml")
    if not mscx_path:
        missing.append("mscx")
    if missing:
        return MuseScoreComSample(
            sample_id=sample_id,
            url=url,
            sample_dir=sample_dir,
            status="incomplete",
            pdf_path=pdf_path,
            musicxml_path=musicxml_path,
            mscx_path=mscx_path,
            message=f"Missing required source file(s): {', '.join(missing)}",
        )

    parse_result = parse_musicxml(musicxml_path)
    if not parse_result.ok:
        return MuseScoreComSample(
            sample_id=sample_id,
            url=url,
            sample_dir=sample_dir,
            status="ground_truth_parse_failed",
            pdf_path=pdf_path,
            musicxml_path=musicxml_path,
            mscx_path=mscx_path,
            message=parse_result.error or "Ground-truth MusicXML did not parse.",
        )

    if musescore_path and mscx_path:
        try:
            validate_musescore_can_export(
                musescore_path,
                mscx_path,
                sample_dir / "source.import-check.musicxml",
            )
        except RuntimeError as exc:
            return MuseScoreComSample(
                sample_id=sample_id,
                url=url,
                sample_dir=sample_dir,
                status="mscx_validation_failed",
                pdf_path=pdf_path,
                musicxml_path=musicxml_path,
                mscx_path=mscx_path,
                message=str(exc),
            )

    return MuseScoreComSample(
        sample_id=sample_id,
        url=url,
        sample_dir=sample_dir,
        status="complete",
        pdf_path=pdf_path,
        musicxml_path=musicxml_path,
        mscx_path=mscx_path,
    )


def write_evaluation_manifest(samples: list[MuseScoreComSample], manifest_path: Path) -> None:
    """Write the PDF2Muse evaluation manifest for complete benchmark samples."""

    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_samples = []
    for sample in samples:
        if sample.status != "complete" or not sample.pdf_path or not sample.musicxml_path:
            continue
        manifest_samples.append(
            {
                "id": sample.sample_id,
                "input": _relative(manifest_path, sample.pdf_path),
                "ground_truth": _relative(manifest_path, sample.musicxml_path),
                "source": "MuseScore.com",
                "source_url": sample.url,
                "license_notes": (
                    "Local MuseScore.com benchmark sample. Verify the uploader license "
                    "before redistribution; downloaded assets remain ignored locally."
                ),
                "difficulty_tags": ["musescore-com", "clean-typeset"],
                "first_page": 1,
                "last_page": 1,
                "input_quality": {
                    "renderer": "musescore-com-download",
                    "trusted_for_accuracy": True,
                },
                "metadata": {
                    "source_mscx": _relative(manifest_path, sample.mscx_path)
                    if sample.mscx_path
                    else None,
                    "collection_status": sample.status,
                },
            }
        )
    manifest_path.write_text(
        json.dumps({"samples": manifest_samples}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def collect_musescore_com_benchmark(
    *,
    urls_file: Path,
    output_dir: Path,
    manifest_path: Path,
    limit: int = 10,
    allow_unofficial_downloader: bool = False,
    musescore_path: Optional[Path] = None,
    setup_musescore_portable: bool = False,
    tools_dir: Path = Path("datasets/tools/musescore"),
    interactive_browser_downloads: bool = False,
    browser_user_data_dir: Path = Path("datasets/tools/musescore-browser-profile"),
    browser_wait_seconds: Optional[int] = None,
    chrome_executable: Optional[Path] = None,
    chrome_profile_directory: Optional[str] = None,
) -> list[MuseScoreComSample]:
    """Collect and validate MuseScore.com samples, preserving per-score status."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_musescore = find_musescore_executable(
        custom_path=musescore_path,
        tools_dir=tools_dir,
    )
    if not resolved_musescore and setup_musescore_portable:
        setup_result = setup_portable_musescore(tools_dir=tools_dir)
        resolved_musescore = setup_result.executable_path

    if interactive_browser_downloads:
        collect_browser_downloads(
            urls_file=urls_file,
            output_dir=output_dir,
            user_data_dir=browser_user_data_dir,
            limit=limit,
            wait_seconds=browser_wait_seconds,
            chrome_executable=chrome_executable,
            chrome_profile_directory=chrome_profile_directory,
        )

    samples: list[MuseScoreComSample] = []
    for url in load_score_urls(urls_file, limit=limit):
        sample_id = sample_id_for_url(url)
        sample_dir = output_dir / sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)

        if allow_unofficial_downloader and not _first_file(sample_dir, (".pdf",)):
            download_result = download_pdf_with_librescore(url, sample_dir)
            if download_result.status not in {"pdf_downloaded"}:
                samples.append(download_result)
                _write_collection_status(output_dir, samples)
                continue

        sample = normalize_sample_sources(
            sample_dir,
            sample_id=sample_id,
            url=url,
            musescore_path=resolved_musescore,
        )
        samples.append(sample)
        _write_collection_status(output_dir, samples)

    write_evaluation_manifest(samples, manifest_path)
    return samples


def _first_file(directory: Path, suffixes: tuple[str, ...]) -> Optional[Path]:
    for suffix in suffixes:
        preferred = directory / f"ground_truth{suffix}"
        if preferred.exists():
            return preferred
        source = directory / f"source{suffix}"
        if source.exists():
            return source
        input_path = directory / f"input{suffix}"
        if input_path.exists():
            return input_path
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in suffixes:
            return path
    return None


def _write_collection_status(output_dir: Path, samples: list[MuseScoreComSample]) -> None:
    status_path = output_dir / "collection_status.json"
    status_path.write_text(
        json.dumps(
            {"samples": [_jsonable_sample(sample, output_dir) for sample in samples]},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _jsonable_sample(sample: MuseScoreComSample, base_dir: Path) -> dict[str, Optional[str]]:
    data = asdict(sample)
    data["id"] = data.pop("sample_id")
    for key in ("sample_dir", "pdf_path", "musicxml_path", "mscx_path"):
        if data[key] is not None:
            data[key] = _relative(base_dir / "collection_status.json", Path(data[key]))
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
        "--manifest",
        type=Path,
        default=Path("evaluation/manifests/musescore-com.local.json"),
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--allow-unofficial-downloader", action="store_true")
    parser.add_argument("--interactive-browser-downloads", action="store_true")
    parser.add_argument(
        "--browser-user-data-dir",
        type=Path,
        default=Path("datasets/tools/musescore-browser-profile"),
    )
    parser.add_argument(
        "--browser-wait-seconds",
        type=int,
        default=None,
        help="Automatically advance browser downloads after this many seconds per score.",
    )
    parser.add_argument("--chrome-executable", type=Path)
    parser.add_argument("--chrome-profile-directory")
    parser.add_argument("--setup-musescore-portable", action="store_true")
    parser.add_argument("--tools-dir", type=Path, default=Path("datasets/tools/musescore"))
    parser.add_argument("--musescore-path", type=Path)
    args = parser.parse_args(argv)

    samples = collect_musescore_com_benchmark(
        urls_file=args.urls_file,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        limit=args.limit,
        allow_unofficial_downloader=args.allow_unofficial_downloader,
        musescore_path=args.musescore_path,
        setup_musescore_portable=args.setup_musescore_portable,
        tools_dir=args.tools_dir,
        interactive_browser_downloads=args.interactive_browser_downloads,
        browser_user_data_dir=args.browser_user_data_dir,
        browser_wait_seconds=args.browser_wait_seconds,
        chrome_executable=args.chrome_executable,
        chrome_profile_directory=args.chrome_profile_directory,
    )
    complete = sum(1 for sample in samples if sample.status == "complete")
    print(f"Collected {complete}/{len(samples)} complete MuseScore.com samples")
    print(f"Manifest: {args.manifest}")
    print(f"Status: {args.output_dir / 'collection_status.json'}")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
