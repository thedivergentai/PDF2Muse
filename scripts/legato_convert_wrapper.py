"""Convert Legato ABC JSON to MusicXML without relying on vendor software/mscore.

Calls Legato's utils/abc2xml.py, then optionally reformats via MuseScore CLI
discovered by PDF2Muse (find_musescore_binary). Does not edit vendor source.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.legato_env import load_legato_env_defaults  # noqa: E402
from pdf2muse.musicxml import find_musescore_binary  # noqa: E402


def _legato_repo() -> Path:
    load_legato_env_defaults(REPO_ROOT)
    repo = os.environ.get("PDF2MUSE_LEGATO_REPO")
    if not repo:
        raise RuntimeError("PDF2MUSE_LEGATO_REPO is not set; run scripts/legato_setup.py")
    path = Path(repo).resolve()
    if not (path / "utils" / "abc2xml.py").exists():
        raise RuntimeError(f"Legato abc2xml.py missing under {path}")
    return path


def _legato_python() -> str:
    return os.environ.get("PDF2MUSE_LEGATO_PYTHON", sys.executable)


def convert_abc_json_to_xml(
    input_file: Path,
    tmp_dir: Path,
    *,
    musescore_path: Path | None = None,
) -> Path:
    """Convert *_abc.json to *_xml.json using abc2xml + optional MuseScore reformat."""

    input_file = Path(input_file)
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    repo = _legato_repo()
    python = _legato_python()
    abc2xml = repo / "utils" / "abc2xml.py"

    payload = json.loads(input_file.read_text(encoding="utf-8"))
    transcriptions = payload.get("abc_transcription", [])
    if isinstance(transcriptions, str):
        transcriptions = [transcriptions]
    if not isinstance(transcriptions, list) or not transcriptions:
        raise ValueError("ABC JSON has no abc_transcription entries")

    musescore = musescore_path or find_musescore_binary()
    xmls: list[str] = []
    for index, abc_text in enumerate(transcriptions):
        if not str(abc_text).strip():
            xmls.append("")
            continue
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".musicxml",
            dir=tmp_dir,
            delete=False,
            encoding="utf-8",
        ) as handle:
            tmp_musicxml = Path(handle.name)

        try:
            result = subprocess.run(
                [python, str(abc2xml), "-"],
                input=str(abc_text).encode("utf-8"),
                capture_output=True,
                check=False,
                cwd=str(repo),
            )
            if result.returncode != 0 or not result.stdout.strip():
                raise RuntimeError(
                    f"abc2xml failed for entry {index}: "
                    f"{(result.stderr or b'').decode('utf-8', errors='replace')[:400]}"
                )
            tmp_musicxml.write_bytes(result.stdout)

            if musescore is not None and musescore.exists():
                try:
                    subprocess.run(
                        [str(musescore), "-f", "-o", str(tmp_musicxml), str(tmp_musicxml)],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    # MuseScore reformat is optional; keep abc2xml output.
                    pass

            xmls.append(tmp_musicxml.read_text(encoding="utf-8", errors="replace"))
        finally:
            if tmp_musicxml.exists():
                tmp_musicxml.unlink(missing_ok=True)

    output_file = Path(str(input_file).replace("_abc.json", "_xml.json"))
    if output_file == input_file:
        output_file = input_file.with_name(input_file.stem + "_xml.json")
    output_file.write_text(json.dumps(xmls), encoding="utf-8")
    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_file", type=Path, required=True)
    parser.add_argument("--tmp_dir", type=Path, required=True)
    parser.add_argument("--musescore-path", type=Path, default=None)
    args = parser.parse_args()
    out = convert_abc_json_to_xml(
        args.input_file,
        args.tmp_dir,
        musescore_path=args.musescore_path,
    )
    print(f"Saved XML outputs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
