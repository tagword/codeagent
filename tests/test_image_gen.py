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

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp):
        from seed_tools.image_gen_tools import image_generate

        raw = asyncio.run(image_generate(prompt="a red circle on white background", n=1))
    payload = json.loads(raw)
    assert payload.get("images")
    assert payload["images"][0]["attachment_id"]
    assert "attachment:" in payload.get("summary", "")


@pytest.fixture
def agent_home_minimax(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    presets = [
        {
            "id": "mm-image",
            "name": "MiniMax 生图",
            "provider": "minimax",
            "base_url": "https://api.minimaxi.com/v1",
            "model": "image-01",
            "api_key": "test-key",
            "supports_image_gen": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_image_generate_minimax(agent_home_minimax) -> None:
    import asyncio

    from seed.core.agent_context import set_active_image_gen_preset, set_active_llm_session

    set_active_llm_session("default::sess-mm")
    set_active_image_gen_preset("mm-image")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    b64 = base64.standard_b64encode(png).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"image_base64": [b64]},
    }

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp) as post:
        from seed_tools.image_gen_tools import image_generate

        raw = asyncio.run(
            image_generate(prompt="女孩在图书馆", size="9:16", n=1)
        )
        call_args = post.call_args
        assert "image_generation" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["model"] == "image-01"
        assert body["aspect_ratio"] == "9:16"
        assert body["response_format"] == "base64"

    payload = json.loads(raw)
    assert payload.get("provider") == "minimax"
    assert payload.get("images")


@pytest.fixture
def agent_home_volcengine(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    presets = [
        {
            "id": "ark-img",
            "name": "方舟 Seedream",
            "provider": "volcengine",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "doubao-seedream-5-0-lite",
            "api_key": "test-key",
            "supports_image_gen": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_image_generate_volcengine(agent_home_volcengine) -> None:
    import asyncio

    from seed.core.agent_context import set_active_image_gen_preset, set_active_llm_session

    set_active_llm_session("default::sess-ark")
    set_active_image_gen_preset("ark-img")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    b64 = base64.standard_b64encode(png).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"b64_json": b64}]}

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp) as post:
        from seed_tools.image_gen_tools import image_generate

        raw = asyncio.run(image_generate(prompt="一只猫", size="2K", n=1))
        body = post.call_args[1]["json"]
        assert body["model"] == "doubao-seedream-5-0-lite"
        assert body["size"] == "2K"
        assert body["sequential_image_generation"] == "disabled"
        assert "ark.cn-beijing.volces.com" in post.call_args[0][0]

    payload = json.loads(raw)
    assert payload.get("provider") == "volcengine"
    assert payload.get("images")


def test_image_generate_volcengine_i2i(agent_home_volcengine) -> None:
    import asyncio

    from seed.core.agent_context import set_active_image_gen_preset, set_active_llm_session

    set_active_llm_session("default::sess-ark2")
    set_active_image_gen_preset("ark-img")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    b64 = base64.standard_b64encode(png).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"b64_json": b64}]}

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp) as post:
        from seed_tools.image_gen_tools import image_generate

        asyncio.run(
            image_generate(
                prompt="换成演唱会背景",
                reference_image_urls=["https://example.com/ref.png"],
            )
        )
        assert post.call_args[1]["json"]["image"] == "https://example.com/ref.png"
