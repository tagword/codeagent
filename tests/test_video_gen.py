"""Video generation tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeagent.core.video_models import (
    list_video_gen_presets,
    preset_supports_video_gen_id,
    resolve_video_gen_preset,
)


@pytest.fixture
def agent_home_agnes_video(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    presets = [
        {
            "id": "agnes-video",
            "name": "Agnes Video",
            "provider": "agnes",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "model": "agnes-video-v2.0",
            "api_key": "test-key",
            "supports_video_gen": True,
        },
    ]
    (cfg / "seed.models.json").write_text(json.dumps(presets), encoding="utf-8")
    return tmp_path


def test_list_video_gen_presets(agent_home_agnes_video) -> None:
    presets = list_video_gen_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "agnes-video"


def test_resolve_video_gen_preset(agent_home_agnes_video) -> None:
    p = resolve_video_gen_preset("agnes-video")
    assert p["model"] == "agnes-video-v2.0"


def test_preset_supports_video_gen_id(agent_home_agnes_video) -> None:
    assert preset_supports_video_gen_id("agnes-video") is True
    assert preset_supports_video_gen_id("missing") is False


def test_video_generate_saves_attachment(agent_home_agnes_video) -> None:
    import asyncio

    from seed.core.agent_context import set_active_llm_session, set_active_video_gen_preset

    set_active_llm_session("default::sess-video")
    set_active_video_gen_preset("agnes-video")

    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {
        "id": "task_123",
        "status": "queued",
        "progress": 0,
    }
    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "id": "task_123",
        "status": "completed",
        "progress": 100,
        "video_url": "https://storage.example.com/out.mp4",
    }
    dl_resp = MagicMock()
    dl_resp.content = mp4
    dl_resp.raise_for_status = MagicMock()

    def fake_post(url, **kwargs):
        assert url.endswith("/videos")
        body = kwargs["json"]
        assert body["model"] == "agnes-video-v2.0"
        assert body["prompt"] == "A cat on the beach at sunset"
        return create_resp

    def fake_get(url, **kwargs):
        if url.endswith("/out.mp4"):
            return dl_resp
        assert url.endswith("/task_123")
        return poll_resp

    with patch("seed.core.model_providers.requests.post", side_effect=fake_post), patch(
        "seed.core.model_providers.requests.get", side_effect=fake_get
    ), patch("seed.core.model_providers.time.sleep"):
        from seed_tools.video_gen import video_generate

        raw = asyncio.run(
            video_generate(
                prompt="A cat on the beach at sunset",
                num_frames=121,
                frame_rate=24,
            )
        )

    payload = json.loads(raw)
    assert payload.get("video", {}).get("attachment_id")
    assert "attachment:" in payload.get("summary", "")


def test_normalize_video_num_frames() -> None:
    from seed_model_providers import normalize_video_num_frames

    assert normalize_video_num_frames(121) == 121
    assert normalize_video_num_frames(125) == 121
    assert normalize_video_num_frames(441) == 441
