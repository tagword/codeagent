"""Web UI session endpoints — split out of ``webui_api_app``.

Mounted at ``/api/ui``. These handlers need ``project_root`` (via the factory)
plus shared runtime state (``SESSIONS``/``_memkey``/``_running_list``) from the
``server`` package. Pure helpers defined in ``webui_api_app`` are imported lazily
inside each handler to avoid a circular import (this module is imported by
``webui_api_app``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from seed.core.llm_sess import (
    archive_stored_llm_session,
    delete_stored_session,
    list_stored_sessions_meta,
    load_chat_session_from_disk,
    load_or_create_chat_session,
)
from seed.core.proj_reg import (
    list_project_sessions_meta,
    list_projects,
    unregister_session,
)

from . import SESSIONS, _memkey, _running_list

logger = logging.getLogger(__name__)


def build_sessions_routes(project_root: Path) -> list[Route]:
    """Return the session routes for ``webui_api_app``."""

    async def api_sessions(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID, _default_agent_id
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        try:
            lim = int(request.query_params.get("limit") or "80")
        except ValueError:
            lim = 80
        pid = (request.query_params.get("project_id") or "").strip()
        if pid == _UNASSIGNED_PROJECT_ID:
            rows = list_stored_sessions_meta(
                limit=lim, agent_id=aid,
                filter_by_project=True, filter_project_id="",
            )
        elif pid:
            rows = list_stored_sessions_meta(
                limit=lim,
                agent_id=aid,
                filter_by_project=True,
                filter_project_id=pid,
            )
        else:
            rows = list_stored_sessions_meta(limit=lim, agent_id=aid, filter_by_project=False)

        # Annotate each row with whether it has any per-session model-stack override
        # so the sidebar can show a 📌 badge without re-fetching every session.
        _model_stack_keys = (
            "llm_id", "vision_llm_id", "image_gen_llm_id",
            "audio_llm_id", "music_llm_id", "video_gen_llm_id",
        )
        # context_usage 已由 registry SQLite 缓存提供（快速路径）。
        # model_stack_overrides 仍需加载 session JSON 来解析（低频字段，走快捷加载）。
        for r in rows:
            try:
                sid = r.get("session_id") if isinstance(r, dict) else None
                if not isinstance(sid, str) or not sid.strip():
                    r["model_stack_overrides"] = {"count": 0, "has_any": False}
                    continue
                # 使用 registry 缓存的 context_usage（不含则回退加载 session JSON）
                r["context_usage"] = r.get("context_usage")
                # model_stack_overrides 需加载 session JSON
                chat_sess = load_or_create_chat_session(sid.strip(), aid)
                md = chat_sess.metadata if isinstance(chat_sess.metadata, dict) else {}
                present = [k for k in _model_stack_keys if isinstance(md.get(k), str) and md.get(k).strip()]
                r["model_stack_overrides"] = {
                    "count": len(present),
                    "has_any": bool(present),
                    "keys": present,
                }
                # 回退：registry 无缓存时从 session JSON 获取
                if r["context_usage"] is None:
                    r["context_usage"] = md.get("context_usage")
            except Exception:
                r["model_stack_overrides"] = {"count": 0, "has_any": False}

        return JSONResponse({"sessions": rows})

    async def api_sessions_running(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _default_agent_id
        """返回当前正在执行中的会话 ID 列表（用于页面刷新后恢复心跳指示）。"""
        aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
        running = _running_list(aid)
        return JSONResponse({"running": running})

    async def api_session_history(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import (
            _default_agent_id,
            _resolve_project_id,
            _session_history_json_for_session,
        )
        """Chat history for Web UI bubbles (projection of Session.messages)."""
        try:
            sid = (request.query_params.get("session_id") or "").strip()
            aid = (request.query_params.get("agent_id") or "").strip() or _default_agent_id()
            pid = _resolve_project_id((request.query_params.get("project_id") or "").strip())
            bb = request.query_params.get("before_block_index")
            before_i: int | None = None
            if bb is not None and str(bb).strip() != "":
                try:
                    before_i = int(bb)
                except ValueError:
                    before_i = None

            if not sid:
                return JSONResponse({"detail": "session_id required"}, status_code=400)

            mkey = _memkey(aid, sid)
            sess = SESSIONS.get(mkey)
            if sess is None:
                sess = load_chat_session_from_disk(sid, aid, pid or None)
            if sess is None:
                return JSONResponse(
                    {
                        "messages": [],
                        "first_block_index": None,
                        "has_more_older": False,
                        "truncated_start": False,
                    }
                )
            return JSONResponse(_session_history_json_for_session(sess, before_i))
        except Exception as e:
            logger.exception("api_session_history failed")
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def api_session_archive(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _archive_session_path, _locate_session_file, _resolve_project_id
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        sid = str(body.get("session_id") or "").strip()
        aid = str(body.get("agent_id") or "").strip()
        pid = _resolve_project_id(str(body.get("project_id") or "").strip())
        ok = archive_stored_llm_session(sid, aid, pid or None)
        if not ok:
            loc = _locate_session_file(sid, aid, pid)
            ok = bool(loc and loc.is_file() and _archive_session_path(loc))
        if not ok:
            return JSONResponse({"detail": "archive failed"}, status_code=400)
        SESSIONS.pop(_memkey(aid, sid), None)
        return JSONResponse({"ok": True})

    async def api_session_delete(request: Request) -> JSONResponse:
        from codeagent.server.webui_api_app import _locate_session_file, _resolve_project_id
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        sid = str(body.get("session_id") or "").strip()
        aid = str(body.get("agent_id") or "").strip()
        pid = _resolve_project_id(str(body.get("project_id") or "").strip())
        ok = delete_stored_session(sid, aid, pid or None)
        if not ok:
            loc = _locate_session_file(sid, aid, pid)
            if loc and loc.is_file():
                try:
                    loc.unlink()
                    ok = True
                except OSError:
                    ok = False
            # fallback 删除了文件但可能未清理 registry，补一个全项目扫描清理
            if ok and sid:
                for proj in list_projects(aid):
                    proj_pid = str(proj.get("id") or "").strip()
                    if proj_pid and sid in list_project_sessions_meta(aid, proj_pid):
                        unregister_session(aid, proj_pid, sid)
                        break
        if not ok:
            return JSONResponse({"detail": "delete failed"}, status_code=400)
        SESSIONS.pop(_memkey(aid, sid), None)
        return JSONResponse({"ok": True})

    return [
        Route("/sessions", api_sessions, methods=["GET"]),
        Route("/sessions/running", api_sessions_running, methods=["GET"]),
        Route("/session/history", api_session_history, methods=["GET"]),
        Route("/session/archive", api_session_archive, methods=["POST"]),
        Route("/session/delete", api_session_delete, methods=["POST"]),
    ]
