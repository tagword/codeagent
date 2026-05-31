"""POST /api/tts — synthesize chat bubble text for playback."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from codeagent.core.speech_synth import (
    minimax_tts_configured,
    synthesize_minimax_speech_with_detail,
    tts_http_status_for_outcome,
)
from codeagent.core.tts_voices import normalize_tts_model, normalize_tts_voice_id


async def api_tts(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    text = str(body.get("text") or "").strip()
    if not text:
        return JSONResponse({"detail": "text required"}, status_code=422)
    if len(text) > 10000:
        return JSONResponse({"detail": "text too long (max 10000)"}, status_code=422)

    voice_id = normalize_tts_voice_id(body.get("voice_id"))
    model = normalize_tts_model(body.get("model"))

    if not minimax_tts_configured():
        return JSONResponse(
            {"detail": "MiniMax TTS not configured", "fallback": True},
            status_code=503,
        )

    out = synthesize_minimax_speech_with_detail(text, voice_id=voice_id, model=model)
    if not out.ok or out.audio is None:
        detail = out.error or "TTS synthesis failed"
        return JSONResponse(
            {
                "detail": detail,
                "fallback": True,
                "status_code": out.status_code,
            },
            status_code=tts_http_status_for_outcome(out),
        )

    return Response(content=out.audio, media_type=out.mime)
