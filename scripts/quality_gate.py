#!/usr/bin/env python3
"""CLI wrapper for the local quality-matrix NED gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pdf2muse.quality_gate import evaluate_quality_summary_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a quality-matrix style summary regresses past 0.576 + 0.02 OMR-NED."
    )
    parser.add_argument("summary_json", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_quality_summary_path(args.summary_json)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
