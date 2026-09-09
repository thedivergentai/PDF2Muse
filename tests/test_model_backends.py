from pathlib import Path

import pytest

from pdf2muse.oemer_utils import (
    OEMER_CHECKPOINT_ENV,
    ensure_checkpoints,
    get_checkpoint_dir,
    get_model_backend_config,
    list_model_backend_configs,
    resolve_oemer_device,
)


def test_resolve_oemer_device_auto_uses_cuda_when_available(monkeypatch):
    monkeypatch.setattr("pdf2muse.oemer_utils.cuda_ep_available", lambda: True)
    assert resolve_oemer_device("auto") == "cuda"
    monkeypatch.setattr("pdf2muse.oemer_utils.cuda_ep_available", lambda: False)
    assert resolve_oemer_device("auto") == "cpu"
    assert resolve_oemer_device("cpu") == "cpu"
    assert resolve_oemer_device("CUDA") == "cuda"


def test_get_checkpoint_dir_uses_environment_override(monkeypatch, tmp_path):
    custom_dir = tmp_path / "custom-checkpoints"
    monkeypatch.setenv(OEMER_CHECKPOINT_ENV, str(custom_dir))

    assert get_checkpoint_dir() == custom_dir.resolve()


def test_model_backend_config_describes_stock_oemer():
    config = get_model_backend_config("oemer-stock")

    assert config.name == "oemer-stock"
    assert config.kind == "oemer"
    assert config.checkpoint_dir is None
    assert config.experimental is False


def test_model_backend_config_supports_custom_oemer_checkpoints(tmp_path):
    config = get_model_backend_config("oemer-custom", checkpoint_dir=tmp_path)

    assert config.name == "oemer-custom"
    assert config.kind == "oemer"
    assert config.checkpoint_dir == tmp_path.resolve()
    assert config.experimental is True


def test_model_backend_config_lists_replacement_adapter():
    names = [config.name for config in list_model_backend_configs()]

    assert "oemer-stock" in names
    assert "oemer-custom" in names
    assert "legato-experimental" in names
    assert "homr-experimental" in names


def test_homr_backend_is_experimental_agpl_slot():
    config = get_model_backend_config("homr-experimental")
    assert config.kind == "adapter"
    assert config.experimental is True
    assert "AGPL" in config.description

    with pytest.raises(ValueError, match="Unknown model backend"):
        get_model_backend_config("unknown-backend")


def test_custom_checkpoint_validation_does_not_download_stock_weights(tmp_path):
    with pytest.raises(FileNotFoundError, match="Custom checkpoint directory is incomplete"):
        ensure_checkpoints(checkpoint_dir=tmp_path, download_missing=False)
