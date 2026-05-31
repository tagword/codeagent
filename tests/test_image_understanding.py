"""Image understanding: vision preset vs MiniMax MCP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeagent.core.attachments import save_attachment
from codeagent.core.image_understanding import (
    MCP_VISION_SENTINEL,
    image_attachment_allowed,
    minimax_mcp_configured,
    video_attachment_allowed,
)


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "seed.env").write_text(
        "SEED_LLM_BASEURL=https://example.test/v1\nSEED_MCP_ENABLED=1\n",
        encoding="utf-8",
    )
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


def _write_minimax_mcp(base: Path, *, key: str = "sk-test") -> None:
    mcp = {
        "servers": {
            "MiniMax": {
                "enabled": True,
                "transport": "stdio",
                "command": "uvx",
                "args": ["minimax-coding-plan-mcp", "-y"],
                "env": {
                    "MINIMAX_API_KEY": key,
                    "MINIMAX_API_HOST": "https://api.minimaxi.com",
                },
            }
        }
    }
    (base / "config" / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")


def test_minimax_mcp_configured(agent_home) -> None:
    assert minimax_mcp_configured(agent_home) is False
    _write_minimax_mcp(agent_home)
    assert minimax_mcp_configured(agent_home) is True


def test_image_attachment_allowed(agent_home) -> None:
    assert image_attachment_allowed("vision1") is True
    assert image_attachment_allowed("main") is False
    assert image_attachment_allowed("") is False
    _write_minimax_mcp(agent_home)
    assert image_attachment_allowed("") is True
    assert image_attachment_allowed(MCP_VISION_SENTINEL) is True


def test_video_requires_vision(agent_home) -> None:
    _write_minimax_mcp(agent_home)
    assert video_attachment_allowed("") is False
    assert video_attachment_allowed("vision1") is True


def test_api_chat_accepts_image_with_mcp_only(agent_home, monkeypatch) -> None:
    from codeagent.server.app_factory import create_app

    _write_minimax_mcp(agent_home)
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    meta = save_attachment(
        agent_id="default",
        session_id="web-chat",
        raw_bytes=raw,
        filename="x.png",
        mime="image/png",
    )

    async def _fake_loop(*_a, **_k):
        return ("ok", None, [], [], {"usage": {}})

    monkeypatch.setattr(
        "seed.core.agent_runtime.run_llm_tool_loop",
        _fake_loop,
    )

    app = create_app()
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={
                "session_id": "web-chat",
                "message": "look",
                "attachment_ids": [meta.id],
                "vision_llm_id": MCP_VISION_SENTINEL,
            },
        )
        assert r.status_code == 200
        assert r.json().get("reply") == "ok"
