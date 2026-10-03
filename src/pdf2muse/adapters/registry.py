"""OMR adapter registry and backend cascade resolution."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Union

from ..legato_env import load_legato_env_defaults
from ..oemer_utils import ModelBackendConfig, get_model_backend_config
from .base import AdapterStatus, OmrAdapter
from .homr import HomrAdapter
from .legato import LegatoAdapter
from .oemer import OemerAdapter

logger = logging.getLogger(__name__)

load_legato_env_defaults()


def resolve_auto_backend(
    *,
    checkpoint_dir: Optional[Union[Path, str]] = None,
) -> str:
    """Pick the highest-quality backend available on this machine."""

    allow_legato = os.environ.get("PDF2MUSE_ALLOW_LEGATO_AUTO") == "1"
    legato = LegatoAdapter()
    if allow_legato and legato.healthcheck().available:
        logger.info("Auto backend selected: legato-experimental")
        return "legato-experimental"
    # AGPL HOMR is never auto-selected unless explicitly opted in.
    # homr-experimental is never auto-selected.
    allow_homr = os.environ.get("PDF2MUSE_ALLOW_HOMR_AUTO") == "1"
    if allow_homr and HomrAdapter().healthcheck().available:
        logger.info("Auto backend selected: homr")
        return "homr"
    if checkpoint_dir:
        return "oemer-custom"
    logger.info("Auto backend selected: oemer-stock")
    return "oemer-stock"


def create_adapter(
    backend: ModelBackendConfig,
    *,
    oemer_retries: bool = True,
    quality_report: bool = True,
    keep_page_artifacts: bool = False,
    artifact_root: Optional[Path] = None,
) -> OmrAdapter:
    """Instantiate the adapter for a model backend configuration."""

    if backend.name in {"homr", "homr-experimental"} or backend.kind == "homr":
        return HomrAdapter()
    if backend.name == "legato-experimental":
        return LegatoAdapter()
    if backend.kind == "adapter":
        # Unknown adapter names fall through to Legato for backward compatibility
        # of tests that only set kind="adapter"; prefer explicit names above.
        return LegatoAdapter()
    return OemerAdapter(
        retries=oemer_retries,
        quality_report=quality_report,
        keep_page_artifacts=keep_page_artifacts,
        artifact_root=artifact_root,
    )


def adapter_healthchecks() -> list[AdapterStatus]:
    """Return health status for all registered adapters."""

    return [
        OemerAdapter().healthcheck(),
        LegatoAdapter().healthcheck(),
        HomrAdapter().healthcheck(),
    ]


def resolve_backend_config(
    model_backend: str,
    *,
    checkpoint_dir: Optional[Union[Path, str]] = None,
) -> ModelBackendConfig:
    """Resolve model backend name, including ``auto`` cascade."""

    if model_backend == "auto":
        model_backend = resolve_auto_backend(checkpoint_dir=checkpoint_dir)
    return get_model_backend_config(model_backend, checkpoint_dir=checkpoint_dir)
