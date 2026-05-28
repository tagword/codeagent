"""Image generation tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeagent.core.image_gen_models import (
    list_image_gen_presets,
    preset_supports_image_gen_id,
    resolve_image_gen_preset,
)


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    presets = [
        {
            "id": "dalle",
            "name": "DALL-E",
            "base_url": "https://api.openai.com/v1",
            "model": "dall-e-3",
            "supports_image_gen": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_list_image_gen_presets(agent_home) -> None:
    presets = list_image_gen_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "dalle"


def test_resolve_image_gen_preset(agent_home) -> None:
    p = resolve_image_gen_preset("dalle")
    assert p["model"] == "dall-e-3"


def test_preset_supports_image_gen_id(agent_home) -> None:
    assert preset_supports_image_gen_id("dalle") is True
    assert preset_supports_image_gen_id("missing") is False


def test_image_generate_saves_attachment(agent_home, monkeypatch) -> None:
    import asyncio

    from seed.core.agent_context import set_active_image_gen_preset, set_active_llm_session

    set_active_llm_session("default::sess-1")
    set_active_image_gen_preset("dalle")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    b64 = base64.standard_b64encode(png).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"b64_json": b64}]}

    with patch("seed_tools.image_gen_tools.requests.post", return_value=mock_resp):
        from seed_tools.image_gen_tools import image_generate

        raw = asyncio.run(image_generate(prompt="a red circle on white background", n=1))
    payload = json.loads(raw)
    assert payload.get("images")
    assert payload["images"][0]["attachment_id"]
    assert "attachment:" in payload.get("summary", "")
