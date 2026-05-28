"""Multimodal api_chat and attachment API tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from codeagent.core.attachments import save_attachment
from codeagent.core.vision_models import list_vision_presets, preset_supports_vision_id
from codeagent.server.attachment_api import parse_chat_multimodal_body


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "seed.env").write_text("SEED_LLM_BASEURL=https://example.test/v1\n", encoding="utf-8")
    presets = [
        {
            "id": "main",
            "name": "Main",
            "base_url": "https://example.test/v1",
            "model": "deepseek-chat",
        },
        {
            "id": "vision1",
            "name": "Vision",
            "base_url": "https://example.test/v1",
            "model": "gpt-4o",
            "supports_vision": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_parse_chat_multimodal_body_text_only(agent_home) -> None:
    user_msg, att_ids, has_image, extra = parse_chat_multimodal_body(
        {"message": "hello", "session_id": "s1", "agent_id": "default"}
    )
    assert user_msg["content"] == "hello"
    assert att_ids == []
    assert has_image is False
    assert extra["session_id"] == "s1"


def test_parse_chat_multimodal_body_with_staged_attachment(agent_home) -> None:
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    meta = save_attachment(
        agent_id="default",
        session_id="s1",
        raw_bytes=raw,
        filename="x.png",
        mime="image/png",
    )
    user_msg, att_ids, has_image, _extra = parse_chat_multimodal_body(
        {
            "message": "see",
            "session_id": "s1",
            "attachment_ids": [meta.id],
        }
    )
    assert has_image is True
    assert meta.id in att_ids
    assert f"[attachment:{meta.id}" in user_msg["content"]


def test_list_vision_presets_filters(agent_home) -> None:
    presets = list_vision_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "vision1"


def test_preset_supports_vision_id(agent_home) -> None:
    assert preset_supports_vision_id("vision1") is True
    assert preset_supports_vision_id("main") is False


def test_api_attachment_upload(agent_home) -> None:
    from codeagent.server.app_factory import create_app

    app = create_app()
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    payload = {
        "session_id": "web-chat",
        "filename": "t.png",
        "mime": "image/png",
        "data_base64": base64.standard_b64encode(raw).decode("ascii"),
    }
    with TestClient(app) as client:
        r = client.post("/api/attachments", json=payload)
        assert r.status_code == 200
        j = r.json()
        assert j["id"]
        get_r = client.get(
            f"/api/attachments/{j['id']}",
            params={"session_id": "web-chat", "agent_id": "default"},
        )
        assert get_r.status_code == 200
        assert get_r.content.startswith(b"\x89PNG")


def test_api_chat_rejects_image_without_vision(agent_home) -> None:
    from codeagent.server.app_factory import create_app

    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    meta = save_attachment(
        agent_id="default",
        session_id="web-chat",
        raw_bytes=raw,
        filename="x.png",
        mime="image/png",
    )
    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={
                "session_id": "web-chat",
                "message": "look",
                "attachment_ids": [meta.id],
            },
        )
        assert r.status_code == 400
        assert "vision" in (r.json().get("detail") or "").lower()


def test_api_chat_text_backward_compatible(agent_home, monkeypatch) -> None:
    from codeagent.server.app_factory import create_app

    async def _fake_loop(*_a, **_k):
        return ("ok", None, [], [], {"usage": {}})

    monkeypatch.setattr(
        "seed.core.agent_runtime.run_llm_tool_loop",
        _fake_loop,
    )

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"session_id": "web-chat", "message": "hi"},
        )
        assert r.status_code == 200
        assert r.json().get("reply") == "ok"
