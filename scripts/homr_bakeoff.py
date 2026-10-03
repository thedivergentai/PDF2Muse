#!/usr/bin/env python3
"""Scaffold a HOMR (AGPL) vs oemer NED bake-off — gated, non-default."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from pdf2muse.adapters.homr import HomrAdapter  # noqa: E402
from pdf2muse.oemer_utils import get_model_backend_config, list_model_backend_configs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO / "evaluation" / "runs" / "homr-bakeoff" / "scaffold.json",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="If HOMR is available, attempt a single smoke recognize (still experimental).",
    )
    parser.add_argument("--image", type=Path, default=None)
    args = parser.parse_args()

    backends = [c.name for c in list_model_backend_configs()]
    config = get_model_backend_config("homr-experimental")
    adapter = HomrAdapter()
    status = adapter.healthcheck()
    payload = {
        "backend": config.name,
        "experimental": config.experimental,
        "license": "AGPL-3.0",
        "product_default": False,
        "registered_backends": backends,
        "health": {
            "available": status.available,
            "message": status.message,
        },
        "bakeoff_instructions": [
            "1. Clone https://github.com/liebharc/homr into a dedicated directory.",
            "2. Install HOMR into an isolated venv (AGPL); set PDF2MUSE_HOMR_REPO / PDF2MUSE_HOMR_PYTHON.",
            "3. Run multi_tier_eval / model_benchmark with --model-backend homr-experimental.",
            "4. Compare OMR-NED and part_collapse vs dpi360-quality-step128 oemer baseline.",
            "5. Do not promote HOMR to default without a license decision.",
        ],
        "smoke": None,
    }

    if args.run:
        if not status.available:
            payload["smoke"] = {"skipped": True, "reason": status.message}
        elif args.image is None or not args.image.exists():
            payload["smoke"] = {
                "skipped": True,
                "reason": "Pass --image PATH for smoke recognition",
            }
        else:
            out_dir = args.out.parent / "smoke"
            result = adapter.recognize_page(
                args.image,
                out_dir,
                __import__("pdf2muse.adapters.base", fromlist=["OmrOptions"]).OmrOptions(),
            )
            payload["smoke"] = {
                "error": result.error,
                "failure_class": result.failure_class,
                "musicxml_path": str(result.musicxml_path) if result.musicxml_path else None,
                "metadata": result.metadata,
            }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["health"], indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
