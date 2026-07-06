"""HTTP handlers for chat attachments."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

logger = logging.getLogger(__name__)


def _parse_body_json(body: bytes) -> dict[str, Any]:
    try:
        j = json.loads(body.decode("utf-8") or "{}")
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


async def api_attachment_upload(request: Request) -> JSONResponse:
    from codeagent.core import env as ca_env
    from codeagent.core.attachments import save_attachment, _max_count

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid json"}, status_code=400)

    agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
    session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
    filename = str(body.get("filename") or "upload.bin").strip() or "upload.bin"
    data_b64 = str(body.get("data_base64") or "").strip()
    if not data_b64:
        return JSONResponse({"detail": "data_base64 required"}, status_code=400)
    try:
        raw = base64.standard_b64decode(data_b64)
    except Exception:
        return JSONResponse({"detail": "invalid base64"}, status_code=400)
    mime = str(body.get("mime") or "").strip()
    try:
        meta = save_attachment(
            agent_id=agent_id,
            session_id=session_id,
            raw_bytes=raw,
            filename=filename,
            mime=mime,
        )
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("attachment upload failed")
        return JSONResponse({"detail": str(e)}, status_code=500)

    return JSONResponse(
        {
            "id": meta.id,
            "url": f"/api/attachments/{meta.id}?session_id={session_id}&agent_id={agent_id}",
            "meta": meta.to_dict(),
        }
    )


async def api_attachment_batch(request: Request) -> JSONResponse:
    from codeagent.core import env as ca_env
    from codeagent.core.attachments import save_attachment, _max_count, _dir_max_files

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid json"}, status_code=400)

    agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
    session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
    files = body.get("files")
    if not isinstance(files, list) or not files:
        return JSONResponse({"detail": "files array required"}, status_code=400)

    limit = min(_dir_max_files(), _max_count() * 4)
    attachment_ids: list[str] = []
    errors: list[str] = []
    truncated = False
    for item in files[: limit + 1]:
        if len(attachment_ids) >= limit:
            truncated = True
            break
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "file").strip()
        data_b64 = str(item.get("data_base64") or "").strip()
        if not data_b64:
            errors.append(f"missing data for {filename}")
            continue
        try:
            raw = base64.standard_b64decode(data_b64)
            meta = save_attachment(
                agent_id=agent_id,
                session_id=session_id,
                raw_bytes=raw,
                filename=filename,
                mime=str(item.get("mime") or "").strip(),
            )
            attachment_ids.append(meta.id)
        except Exception as e:
            errors.append(f"{filename}: {e}")

    return JSONResponse(
        {
            "attachment_ids": attachment_ids,
            "dir_label": str(body.get("dir_label") or "").strip() or None,
            "truncated": truncated,
            "errors": errors or None,
        }
    )


async def api_attachment_get(request: Request) -> Response:
    from codeagent.core import env as ca_env
    from codeagent.core.attachments import resolve_attachment_path
    import mimetypes

    attachment_id = request.path_params.get("attachment_id") or ""
    agent_id = str(request.query_params.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
    session_id = str(request.query_params.get("session_id") or "").strip()
    if not session_id:
        return JSONResponse({"detail": "session_id required"}, status_code=400)

    path = resolve_attachment_path(agent_id, session_id, attachment_id)
    if not path or not path.is_file():
        return JSONResponse({"detail": "not found"}, status_code=404)

    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        str(path),
        media_type=mime or "application/octet-stream",
        filename=path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


async def api_file_serve(request: Request) -> Response:
    """Serve local files from the server filesystem.
    
    Security: only serves files under /home/u2/ (agent workspace).
    Rejects '..' path traversal.
    """
    from pathlib import Path as _Path
    import mimetypes as _mime

    raw = request.query_params.get("path", "").strip()
    if not raw:
        return JSONResponse({"detail": "path query parameter required"}, status_code=400)

    # Path traversal protection
    if ".." in raw.split("/") or raw.startswith("~"):
        return JSONResponse({"detail": "invalid path"}, status_code=403)

    p = _Path(raw)
    if not p.is_absolute():
        return JSONResponse({"detail": "absolute path required"}, status_code=400)

    try:
        resolved = p.resolve(strict=False)
    except Exception:
        return JSONResponse({"detail": "invalid path"}, status_code=400)

    # Only allow files under /home/u2/
    allowed_prefix = "/home/u2/"
    if not str(resolved).startswith(allowed_prefix):
        return JSONResponse({"detail": "access denied"}, status_code=403)

    if not resolved.is_file():
        return JSONResponse({"detail": "not found"}, status_code=404)

    mt, _ = _mime.guess_type(str(resolved))
    return FileResponse(
        str(resolved),
        media_type=mt or "application/octet-stream",
        filename=resolved.name,
        headers={"Cache-Control": "private, max-age=300"},
    )


def parse_chat_multimodal_body(body: dict[str, Any]) -> tuple[str, list[str], bool, dict[str, Any]]:
    """Return (message_text, attachment_ids, has_image, extra)."""
    from codeagent.core.attachments import (
        ATTACHMENT_TAG_RE,
        build_user_message,
        message_has_audio_attachments,
        message_has_image_attachments,
        message_has_video_attachments,
        save_attachment,
        parse_image_dir_tags,
    )
    from codeagent.core import env as ca_env

    agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
    session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
    message = str(body.get("message") or "").strip()
    clear_vision = bool(body.get("clear_vision_context"))

    attachment_ids: list[str] = []
    raw_ids = body.get("attachment_ids")
    if isinstance(raw_ids, list):
        attachment_ids.extend(str(x).strip() for x in raw_ids if str(x).strip())

    metas = []
    inline = body.get("attachments")
    if isinstance(inline, list):
        for item in inline:
            if not isinstance(item, dict):
                continue
            data_b64 = str(item.get("data_base64") or "").strip()
            if not data_b64:
                continue
            try:
                raw = base64.standard_b64decode(data_b64)
                meta = save_attachment(
                    agent_id=agent_id,
                    session_id=session_id,
                    raw_bytes=raw,
                    filename=str(item.get("filename") or "upload"),
                    mime=str(item.get("mime") or "").strip(),
                )
                metas.append(meta)
                attachment_ids.append(meta.id)
            except Exception:
                pass

    for aid in attachment_ids:
        if not any(m.id == aid for m in metas):
            from codeagent.core.attachments import load_attachment_meta

            m = load_attachment_meta(agent_id, session_id, aid)
            if m:
                metas.append(m)

    dir_tags = parse_image_dir_tags(message)
    image_dir_tag = ""
    if dir_tags:
        rel, mx = dir_tags[0]
        image_dir_tag = f"[image_dir:{rel} max={mx}]"

    if not message and not metas and not dir_tags:
        raise ValueError("message or attachments required")

    user_msg = build_user_message(message, metas, image_dir_tag=image_dir_tag)
    has_image = message_has_image_attachments(user_msg) or bool(dir_tags)
    has_video = message_has_video_attachments(user_msg)
    has_audio = message_has_audio_attachments(user_msg)

    return user_msg, attachment_ids, has_image, {
        "clear_vision_context": clear_vision,
        "agent_id": agent_id,
        "session_id": session_id,
        "has_video": has_video,
        "has_audio": has_audio,
    }
