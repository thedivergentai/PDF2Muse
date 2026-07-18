"""OMR adapter protocol and shared result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol


@dataclass(frozen=True)
class OmrOptions:
    """Per-page recognition options passed to an OMR adapter."""

    deskew: bool = True
    use_tf: bool = False
    device: str = "auto"
    quality_profile: str = "quality"
    line_threshold: Optional[float] = None
    timeout_seconds: int = 900
    save_cache: bool = False
    checkpoint_dir: Optional[Path] = None


@dataclass
class PageResult:
    """Outcome of recognizing one page image."""

    musicxml_path: Optional[Path] = None
    error: Optional[str] = None
    failure_class: Optional[str] = None
    backend: str = ""
    attempts: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterStatus:
    """Health check for one OMR backend."""

    name: str
    available: bool
    message: str
    requires_gpu: bool = False


class OmrAdapter(Protocol):
    """Contract for pluggable OMR backends."""

    name: str

    def healthcheck(self) -> AdapterStatus:
        """Return whether this adapter can run on the current machine."""

    def recognize_page(
        self,
        image_path: Path,
        output_dir: Path,
        options: OmrOptions,
    ) -> PageResult:
        """Run OMR on one page image and write MusicXML under output_dir."""
