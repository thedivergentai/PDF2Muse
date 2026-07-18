"""Adapter package for pluggable OMR backends."""

from .base import AdapterStatus, OmrAdapter, OmrOptions, PageResult
from .legato import LegatoAdapter
from .oemer import OemerAdapter
from .registry import (
    adapter_healthchecks,
    create_adapter,
    resolve_auto_backend,
    resolve_backend_config,
)

__all__ = [
    "AdapterStatus",
    "LegatoAdapter",
    "OemerAdapter",
    "OmrAdapter",
    "OmrOptions",
    "PageResult",
    "adapter_healthchecks",
    "create_adapter",
    "resolve_auto_backend",
    "resolve_backend_config",
]
