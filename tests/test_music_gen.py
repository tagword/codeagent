"""Music generation tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeagent.core.music_models import (
    list_music_presets,
    preset_supports_music_id,
    resolve_music_preset,
)


@pytest.fixture
def agent_home_minimax_music(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    presets = [
        {
            "id": "mm-music",
            "name": "MiniMax 音乐",
            "provider": "minimax",
            "base_url": "https://api.minimaxi.com/v1",
            "model": "music-2.6",
            "api_key": "test-key",
            "supports_music": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_list_music_presets(agent_home_minimax_music) -> None:
    presets = list_music_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "mm-music"


def test_resolve_music_preset(agent_home_minimax_music) -> None:
    p = resolve_music_preset("mm-music")
    assert p["model"] == "music-2.6"


def test_preset_supports_music_id(agent_home_minimax_music) -> None:
    assert preset_supports_music_id("mm-music") is True
    assert preset_supports_music_id("missing") is False


def test_music_generate_saves_attachment(agent_home_minimax_music) -> None:
    import asyncio

    from seed.core.agent_context import set_active_llm_session, set_active_music_preset

    set_active_llm_session("default::sess-music")
    set_active_music_preset("mm-music")

    mp3 = b"ID3" + b"\x00" * 64
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 0, "status_msg": "success"},
        "data": {"status": 2, "audio": mp3.hex()},
        "extra_info": {"music_duration": 30000, "music_sample_rate": 44100},
    }

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp) as post:
        from seed_tools.music_gen_tools import music_generate

        raw = asyncio.run(
            music_generate(
                prompt="Pop, upbeat, summer",
                lyrics="[Verse]\nHello world\n[Chorus]\nSing along",
            )
        )
        call_args = post.call_args
        assert "music_generation" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["model"] == "music-2.6"
        assert body["output_format"] == "hex"
        assert "[Verse]" in body["lyrics"]

    payload = json.loads(raw)
    assert payload.get("audio", {}).get("attachment_id")
    assert "attachment:" in payload.get("summary", "")


def test_music_generate_instrumental(agent_home_minimax_music) -> None:
    import asyncio

    from seed.core.agent_context import set_active_llm_session, set_active_music_preset

    set_active_llm_session("default::sess-music2")
    set_active_music_preset("mm-music")

    mp3 = b"ID3" + b"\x00" * 32
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "base_resp": {"status_code": 0},
        "data": {"status": 2, "audio": mp3.hex()},
    }

    with patch("seed.core.model_providers.requests.post", return_value=mock_resp) as post:
        from seed_tools.music_gen_tools import music_generate

        raw = asyncio.run(
            music_generate(
                prompt="Lo-fi chill beats",
                is_instrumental=True,
            )
        )
        body = post.call_args[1]["json"]
        assert body["is_instrumental"] is True

    payload = json.loads(raw)
    assert payload["is_instrumental"] is True
