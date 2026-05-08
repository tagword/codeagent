"""Starlette HTTP / WebSocket application factory."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_app():
    import logging as logging_mod

    if not logging_mod.getLogger().handlers:
        logging_mod.basicConfig(
            level=os.environ.get("CODEAGENT_LOG_LEVEL", "INFO").upper(),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    from contextlib import asynccontextmanager

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse, Response
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.websockets import WebSocket

    from src.env_config import apply_codeagent_env_from_config
    from src.server_pkg.webui_api_app import build_webui_api_app

    apply_codeagent_env_from_config()

    try:
        from src.config_plane_pkg import ensure_default_config_files
        from src.config_plane_pkg import project_root as _pr

        ensure_default_config_files(_pr())
    except Exception:
        logger.exception("bootstrap config failed")

    from src.config_plane_pkg import project_root as project_root_fn
    from src.server_pkg._server_pkg_small_merged import _memkey, get_app_html, get_setup_html
    from src.webui_auth import WebUIAuthMiddleware, get_webui_token

    project_root = project_root_fn()

    # ── WebSocket 广播基础设施 ──
    WS_BY_SESSION: dict[str, set] = defaultdict(set)

    async def _broadcast_session_event(aid: str, sid: str, payload: dict) -> None:
        mkey = _memkey(aid, sid)
        msg = dict(payload)
        msg.setdefault("session_id", sid)
        msg.setdefault("agent_id", aid)
        for ws in list(WS_BY_SESSION.get(mkey, ())):
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    async def homepage(_: Request) -> HTMLResponse:
        from starlette.responses import RedirectResponse

        setup_marker = project_root / "config" / "codeagent.setup.json"
        done = False
        if setup_marker.is_file():
            try:
                j = json.loads(setup_marker.read_text(encoding="utf-8") or "{}")
                done = bool(j.get("done"))
            except Exception:
                done = False
        if not done:
            return RedirectResponse("/setup", status_code=302)
        return HTMLResponse(get_app_html())

    async def setup_page(_: Request) -> HTMLResponse:
        return HTMLResponse(get_setup_html())

    async def api_chat(request: Request) -> JSONResponse:
        from src.agent_context import set_active_llm_session
        from src.agent_runtime_pkg import (
            build_api_projection_messages,
            default_system_prompt,
            maybe_compact_context_messages,
            merge_llm_tail_into_full,
            run_llm_tool_loop,
        )
        from src.llm_exec_pkg import LLMError
        from src.llm_presets import llm_executor_from_resolved, resolve_preset
        from src.llm_sess_pkg import load_or_create_chat_session, merge_fresh_system, persist_chat_session
        from src.mem_bridge_pkg import apply_episodic_to_messages
        from src.server_pkg._server_pkg_small_merged import SESSIONS, tools_for_agent
        from src.session_title import maybe_llm_refresh_session_title

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)

        session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
        agent_id = str(body.get("agent_id") or os.environ.get("CODEAGENT_AGENT_ID", "default")).strip() or "default"
        project_id = str(body.get("project_id") or "").strip()
        message = str(body.get("message") or "").strip()
        if not message:
            return JSONResponse({"detail": "message required"}, status_code=400)

        mkey = _memkey(agent_id, session_id)
        try:
            from src.codeagent.core.paths import ensure_agent_scaffold

            ensure_agent_scaffold(agent_id)
        except Exception:
            pass

        if mkey in SESSIONS:
            chat_sess = SESSIONS[mkey]
        else:
            chat_sess = load_or_create_chat_session(session_id, agent_id, project_id or None)
            SESSIONS[mkey] = chat_sess

        fresh_sys = default_system_prompt()
        if not chat_sess.messages:
            chat_sess.messages = [{"role": "system", "content": fresh_sys}]
        else:
            chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

        chat_sess.messages.append({"role": "user", "content": message})
        try:
            from src.transcript_store import append_transcript_entries

            append_transcript_entries(session_id, [chat_sess.messages[-1]], agent_id=agent_id)
        except Exception:
            pass

        max_hist = int(os.environ.get("CODEAGENT_CHAT_USER_ROUNDS", "12"))
        max_rounds = int(os.environ.get("CODEAGENT_MAX_TOOL_ROUNDS", "24"))

        llm = llm_executor_from_resolved(resolve_preset(None))
        reg, exe = tools_for_agent(agent_id)
        set_active_llm_session(session_id)

        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            max_user_rounds=max_hist,
            skills_suffix=None,
        )
        maybe_compact_context_messages(api_msgs, llm)
        apply_episodic_to_messages(
            api_msgs,
            project_root,
            session_id,
            project_id=project_id or None,
            project_scope=False,
        )

        # ── WS 广播回调 ──
        from src.chat_events import reset_chat_event_emitter, set_chat_event_emitter

        main_loop = asyncio.get_event_loop()
        emitter_token = None

        def _emit_progress_from_worker(evt: dict) -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    _broadcast_session_event(agent_id, session_id, evt), main_loop
                )
            except Exception:
                pass

        emitter_token = set_chat_event_emitter(_emit_progress_from_worker)

        n_before = len(api_msgs)
        n_before_ref = [n_before]
        _last_trace_len = [0]
        _stream_placeholder_created = [False]

        def _on_tool_round_persist(tt: list, tu: list) -> None:
            try:
                new_tail = api_msgs[n_before_ref[0]:]
                if new_tail:
                    if (_stream_placeholder_created[0]
                            and chat_sess.messages
                            and chat_sess.messages[-1].get("_streaming")
                            and new_tail[0].get("role") == "assistant"):
                        real_msg = dict(new_tail[0])
                        real_msg.pop("_streaming", None)
                        chat_sess.messages[-1] = real_msg
                        rest = new_tail[1:]
                    else:
                        rest = new_tail
                    if rest:
                        chat_sess.messages.extend(rest)
                    n_before_ref[0] = len(api_msgs)
                _stream_placeholder_created[0] = False
                if tt:
                    new_trace = tt[_last_trace_len[0]:]
                    if new_trace:
                        for _i in range(len(chat_sess.messages) - 1, -1, -1):
                            mm = chat_sess.messages[_i]
                            if isinstance(mm, dict) and mm.get("role") == "assistant":
                                existing = mm.get("tool_trace")
                                if not isinstance(existing, list):
                                    existing = []
                                chat_sess.messages[_i] = {
                                    **mm,
                                    "tool_trace": existing + new_trace,
                                    "tools_used": list(tu) if tu else mm.get("tools_used", []),
                                }
                                break
                    _last_trace_len[0] = len(tt)
                persist_chat_session(chat_sess, agent_id)
            except Exception:
                pass

        def _on_text_delta(full_text: str) -> None:
            try:
                if not _stream_placeholder_created[0]:
                    chat_sess.messages.append({
                        "role": "assistant",
                        "content": "",
                        "_streaming": True,
                    })
                    _stream_placeholder_created[0] = True
                if chat_sess.messages and chat_sess.messages[-1].get("_streaming"):
                    chat_sess.messages[-1]["content"] = full_text
                try:
                    asyncio.run_coroutine_threadsafe(
                        _broadcast_session_event(agent_id, session_id, {
                            "type": "text_delta",
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "text": full_text,
                        }), main_loop
                    )
                except Exception:
                    pass
            except Exception:
                pass

        def _on_reasoning_delta(full_reasoning: str) -> None:
            try:
                if (_stream_placeholder_created[0]
                        and chat_sess.messages
                        and chat_sess.messages[-1].get("_streaming")):
                    chat_sess.messages[-1]["reasoning_content"] = full_reasoning
            except Exception:
                pass

        try:
            reply, _meta, tools_used, tool_trace, _loop_meta = await run_llm_tool_loop(
                llm,
                exe,
                messages=api_msgs,
                registry=reg,
                max_tool_rounds=max_rounds,
                on_round_persist=_on_tool_round_persist,
                on_text_delta=_on_text_delta,
                on_reasoning_delta=_on_reasoning_delta,
            )

            # ── WS: 广播 text_done + reply ──
            trace_out_ws = [
                {"tool": t.get("name", ""), "arguments": t.get("arguments", ""), "result": t.get("result", "")}
                for t in (tool_trace or [])
            ]
            import logging as _lg; _lg.getLogger("ws_debug").info("DEBUG: text_done tool_trace=%d entries, reply=%r", len(trace_out_ws), (reply or '')[:60])
            try:
                asyncio.run_coroutine_threadsafe(
                    _broadcast_session_event(agent_id, session_id, {
                        "type": "text_done",
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "text": reply or "",
                        "tool_trace": trace_out_ws,
                        "tools_used": tools_used or [],
                    }), main_loop
                )
            except Exception:
                pass
            try:
                asyncio.run_coroutine_threadsafe(
                    _broadcast_session_event(agent_id, session_id, {
                        "type": "reply",
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "text": reply or "",
                        "tool_trace": trace_out_ws,
                        "tools_used": tools_used or [],
                    }), main_loop
                )
            except Exception:
                pass

            tail = merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before_ref[0])
            try:
                from src.transcript_store import append_transcript_entries

                if tail:
                    append_transcript_entries(session_id, tail, agent_id=agent_id)
            except Exception:
                pass
            try:
                persist_chat_session(chat_sess, agent_id)
            except Exception:
                logger.exception("persist_chat_session failed")
            try:
                maybe_llm_refresh_session_title(llm, chat_sess)
            except Exception:
                logger.exception("session title refresh failed")
            trace_out = [
                {
                    # WebUI 读 row.tool；run_llm_tool_loop 写 row.name — 两边对齐
                    "tool": t.get("name", ""),
                    "name": t.get("name", ""),
                    "arguments": t.get("arguments", ""),
                    "result": t.get("result", ""),
                }
                for t in tool_trace
            ]
            return JSONResponse(
                {
                    "reply": reply,
                    "session_id": session_id,
                    "tools_used": tools_used,
                    "tool_trace": trace_out,
                }
            )
        except LLMError as e:
            try:
                chat_sess.messages.pop()
            except Exception:
                pass
            return JSONResponse({"detail": str(e)}, status_code=502)
        finally:
            set_active_llm_session(None)
            if emitter_token:
                try:
                    reset_chat_event_emitter(emitter_token)
                except Exception:
                    pass

    async def api_chat_stop(_: Request) -> JSONResponse:
        return JSONResponse({"active": False})

    def _site_icon_path() -> Path:
        return Path(__file__).resolve().parent.parent / "icon.png"

    async def icon_png(_: Request) -> Response:
        p = _site_icon_path()
        if not p.is_file():
            return Response(status_code=404)
        return Response(content=p.read_bytes(), media_type="image/png")

    async def favicon_ico(_: Request) -> Response:
        """Browsers default to /favicon.ico; serve same PNG as /icon.png."""
        p = _site_icon_path()
        if not p.is_file():
            return Response(status_code=404)
        return Response(
            content=p.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def websocket_chat(websocket: WebSocket) -> None:
        await websocket.accept()
        sid = (websocket.query_params.get("session_id") or "").strip()
        aid = (websocket.query_params.get("agent_id") or "").strip() or "default"
        if sid:
            mkey = _memkey(aid, sid)
            WS_BY_SESSION[mkey].add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            if sid:
                WS_BY_SESSION[mkey].discard(websocket)

    middleware: list[Any] = []
    tok = get_webui_token(project_root)
    if tok:
        middleware.append(Middleware(WebUIAuthMiddleware, project_root=project_root))

    # ── Cron：Starlette 1.x 用 lifespan（on_startup 已移除）；且 AsyncIOScheduler 需要已有运行中的 loop ──
    @asynccontextmanager
    async def _lifespan(_app: Starlette):
        try:
            from src.cron_sched_pkg import start_cron_scheduler

            start_cron_scheduler()
        except Exception as exc:
            logger.warning("cron scheduler startup failed: %s", exc)
        yield
        try:
            from src.cron_sched_pkg import shutdown_cron_scheduler

            shutdown_cron_scheduler()
        except Exception:
            pass

    routes = [
        Route("/", homepage),
        Route("/setup", setup_page),
        Route("/health", health),
        Route("/icon.png", icon_png),
        Route("/favicon.ico", favicon_ico),
        Mount("/api/ui", app=build_webui_api_app(project_root)),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/chat/stop", api_chat_stop, methods=["POST"]),
        WebSocketRoute("/ws", websocket_chat),
        WebSocketRoute("/ws/{path:path}", websocket_chat),
    ]

    return Starlette(debug=False, routes=routes, middleware=middleware, lifespan=_lifespan)
