"""Prove PDF2MUSE_OEMER_CHECKPOINT_DIR redirects oemer inference paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pdf2muse._oemer_common as common
from pdf2muse.oemer_utils import OEMER_CHECKPOINT_ENV


def test_checkpoint_dir_redirects_inference_model_path(monkeypatch, tmp_path):
    stock = tmp_path / "stock" / "checkpoints"
    custom = tmp_path / "custom" / "checkpoints"
    (stock / "seg_net").mkdir(parents=True)
    (custom / "seg_net").mkdir(parents=True)
    stock_model = stock / "seg_net" / "model.onnx"
    custom_model = custom / "seg_net" / "model.onnx"
    stock_model.write_bytes(b"stock")
    custom_model.write_bytes(b"custom")

    fake_oemer = MagicMock()
    fake_oemer.__file__ = str(tmp_path / "stock" / "__init__.py")
    captured: dict[str, str] = {}

    def fake_inference(model_path, img_path, *args, **kwargs):
        captured["model_path"] = str(model_path)
        return ("ok", "ok")

    fake_inference_mod = MagicMock()
    fake_inference_mod.inference = fake_inference

    monkeypatch.setenv(OEMER_CHECKPOINT_ENV, str(custom))
    monkeypatch.setitem(__import__("sys").modules, "oemer", fake_oemer)
    monkeypatch.setitem(__import__("sys").modules, "oemer.inference", fake_inference_mod)

    # Bypass import machinery used inside patch helper by injecting modules.
    import oemer
    import oemer.inference as inference_mod

    monkeypatch.setattr(oemer, "__file__", str(tmp_path / "stock" / "__init__.py"))
    monkeypatch.setattr(inference_mod, "inference", fake_inference)

    common._patch_oemer_checkpoint_dir()
    inference_mod.inference(str(stock_model), "img.png")
    assert captured["model_path"] == str(custom_model)
