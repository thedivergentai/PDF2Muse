#!/usr/bin/env python3
"""Run HOMR process_image on a single page image (PDF2Muse adapter helper).

Do not use HOMR's multi-image run_homr path: it merges pages and deletes
per-page MusicXML. PDF2Muse joins pages itself.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF2Muse HOMR single-page wrapper")
    parser.add_argument("image", type=str, help="Path to page image (PNG/JPG)")
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="GPU preference for HOMR onnxruntime providers",
    )
    parser.add_argument(
        "--no-title",
        action="store_true",
        help="Skip title OCR for faster inference",
    )
    args = parser.parse_args()

    try:
        from homr.main import (
            ProcessingConfig,
            download_weights,
            process_image,
        )
        from homr.music_xml_generator import XmlGeneratorArguments
        from homr.onnx_providers import cuda_available, rocm_available
    except ImportError as exc:
        print(f"HOMR is not installed: {exc}", file=sys.stderr)
        print(
            "Install with: pip install 'pdf2muse[homr]' (requires Python >= 3.11)",
            file=sys.stderr,
        )
        return 2

    force_gpu = args.device == "cuda"
    auto_gpu = args.device == "auto"
    has_gpu = cuda_available() or rocm_available()
    transformer_use_gpu = force_gpu or (auto_gpu and has_gpu)
    segnet_use_gpu = force_gpu or (auto_gpu and has_gpu)

    download_weights(segnet_use_gpu, transformer_use_gpu, False)
    config = ProcessingConfig(
        False,  # enable_debug
        False,  # enable_cache
        False,  # write_staff_positions
        False,  # read_staff_positions
        -1,  # selected_staff
        transformer_use_gpu,
        segnet_use_gpu,
        False,  # coreml_encoder
        not args.no_title,
    )
    xml_args = XmlGeneratorArguments(False, None, None)
    xml_path = process_image(args.image, config, xml_args)
    print(xml_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
