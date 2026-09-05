#!/usr/bin/env python3
"""Run HOMR process_image on a single page image (PDF2Muse adapter helper).

Do not use HOMR's multi-image run_homr path: it merges pages and deletes
per-page MusicXML. PDF2Muse joins pages itself.

HOMR is AGPL-3.0: https://github.com/liebharc/homr
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys


def _replace_extension(path: str, new_extension: str) -> str:
    return os.path.splitext(path)[0] + new_extension


def _build_processing_config(
    *,
    enable_debug: bool,
    enable_cache: bool,
    transformer_use_gpu: bool,
    segnet_use_gpu: bool,
    coreml_encoder: bool,
    title_detection: bool,
):
    from homr.main import ProcessingConfig

    kwargs = {
        "enable_debug": enable_debug,
        "enable_cache": enable_cache,
        "write_staff_positions": False,
        "read_staff_positions": False,
        "selected_staff": -1,
        "transformer_use_gpu": transformer_use_gpu,
        "segnet_use_gpu": segnet_use_gpu,
        "coreml_encoder": coreml_encoder,
        "title_detection": title_detection,
    }
    params = inspect.signature(ProcessingConfig).parameters
    filtered = {key: value for key, value in kwargs.items() if key in params}
    return ProcessingConfig(**filtered)


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
        help="Skip title OCR when this HOMR version supports title_detection",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable HOMR segmentation cache (maps to PDF2Muse --save-cache)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write HOMR debug images beside the work image",
    )
    args = parser.parse_args()

    try:
        from homr.main import download_weights, process_image
        from homr.music_xml_generator import XmlGeneratorArguments
        from homr.onnx_providers import coreml_available, cuda_available
    except ImportError as exc:
        print(f"HOMR is not installed: {exc}", file=sys.stderr)
        print(
            "Install with: pip install 'pdf2muse[homr]' (requires Python >= 3.11)",
            file=sys.stderr,
        )
        return 2

    try:
        from homr.onnx_providers import rocm_available
    except ImportError:
        def rocm_available() -> bool:
            return False

    force_gpu = args.device == "cuda"
    auto_gpu = args.device == "auto"
    has_accel = cuda_available() or rocm_available()
    if force_gpu and not has_accel:
        print(
            "HOMR: CUDA/ROCm requested but not available; falling back to CPU",
            file=sys.stderr,
        )
        transformer_use_gpu = False
        segnet_use_gpu = bool(coreml_available())
    else:
        transformer_use_gpu = force_gpu or (auto_gpu and has_accel)
        segnet_use_gpu = force_gpu or (
            auto_gpu and (has_accel or bool(coreml_available()))
        )
    coreml_encoder = False

    download_weights(segnet_use_gpu, transformer_use_gpu, coreml_encoder)
    config = _build_processing_config(
        enable_debug=args.debug,
        enable_cache=args.cache,
        transformer_use_gpu=transformer_use_gpu,
        segnet_use_gpu=segnet_use_gpu,
        coreml_encoder=coreml_encoder,
        title_detection=not args.no_title,
    )
    xml_args = XmlGeneratorArguments(False, None, None)
    xml_path = _replace_extension(args.image, ".musicxml")
    result = process_image(args.image, config, xml_args)
    if isinstance(result, str) and result:
        xml_path = result
    if not os.path.exists(xml_path):
        print(f"HOMR did not write {xml_path}", file=sys.stderr)
        return 1
    print(xml_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
