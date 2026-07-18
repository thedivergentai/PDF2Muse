"""Detect or prepare a local MuseScore CLI for benchmark validation."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from pdf2muse.musicxml import find_musescore_binary as find_existing_musescore_binary


PORTABLE_VERSION = "4.6.5"
PORTABLE_INSTALLER_NAME = f"MuseScorePortable_{PORTABLE_VERSION}.paf.exe"
PORTABLE_DOWNLOAD_URL = (
    "https://downloads.sourceforge.net/portableapps/"
    f"{PORTABLE_INSTALLER_NAME}"
)


@dataclass(frozen=True)
class MuseScoreSetupResult:
    status: str
    executable_path: Optional[Path] = None
    installer_path: Optional[Path] = None
    message: str = ""


def find_musescore_executable(
    *,
    custom_path: Optional[Path] = None,
    tools_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Find MuseScore from a custom path, the system, or a local portable tree."""

    if custom_path:
        candidate = Path(custom_path)
        if candidate.exists():
            return candidate

    system_binary = find_existing_musescore_binary(None)
    if system_binary:
        return system_binary

    if not tools_dir:
        return None

    root = Path(tools_dir)
    portable_candidates = [
        root / "MuseScorePortable" / "App" / "MuseScore" / "bin" / "MuseScore4.exe",
        root / "MuseScorePortable" / "App" / "MuseScore" / "bin" / "MuseScore3.exe",
    ]
    portable_candidates.extend(root.rglob("MuseScore4.exe"))
    portable_candidates.extend(root.rglob("MuseScore3.exe"))
    for candidate in portable_candidates:
        if candidate.exists():
            return candidate
    return None


def setup_musescore_portable(
    *,
    tools_dir: Path,
    installer_url: str = PORTABLE_DOWNLOAD_URL,
    run_installer: bool = False,
) -> MuseScoreSetupResult:
    """Download and optionally run the portable MuseScore installer."""

    tools_dir = Path(tools_dir)
    tools_dir.mkdir(parents=True, exist_ok=True)

    executable = find_musescore_executable(tools_dir=tools_dir)
    if executable:
        return MuseScoreSetupResult(
            status="found",
            executable_path=executable,
            message="MuseScore executable already available.",
        )

    installer_path = tools_dir / PORTABLE_INSTALLER_NAME
    if not installer_path.exists():
        _download_file(installer_url, installer_path)
        if not run_installer:
            return MuseScoreSetupResult(
                status="installer_downloaded",
                installer_path=installer_path,
                message=(
                    "Downloaded portable installer. Run again with --run-installer "
                    "or install it into the tools directory."
                ),
            )

    if not run_installer:
        return MuseScoreSetupResult(
            status="installer_present",
            installer_path=installer_path,
            message=(
                "Portable installer is present. Run with --run-installer or install it "
                "into the tools directory."
            ),
        )

    command = [
        str(installer_path),
        f"/DESTINATION={tools_dir}",
        "/AUTOCLOSE=true",
        "/HIDEINSTALLER=true",
        "/SILENT=true",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        return MuseScoreSetupResult(
            status="installer_failed",
            installer_path=installer_path,
            message=(exc.stderr or exc.stdout or str(exc)).strip(),
        )

    executable = find_musescore_executable(tools_dir=tools_dir)
    if executable:
        return MuseScoreSetupResult(
            status="installed",
            executable_path=executable,
            installer_path=installer_path,
            message="Portable MuseScore executable detected after installer run.",
        )
    return MuseScoreSetupResult(
        status="installer_ran_not_found",
        installer_path=installer_path,
        message="Installer completed, but no MuseScore executable was found.",
    )


def validate_musescore_can_export(
    musescore_path: Path,
    input_path: Path,
    output_path: Path,
) -> Path:
    """Validate that MuseScore can load an input score and export a target file."""

    musescore_path = Path(musescore_path)
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [str(musescore_path), "-o", str(output_path), str(input_path)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or exc.stdout or str(exc)).strip()) from exc
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"MuseScore did not write export target: {output_path}")
    return output_path


def _download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, target)


def _jsonable_result(result: MuseScoreSetupResult) -> dict[str, Optional[str]]:
    data = asdict(result)
    for key in ("executable_path", "installer_path"):
        if data[key] is not None:
            data[key] = str(data[key])
    return data


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, default=Path("datasets/tools/musescore"))
    parser.add_argument("--musescore-path", type=Path)
    parser.add_argument("--setup-portable", action="store_true")
    parser.add_argument("--run-installer", action="store_true")
    args = parser.parse_args(argv)

    executable = find_musescore_executable(
        custom_path=args.musescore_path,
        tools_dir=args.tools_dir,
    )
    if executable and not args.setup_portable:
        result = MuseScoreSetupResult(status="found", executable_path=executable)
    elif args.setup_portable:
        result = setup_musescore_portable(
            tools_dir=args.tools_dir,
            run_installer=args.run_installer,
        )
    else:
        result = MuseScoreSetupResult(
            status="not_found",
            message="MuseScore was not found. Use --setup-portable to download the portable installer.",
        )

    print(json.dumps(_jsonable_result(result), indent=2, sort_keys=True))
    return 0 if result.status in {"found", "installed", "installer_downloaded", "installer_present"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
