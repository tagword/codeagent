"""Tests for MiniMax bubble TTS helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from codeagent.core import speech_synth


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    return tmp_path


def _write_minimax_mcp(base: Path, *, key: str = "sk-test") -> None:
    cfg_dir = base / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mcp.json").write_text(
        """{
  "servers": {
    "MiniMax": {
      "enabled": true,
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "%s",
        "MINIMAX_API_HOST": "https://api.minimaxi.com"
      }
    }
  }
}"""
        % key,
        encoding="utf-8",
    )


def test_minimax_tts_not_configured_without_mcp(agent_home) -> None:
    assert speech_synth.minimax_tts_configured(agent_home) is False
    assert speech_synth.synthesize_minimax_speech("你好", agent_home) is None


def test_minimax_tts_from_llm_preset(agent_home) -> None:
    import json

    cfg = agent_home / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "seed.models.json").write_text(
        json.dumps(
            [
                {
                    "id": "mm-chat",
                    "name": "MiniMax · MiniMax-M2.7",
                    "provider": "minimax",
                    "base_url": "https://api.minimaxi.com/v1",
                    "model": "MiniMax-M2.7",
                    "api_key": "sk-from-preset",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert speech_synth.minimax_tts_configured(agent_home) is True
    key, host = speech_synth.get_minimax_tts_credentials(agent_home)
    assert key == "sk-from-preset"
    assert host == "https://api.minimaxi.com"


def test_minimax_tts_synthesize(agent_home, monkeypatch) -> None:
    _write_minimax_mcp(agent_home)
    assert speech_synth.minimax_tts_configured(agent_home) is True

    fake_hex = "ffd8ffe0".ljust(8, "0")  # arbitrary bytes as hex

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "base_resp": {"status_code": 0},
                "data": {"audio": fake_hex, "status": 2},
            }

    with patch("codeagent.core.speech_synth.requests.post", return_value=FakeResp()) as post:
        out = speech_synth.synthesize_minimax_speech("你好世界", agent_home)

    assert out is not None
    audio, mime = out
    assert mime == "audio/mpeg"
    assert audio == bytes.fromhex(fake_hex)
    post.assert_called_once()
    url = post.call_args[0][0]
    assert url.endswith("/v1/t2a_v2")
    payload = post.call_args[1]["json"]
    assert payload["text"] == "你好世界"
    assert payload["stream"] is False
    assert payload["voice_setting"]["voice_id"] == "male-qn-qingse"


def test_minimax_tts_custom_voice(agent_home, monkeypatch) -> None:
    _write_minimax_mcp(agent_home)
    fake_hex = "ffd8ffe0".ljust(8, "0")

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"base_resp": {"status_code": 0}, "data": {"audio": fake_hex}}

    with patch("codeagent.core.speech_synth.requests.post", return_value=FakeResp()) as post:
        out = speech_synth.synthesize_minimax_speech(
            "测试",
            agent_home,
            voice_id="female-shaonv",
            model="speech-2.8-hd",
        )

    assert out is not None
    assert post.call_args[1]["json"]["model"] == "speech-2.8-hd"
    assert post.call_args[1]["json"]["voice_setting"]["voice_id"] == "female-shaonv"


def test_minimax_tts_quota_error(agent_home, monkeypatch) -> None:
    _write_minimax_mcp(agent_home, key="sk-cp-test-token")

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "base_resp": {
                    "status_code": 2056,
                    "status_msg": "usage limit exceeded, 5-hour usage limit reached for Token Plan Plus (0/0 used)",
                },
                "data": {},
            }

    with patch("codeagent.core.speech_synth.requests.post", return_value=FakeResp()):
        out = speech_synth.synthesize_minimax_speech_with_detail("你好", agent_home)

    assert out.ok is False
    assert out.status_code == 2056
    assert "0/0" in out.error
    assert "按量" in out.error
    assert speech_synth.tts_http_status_for_outcome(out) == 429


def test_minimax_tts_prefers_dedicated_key(agent_home, monkeypatch) -> None:
    cfg_dir = agent_home / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mcp.json").write_text(
        """{
  "servers": {
    "MiniMax": {
      "enabled": true,
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "sk-cp-mcp",
        "MINIMAX_TTS_API_KEY": "sk-api-paygo",
        "MINIMAX_API_HOST": "https://api.minimaxi.com"
      }
    }
  }
}""",
        encoding="utf-8",
    )
    key, host = speech_synth.get_minimax_tts_credentials(agent_home)
    assert key == "sk-api-paygo"
    assert host == "https://api.minimaxi.com"
