"""Audio/video media tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeagent.core.attachments import (
    message_has_audio_attachments,
    message_has_video_attachments,
    mime_allowed,
    save_attachment,
)
from codeagent.core.audio_models import list_audio_presets, resolve_audio_preset


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "env").write_text("SEED_LLM_BASEURL=https://example.test/v1\n", encoding="utf-8")
    return tmp_path


def test_mime_allowed_video_audio() -> None:
    assert mime_allowed("video/mp4", "clip.mp4") is True
    assert mime_allowed("audio/mpeg", "a.mp3") is True


def test_message_has_video_and_audio() -> None:
    assert message_has_video_attachments({"attachments": [{"kind": "video"}]}) is True
    assert message_has_audio_attachments({"attachments": [{"kind": "audio"}]}) is True


def test_save_video_attachment(agent_home, monkeypatch) -> None:
    meta = save_attachment(
        agent_id="default",
        session_id="s1",
        raw_bytes=b"\x00" * 128,
        filename="clip.mp4",
        mime="video/mp4",
    )
    assert meta.kind == "video"


def test_list_audio_presets(agent_home) -> None:
    cfg = agent_home / "config"
    (cfg / "seed.models.json").write_text(
        json.dumps(
            [{"id": "w", "name": "W", "base_url": "https://x/v1", "model": "whisper-1", "supports_audio": True}]
        ),
        encoding="utf-8",
    )
    assert len(list_audio_presets()) == 1
    p = resolve_audio_preset("w")
    assert p["model"] == "whisper-1"


def test_audio_transcribe_mock(agent_home) -> None:
    import asyncio

    cfg = agent_home / "config"
    (cfg / "seed.models.json").write_text(
        json.dumps(
            [
                {
                    "id": "whisper",
                    "name": "Whisper",
                    "base_url": "https://api.openai.com/v1",
                    "model": "whisper-1",
                    "supports_audio": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    from seed.core.agent_context import set_active_audio_preset, set_active_llm_session

    set_active_llm_session("default::s1")
    set_active_audio_preset("whisper")

    meta = save_attachment(
        agent_id="default",
        session_id="s1",
        raw_bytes=b"RIFF" + b"\x00" * 64,
        filename="test.wav",
        mime="audio/wav",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "hello world"}

    with patch("seed_tools.media.requests.post", return_value=mock_resp):
        from seed_tools.media import audio_transcribe

        raw = asyncio.run(audio_transcribe(attachment_id=meta.id))
    payload = json.loads(raw)
    assert payload.get("transcript") == "hello world"
