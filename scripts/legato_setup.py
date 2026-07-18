"""Bootstrap a local Legato checkout and optional venv for benchmarking."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR = REPO_ROOT / "datasets" / "vendor"
LEGATO_DIR = VENDOR / "legato"
LEGATO_VENV = VENDOR / "legato-venv"

sys.path.insert(0, str(REPO_ROOT / "src"))
from pdf2muse.legato_env import write_legato_env_file  # noqa: E402
from pdf2muse.musicxml import find_musescore_binary, validate_musicxml_file  # noqa: E402


def _link_musescore_shim() -> None:
    """Create software/mscore launcher for upstream convert.py (best-effort).

    On Windows, also write mscore.cmd. Prefer scripts/legato_convert_wrapper.py
    from the Legato adapter; this shim helps if vendor convert.py is invoked.
    """

    musescore = find_musescore_binary()
    if musescore is None or not (LEGATO_DIR / "utils" / "convert.py").exists():
        return
    software_dir = LEGATO_DIR / "software"
    software_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        bat = software_dir / "mscore.bat"
        cmd = software_dir / "mscore.cmd"
        script = f'@echo off\r\n"{musescore}" %*\r\n'
        for shim in (bat, cmd):
            if not shim.exists():
                shim.write_text(script, encoding="utf-8")
        # Extensionless launcher that cmd.exe can run when PATH includes software/.
        mscore = software_dir / "mscore"
        if not mscore.exists():
            mscore.write_text(script, encoding="utf-8")
    else:
        shim = software_dir / "mscore"
        if shim.exists():
            return
        shim.write_text(
            f'#!/bin/sh\nexec "{musescore}" "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)


def _verify_legato(python: Path) -> None:
    """Tiny PNG → inference → convert wrapper → parseable MusicXML."""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(LEGATO_DIR)
    env["PDF2MUSE_LEGATO_REPO"] = str(LEGATO_DIR)
    env["PDF2MUSE_LEGATO_PYTHON"] = str(python)
    env.setdefault("PDF2MUSE_LEGATO_MODEL", "guangyangmusic/legato-small")
    # huggingface_hub prefers HUGGING_FACE_HUB_TOKEN; accept HF_TOKEN as alias.
    if env.get("HF_TOKEN") and not env.get("HUGGING_FACE_HUB_TOKEN"):
        env["HUGGING_FACE_HUB_TOKEN"] = env["HF_TOKEN"]

    subprocess.run(
        [str(python), "-c", "from legato.models import LegatoModel; print('legato import ok')"],
        check=True,
        env=env,
    )
    abc2xml = LEGATO_DIR / "utils" / "abc2xml.py"
    if not abc2xml.exists():
        raise RuntimeError("Legato abc2xml.py missing from vendor checkout")
    wrapper = REPO_ROOT / "scripts" / "legato_convert_wrapper.py"
    if not wrapper.exists():
        raise RuntimeError(f"Missing {wrapper}")

    inference = LEGATO_DIR / "scripts" / "inference.py"
    if not inference.exists():
        raise RuntimeError("Legato scripts/inference.py missing")

    with tempfile.TemporaryDirectory(prefix="legato-verify-") as tmp:
        tmp_path = Path(tmp)
        png_path = tmp_path / "smoke.png"
        Image.new("RGB", (512, 512), "white").save(png_path, "PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        model = env["PDF2MUSE_LEGATO_MODEL"]
        print(f"Running Legato inference smoke ({model}) — may download weights…")
        completed = subprocess.run(
            [
                str(python),
                str(inference),
                "--model_path",
                model,
                "--image_path",
                str(png_path),
                "--output_path",
                str(out_dir),
                "--device",
                "cuda",
                "--fp16",
            ],
            cwd=str(LEGATO_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "")[:1600]
            hint = ""
            if "403" in detail or "Forbidden" in detail:
                hint = (
                    "\nHint: Hugging Face returned 403. Accept the model license on the Hub "
                    "and set HF_TOKEN / HUGGING_FACE_HUB_TOKEN before re-running --verify."
                )
            raise RuntimeError(
                "Legato inference smoke failed:\n"
                f"{detail}{hint}"
            )
        abc_candidates = list(out_dir.glob("*_abc.json"))
        if not abc_candidates:
            raise RuntimeError(f"Legato inference wrote no *_abc.json under {out_dir}")
        abc_json = abc_candidates[0]
        convert = subprocess.run(
            [
                sys.executable,
                str(wrapper),
                "--input_file",
                str(abc_json),
                "--tmp_dir",
                str(out_dir),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if convert.returncode != 0:
            raise RuntimeError(
                "Legato convert wrapper failed:\n"
                f"{(convert.stderr or convert.stdout or '')[:1200]}"
            )
        xml_json = Path(str(abc_json).replace("_abc.json", "_xml.json"))
        if not xml_json.exists():
            raise RuntimeError(f"Convert wrapper did not write {xml_json}")
        xml_payload = json.loads(xml_json.read_text(encoding="utf-8"))
        if not xml_payload or not str(xml_payload[0]).strip():
            raise RuntimeError("Convert wrapper returned empty MusicXML")
        musicxml_path = out_dir / "verify.musicxml"
        musicxml_path.write_text(xml_payload[0], encoding="utf-8")
        validation = validate_musicxml_file(musicxml_path, structural=False)
        if not validation.ok:
            raise RuntimeError(f"Verify MusicXML not parseable: {validation.error}")
        print(f"Legato verify OK: parseable MusicXML ({musicxml_path.stat().st_size} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run tiny PNG → inference → convert → parseable MusicXML check (GPU + HF download)",
    )
    args = parser.parse_args()

    VENDOR.mkdir(parents=True, exist_ok=True)
    if not (LEGATO_DIR / "scripts" / "inference.py").exists():
        print(f"Cloning Legato into {LEGATO_DIR}…")
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/guang-yng/legato.git", str(LEGATO_DIR)],
            check=True,
        )

    python = LEGATO_VENV / "Scripts" / "python.exe"
    if not python.exists():
        python = LEGATO_VENV / "bin" / "python"

    if args.skip_install:
        _link_musescore_shim()
        if python.exists():
            env_path = write_legato_env_file(repo=LEGATO_DIR, python=python)
            print(f"Wrote env file: {env_path}")
        else:
            print(f"Legato repo ready at {LEGATO_DIR} (venv missing; skip-install)")
        print(f"Set PDF2MUSE_LEGATO_REPO={LEGATO_DIR}")
        if args.verify:
            if not python.exists():
                raise SystemExit("Cannot --verify without legato-venv; omit --skip-install")
            _verify_legato(python)
        return 0

    if not LEGATO_VENV.exists():
        print(f"Creating Legato venv at {LEGATO_VENV}…")
        venv_python = [sys.executable, "-m", "venv", str(LEGATO_VENV)]
        for candidate in (["py", "-3.11"], ["py", "-3.12"]):
            try:
                probe = subprocess.run(
                    candidate + ["-c", "import sys; print(sys.version_info[:2])"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if probe.stdout.strip().startswith("(3, 1"):
                    venv_python = candidate + ["-m", "venv", str(LEGATO_VENV)]
                    break
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        subprocess.run(venv_python, check=True)

    pip = LEGATO_VENV / "Scripts" / "pip.exe"
    python = LEGATO_VENV / "Scripts" / "python.exe"
    if not pip.exists():
        pip = LEGATO_VENV / "bin" / "pip"
        python = LEGATO_VENV / "bin" / "python"

    print("Installing Legato inference dependencies (torch, transformers, …) — this may take several minutes.")
    inference_reqs = LEGATO_VENV / "legato-inference-requirements.txt"
    patched = []
    for line in (LEGATO_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("deepspeed") or stripped.startswith("wandb"):
            continue
        if stripped.startswith("numpy=="):
            patched.append("numpy>=1.26.4")
            continue
        patched.append(stripped.replace("git+ssh://git@github.com/", "git+https://github.com/"))
    inference_reqs.write_text("\n".join(patched) + "\n", encoding="utf-8")
    subprocess.run([str(pip), "install", "-r", str(inference_reqs)], check=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(LEGATO_DIR)
    subprocess.run(
        [str(python), "-c", "from legato.models import LegatoModel; print('legato import ok')"],
        check=True,
        env=env,
    )

    _link_musescore_shim()
    env_path = write_legato_env_file(repo=LEGATO_DIR, python=python)
    if args.verify:
        _verify_legato(python)

    print("\nLegato setup complete.")
    print(f"  Env file: {env_path}")
    print(f"  PDF2MUSE_LEGATO_REPO={LEGATO_DIR}")
    print(f"  PDF2MUSE_LEGATO_PYTHON={python}")
    print(f"  PDF2MUSE_LEGATO_MODEL=guangyangmusic/legato-small")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
