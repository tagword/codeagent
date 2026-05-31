"""MiniMax text-to-speech (HTTP T2A) for Web UI bubble playback."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import requests

from seed.integrations.mcp_config import MINIMAX_MCP_SERVER_ID, get_server_config

from codeagent.core.tts_voices import (
    default_tts_model,
    default_tts_voice_id,
    normalize_tts_model,
    normalize_tts_voice_id,
)

logger = logging.getLogger(__name__)

_QUOTA_STATUS_CODES = frozenset({1002, 1008, 2056})


@dataclass(frozen=True)
class TtsSynthOutcome:
    audio: Optional[bytes] = None
    mime: str = "audio/mpeg"
    error: str = ""
    status_code: Optional[int] = None

    @property
    def ok(self) -> bool:
        return bool(self.audio)


def _base_resp_status_code(base_resp: object) -> tuple[int, str]:
    if not isinstance(base_resp, dict):
        return 0, ""
    raw_code = base_resp.get("status_code", 0)
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        code = 0
    msg = str(base_resp.get("status_msg") or "").strip()
    return code, msg


def _decode_t2a_audio(raw_audio: object, *, timeout: int) -> tuple[Optional[bytes], str]:
    if raw_audio is None:
        return None, ""
    audio_str = str(raw_audio).strip()
    if not audio_str:
        return None, ""
    if audio_str.startswith("http://") or audio_str.startswith("https://"):
        try:
            r = requests.get(audio_str, timeout=max(10, timeout))
            r.raise_for_status()
            mime = r.headers.get("Content-Type") or "audio/mpeg"
            return r.content, str(mime).split(";")[0].strip() or "audio/mpeg"
        except Exception:
            logger.debug("MiniMax TTS audio URL download failed", exc_info=True)
            return None, ""
    try:
        audio_bytes = bytes.fromhex(audio_str)
    except ValueError:
        logger.debug("MiniMax TTS invalid hex audio", exc_info=True)
        return None, ""
    if not audio_bytes:
        return None, ""
    return audio_bytes, "audio/mpeg"


def synthesize_minimax_speech_with_detail(
    text: str,
    base: Optional[Path] = None,
    *,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
) -> TtsSynthOutcome:
    """Return structured TTS result with MiniMax error details when synthesis fails."""
    key, host = get_minimax_tts_credentials(base)
    if not key:
        return TtsSynthOutcome(error="MiniMax TTS not configured")

    raw = (text or "").strip()
    if not raw:
        return TtsSynthOutcome(error="text required")
    raw = raw[: _max_tts_chars()]

    model_id = normalize_tts_model(model)
    voice = normalize_tts_voice_id(voice_id)

    payload = {
        "model": model_id,
        "text": raw,
        "stream": False,
        "output_format": "hex",
        "language_boost": "auto",
        "voice_setting": {
            "voice_id": voice,
            "speed": 1,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    try:
        timeout = int(os.environ.get("CODEAGENT_TTS_TIMEOUT_SEC", "120") or 120)
    except ValueError:
        timeout = 120

    try:
        resp = requests.post(
            _t2a_url(host),
            json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=max(10, timeout),
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.HTTPError as e:
        detail = ""
        try:
            err_body = e.response.json() if e.response is not None else {}
            br = err_body.get("base_resp") if isinstance(err_body, dict) else None
            code, msg = _base_resp_status_code(br)
            detail = msg or str(e)
            if code:
                return TtsSynthOutcome(error=detail or f"MiniMax TTS HTTP error ({code})", status_code=code)
        except Exception:
            detail = str(e)
        logger.warning("MiniMax TTS HTTP error: %s", detail or e)
        return TtsSynthOutcome(error=detail or "MiniMax TTS request failed")
    except Exception as e:
        logger.warning("MiniMax TTS request failed: %s", e, exc_info=True)
        return TtsSynthOutcome(error=str(e) or "MiniMax TTS request failed")

    if not isinstance(body, dict):
        return TtsSynthOutcome(error="MiniMax TTS returned invalid JSON")

    code, msg = _base_resp_status_code(body.get("base_resp"))
    if code != 0:
        logger.info("MiniMax TTS base_resp error: %s", body.get("base_resp"))
        return TtsSynthOutcome(
            error=_humanize_tts_error(code, msg, key=key),
            status_code=code,
        )

    data = body.get("data")
    if not isinstance(data, dict):
        return TtsSynthOutcome(error="MiniMax TTS returned no data")

    status = data.get("status")
    if status is not None:
        try:
            if int(status) != 2:
                return TtsSynthOutcome(
                    error=f"MiniMax TTS incomplete (status={status})",
                    status_code=code,
                )
        except (TypeError, ValueError):
            pass

    audio_bytes, mime = _decode_t2a_audio(data.get("audio"), timeout=timeout)
    if not audio_bytes:
        return TtsSynthOutcome(error=msg or "MiniMax TTS returned no audio", status_code=code)
    return TtsSynthOutcome(audio=audio_bytes, mime=mime or "audio/mpeg")


def synthesize_minimax_speech(
    text: str,
    base: Optional[Path] = None,
    *,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[Tuple[bytes, str]]:
    """Return (mp3 bytes, mime) or None when MiniMax TTS is not configured."""
    out = synthesize_minimax_speech_with_detail(
        text,
        base,
        voice_id=voice_id,
        model=model,
    )
    if not out.ok or out.audio is None:
        return None
    return out.audio, out.mime


def tts_http_status_for_outcome(out: TtsSynthOutcome) -> int:
    code = out.status_code
    if code in _QUOTA_STATUS_CODES:
        return 429
    if code in {1004, 2049}:
        return 401
    if code in {2013, 1042}:
        return 422
    return 502


def _max_tts_chars() -> int:
    try:
        return max(1, min(int(os.environ.get("CODEAGENT_TTS_MAX_CHARS", "2000") or 2000), 10000))
    except ValueError:
        return 2000


def _tts_api_key_from_env() -> str:
    from codeagent.core import env as ca_env

    return ca_env.pick_nonempty("CODEAGENT_TTS_API_KEY")


def _tts_api_key_from_mcp(base: Optional[Path] = None) -> tuple[str, str]:
    cfg = get_server_config(MINIMAX_MCP_SERVER_ID, base)
    if not cfg:
        return "", ""
    env = cfg.env or {}
    key = str(env.get("MINIMAX_TTS_API_KEY") or "").strip()
    if not key:
        return "", ""
    host = str(env.get("MINIMAX_TTS_API_HOST") or env.get("MINIMAX_API_HOST") or "https://api.minimaxi.com")
    return key, host.strip().rstrip("/")


def _humanize_tts_error(code: Optional[int], msg: str, *, key: str = "") -> str:
    base = (msg or "").strip() or (f"MiniMax TTS error (status_code={code})" if code else "MiniMax TTS failed")
    if code != 2056:
        return base
    if "0/0" in base or "Token Plan" in base:
        hint = (
            "Token Plan Key（sk-cp-…）通常可用于聊天，但 TTS（Speech）有独立的每日字符额度；"
            "当前返回 0/0 表示套餐未分配朗读额度，并非「已用完」。"
            "请在 MiniMax 开放平台「账户管理 → 接口密钥」创建按量 API Key，"
            "填到配置页「朗读 API Key（开放平台按量，可选）」后重试。"
        )
        if key.startswith("sk-cp-"):
            return f"{base}。{hint}"
        return f"{base}。{hint}"
    return base


def minimax_tts_configured(base: Optional[Path] = None) -> bool:
    key, _host = get_minimax_tts_credentials(base)
    return bool(key)


def get_minimax_tts_credentials(base: Optional[Path] = None) -> Tuple[str, str]:
    """TTS credentials: dedicated pay-as-you-go key first, then MCP / LLM preset."""
    tts_key = _tts_api_key_from_env()
    if tts_key:
        host = _host_from_preset_base_url(
            os.environ.get("CODEAGENT_TTS_API_HOST", "https://api.minimaxi.com")
        )
        return tts_key, host

    mcp_tts_key, mcp_tts_host = _tts_api_key_from_mcp(base)
    if mcp_tts_key:
        return mcp_tts_key, mcp_tts_host

    cfg = get_server_config(MINIMAX_MCP_SERVER_ID, base)
    if cfg:
        env = cfg.env or {}
        key = str(env.get("MINIMAX_API_KEY") or "").strip()
        if key:
            host = str(env.get("MINIMAX_API_HOST") or "https://api.minimaxi.com").strip().rstrip("/")
            return key, host
    return _minimax_credentials_from_llm_presets(base)


def _host_from_preset_base_url(base_url: str) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "https://api.minimaxi.com"
    if raw.endswith("/v1/t2a_v2"):
        return raw[: -len("/v1/t2a_v2")]
    if raw.endswith("/v1"):
        return raw[: -len("/v1")]
    return raw


def _minimax_credentials_from_llm_presets(base: Optional[Path] = None) -> Tuple[str, str]:
    """Use MiniMax LLM preset api_key (e.g. MiniMax-M2.7 chat) for T2A — same platform key."""
    try:
        from seed.core.llm_presets import get_default_preset_id, load_presets
        from seed.core.model_providers import resolve_provider_for_preset
    except Exception:
        return "", "https://api.minimaxi.com"

    default_id = get_default_preset_id().strip()
    ranked: list[tuple[int, str, str, str]] = []
    for p in load_presets():
        if resolve_provider_for_preset(p) != "minimax":
            continue
        key = str(p.get("api_key") or "").strip()
        if not key:
            continue
        pid = str(p.get("id") or "").strip()
        host = _host_from_preset_base_url(str(p.get("base_url") or ""))
        use_type = str(p.get("use_type") or "").strip().lower()
        if pid and pid == default_id:
            rank = 0
        elif use_type in ("", "chat") or "M2" in str(p.get("model") or ""):
            rank = 1
        else:
            rank = 2
        ranked.append((rank, pid, key, host))

    if not ranked:
        return "", "https://api.minimaxi.com"
    ranked.sort(key=lambda x: (x[0], x[1]))
    _rank, _pid, key, host = ranked[0]
    return key, host


def _t2a_url(host: str) -> str:
    base = (host or "").strip().rstrip("/")
    if base.endswith("/v1/t2a_v2"):
        return base
    if base.endswith("/v1"):
        return f"{base}/t2a_v2"
    return f"{base}/v1/t2a_v2"
