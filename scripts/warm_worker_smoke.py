"""Manual warm-worker smoke: recognize one page twice; compare session_load."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from pdf2muse.adapters.base import OmrOptions
from pdf2muse.adapters.oemer import OemerAdapter
from pdf2muse.core import PDF2MusePipeline
from pdf2muse.oemer_worker_client import shutdown_all_oemer_workers


def main() -> int:
    pdf = Path("datasets/cache/clean-typeset-generated/pdfs/generated-clean-typeset-001.pdf")
    out = Path("evaluation/runs/warm-worker-smoke")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    pipeline = PDF2MusePipeline(
        pdf_path=str(pdf),
        output_dir=str(out),
        oemer_device="cuda",
        first_page=1,
        last_page=1,
        oemer_timeout_seconds=900,
    )
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        image_dir = td_path / "images"
        image_dir.mkdir(parents=True)
        images = pipeline.pdf_to_png(image_dir)
        img = images[0]
        adapter = OemerAdapter(retries=False, quality_report=True)
        opts = OmrOptions(
            device="cuda",
            deskew=True,
            quality_profile="quality",
            timeout_seconds=900,
            save_cache=False,
            use_tf=False,
            checkpoint_dir=None,
        )
        r1 = adapter.recognize_page(img, td_path / "mxl1", opts)
        r2 = adapter.recognize_page(img, td_path / "mxl2", opts)
        s1 = (r1.attempts or [{}])[0].get("stages") or {}
        s2 = (r2.attempts or [{}])[0].get("stages") or {}
        print("PASS1", "err" if r1.error else "ok", s1)
        print("PASS2", "err" if r2.error else "ok", s2)
        print("session_load_pass1", s1.get("session_load"))
        print("session_load_pass2", s2.get("session_load"))
        if r1.error or r2.error:
            return 1
        # Warm pass should not reload ORT sessions (0 or missing after first load).
        load2 = float(s2.get("session_load") or 0.0)
        if load2 > 0.5:
            print(f"WARN: unexpected session_load on pass2={load2}")
            return 2
    shutdown_all_oemer_workers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
