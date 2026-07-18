"""Tests for OMR adapter registry."""

from pdf2muse.adapters import (
    LegatoAdapter,
    OemerAdapter,
    create_adapter,
    resolve_auto_backend,
    resolve_backend_config,
)
from pdf2muse.oemer_utils import get_model_backend_config


def test_create_oemer_adapter():
    backend = get_model_backend_config("oemer-stock")
    adapter = create_adapter(backend)
    assert isinstance(adapter, OemerAdapter)


def test_create_legato_adapter():
    backend = get_model_backend_config("legato-experimental")
    adapter = create_adapter(backend)
    assert isinstance(adapter, LegatoAdapter)


def test_resolve_auto_backend_defaults_to_oemer(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_ALLOW_LEGATO_AUTO", raising=False)
    assert resolve_auto_backend() == "oemer-stock"


def test_resolve_auto_backend_can_select_legato_with_opt_in(monkeypatch):
    monkeypatch.setenv("PDF2MUSE_ALLOW_LEGATO_AUTO", "1")
    monkeypatch.setattr(
        "pdf2muse.adapters.registry.LegatoAdapter.healthcheck",
        lambda self: type("S", (), {"available": True})(),
    )
    assert resolve_auto_backend() == "legato-experimental"


def test_resolve_backend_config_auto(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_ALLOW_LEGATO_AUTO", raising=False)
    config = resolve_backend_config("auto")
    assert config.name == "oemer-stock"
