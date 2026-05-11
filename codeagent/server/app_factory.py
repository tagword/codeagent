"""Starlette HTTP / WebSocket application factory."""

from __future__ import annotations

import asyncio
import contextlib
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

    from codeagent.server.webui_api_app import build_webui_api_app
    from seed.integrations.env_config import apply_codeagent_env_from_config

    apply_codeagent_env_from_config()

    try:
        from seed.core.config_plane import ensure_default_config_files
        from seed.core.config_plane import project_root as _pr

        ensure_default_config_files(_pr())
    except Exception:
        logger.exception("bootstrap config failed")

    from codeagent.web.auth_impl import WebUIAuthMiddleware, get_webui_token
    from seed.core.config_plane import project_root as project_root_fn

    from . import _memkey, get_app_html, get_setup_html

    project_root = project_root_fn()

    # ── WebSocket 广播基础设施 ──
    ws_by_session: dict[str, set] = defaultdict(set)

    async def _broadcast_session_event(aid: str, sid: str, payload: dict) -> None:
        mkey = _memkey(aid, sid)
        msg = dict(payload)
        msg.setdefault("session_id", sid)
        msg.setdefault("agent_id", aid)
        for ws in list(ws_by_session.get(mkey, ())):
            with contextlib.suppress(Exception):
                await ws.send_json(msg)

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
        from seed.core.agent_context import set_active_llm_session
        from seed.core.agent_runtime import (
            build_api_projection_messages,
            default_system_prompt,
            maybe_compact_context_messages,
            merge_llm_tail_into_full,
            run_llm_tool_loop,
        )
        from seed.core.llm_exec import LLMError
        from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
        from seed.core.llm_sess import load_or_create_chat_session, merge_fresh_system, persist_chat_session
        from seed.core.mem_bridge import apply_episodic_to_messages
        from seed.core.chat_events import set_chat_cancel_checker, reset_chat_cancel_checker
        from seed.integrations.session_title import maybe_llm_refresh_session_title
        import threading

        from . import SESSIONS, _DEFAULT_AUTO_CONTINUE_NUDGE, _running_sessions, tools_for_agent, ACTIVE_CHAT_CANCELS, PENDING_INJECTIONS

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)

        session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
        agent_id = str(body.get("agent_id") or os.environ.get("CODEAGENT_AGENT_ID", "default")).strip() or "default"
        _run_mkey = _memkey(agent_id, session_id)
        try:
            project_id = str(body.get("project_id") or "").strip()
            if project_id == "__unassigned__":
                project_id = ""
            message = str(body.get("message") or "").strip()
            if not message:
                return JSONResponse({"detail": "message required"}, status_code=400)

            # ── 确保 _cancel_token 在 finnally 之前已初始化 ──
            _cancel_token = None

            # ── 同 session 并发注入 ──
            # 如果 session 已在处理中，将消息入队（下一轮工具循环会自动捡起）
            existing_queue = PENDING_INJECTIONS.get(_run_mkey)
            if existing_queue is not None:
                from datetime import datetime, timezone
                existing_queue.append({
                    "role": "user",
                    "content": message,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                return JSONResponse(
                    {"queued": True, "session_id": session_id, "agent_id": agent_id},
                    status_code=202,
                )
            PENDING_INJECTIONS[_run_mkey] = []
            _running_sessions.add(_run_mkey)

            mkey = _memkey(agent_id, session_id)
            try:
                from codeagent.core.paths import ensure_agent_scaffold

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
                from seed.integrations.transcript_store import append_transcript_entries

                append_transcript_entries(session_id, [chat_sess.messages[-1]], agent_id=agent_id)
            except Exception:
                pass

            max_hist = int(os.environ.get("CODEAGENT_CHAT_USER_ROUNDS", "12"))
            max_rounds = int(os.environ.get("CODEAGENT_MAX_TOOL_ROUNDS", "24"))

            llm = llm_executor_from_resolved(resolve_preset(None))
            reg, exe = tools_for_agent(agent_id)
            set_active_llm_session(session_id)
            from seed.core.agent_context import set_active_project_episodic
            if project_id:
                set_active_project_episodic(True, project_id)
            else:
                set_active_project_episodic(False)

            api_msgs = build_api_projection_messages(
                chat_sess.messages,
                max_user_rounds=max_hist,
                skills_suffix=None,
            )
            await asyncio.to_thread(maybe_compact_context_messages, api_msgs, llm)
            apply_episodic_to_messages(
                api_msgs,
                project_root,
                session_id,
                project_id=project_id or None,
                project_scope=False,
            )

            # ── WS 广播回调 ──
            from seed.core.chat_events import reset_chat_event_emitter, set_chat_event_emitter

            main_loop = asyncio.get_event_loop()
            emitter_token = None

            def _emit_progress_from_worker(evt: dict) -> None:
                with contextlib.suppress(Exception):
                    asyncio.run_coroutine_threadsafe(
                        _broadcast_session_event(agent_id, session_id, evt), main_loop
                    )

            emitter_token = set_chat_event_emitter(_emit_progress_from_worker)

            # ── 停止信号：接线到 ACTIVE_CHAT_CANCELS ──
            try:
                _cancel_event = ACTIVE_CHAT_CANCELS.setdefault(_run_mkey, threading.Event())
                _cancel_token = set_chat_cancel_checker(lambda: _cancel_event.is_set())
            except Exception:
                pass

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
                    loop = asyncio.get_running_loop()
                    loop.run_in_executor(None, persist_chat_session, chat_sess, agent_id)
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
                    with contextlib.suppress(Exception):
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

            def _on_reasoning_delta(full_reasoning: str) -> None:
                try:
                    if (_stream_placeholder_created[0]
                            and chat_sess.messages
                            and chat_sess.messages[-1].get("_streaming")):
                        chat_sess.messages[-1]["reasoning_content"] = full_reasoning
                except Exception:
                    pass

            # ── 运行时消息注入：在每轮工具循环开始前捡起队列中的新消息 ──
            def _drain_pending_injections() -> list:
                msgs = list(PENDING_INJECTIONS.get(_run_mkey, []))
                if msgs:
                    PENDING_INJECTIONS[_run_mkey].clear()
                return msgs

            try:
                # ── auto_continue 配置 ──
                _ac_on = os.environ.get("CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT", "0").strip() in (
                    "1", "true", "yes",
                )
                _max_seg = int(os.environ.get("CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS", "4"))
                _max_seg = max(1, min(_max_seg, 50))

                if _ac_on:
                    from . import _auto_continue_nudge

                    _segment = 0
                    _all_trace: list[dict] = []
                    _all_used: list[str] = []
                    _final_reply = ""
                    _final_meta: dict = {}

                    while _segment < _max_seg:
                        _seg_reply, __, _seg_used, _seg_trace, _seg_meta = await run_llm_tool_loop(
                            llm, exe,
                            messages=api_msgs,
                            registry=reg,
                            max_tool_rounds=max_rounds,
                            on_round_persist=_on_tool_round_persist,
                            on_text_delta=_on_text_delta,
                            on_reasoning_delta=_on_reasoning_delta,
                            on_check_pending_messages=_drain_pending_injections,
                        )
                        _all_trace.extend(_seg_trace or [])
                        for _t in (_seg_used or []):
                            if _t not in _all_used:
                                _all_used.append(_t)
                        if _seg_reply:
                            _final_reply = _seg_reply
                        _final_meta = _seg_meta or {}

                        if _seg_meta.get("stopped_reason") != "max_tool_rounds":
                            break

                        _segment += 1
                        if _segment >= _max_seg:
                            break

                        # Reset per-segment markers for next loop
                        _last_trace_len[0] = 0
                        # Inject nudge as user message to continue
                        # n_before_ref deliberately NOT reset — nudge must be
                        # picked up by _on_tool_round_persist in the next segment
                        _nudge = _auto_continue_nudge(_seg_meta)
                        api_msgs.append({"role": "user", "content": _nudge})

                    reply = _final_reply
                    tools_used = _all_used
                    tool_trace = _all_trace
                    _loop_meta = _final_meta
                else:
                    reply, _meta, tools_used, tool_trace, _loop_meta = await run_llm_tool_loop(
                        llm, exe,
                        messages=api_msgs,
                        registry=reg,
                        max_tool_rounds=max_rounds,
                        on_round_persist=_on_tool_round_persist,
                        on_text_delta=_on_text_delta,
                        on_reasoning_delta=_on_reasoning_delta,
                        on_check_pending_messages=_drain_pending_injections,
                    )

                # ── WS: 广播 text_done + reply（两分支共享） ──
                trace_out_ws = [
                    {"tool": t.get("name", ""), "arguments": t.get("arguments", ""), "result": t.get("result", "")}
                    for t in (tool_trace or [])
                ]
                with contextlib.suppress(Exception):
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
                with contextlib.suppress(Exception):
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

                tail = merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before_ref[0])
                try:
                    from seed.integrations.transcript_store import append_transcript_entries

                    if tail:
                        append_transcript_entries(session_id, tail, agent_id=agent_id)
                except Exception:
                    pass
                try:
                    loop = asyncio.get_running_loop()
                    loop.run_in_executor(None, persist_chat_session, chat_sess, agent_id)
                except Exception:
                    logger.exception("persist_chat_session failed")
                try:
                    # auto-continue 注入的 nudge 消息不应参与标题生成
                    # （否则标题会变成"继续完成未完成事项"而非用户原始意图）
                    # 默认 nudge 以 "请继续完成未完成事项" 开头，
                    # domain playbook 以 "上一段连续在" 开头
                    _nudge_filtered: list[int] = []
                    for _i, _m in enumerate(chat_sess.messages):
                        if (
                            isinstance(_m, dict)
                            and _m.get("role") == "user"
                            and isinstance(_m.get("content"), str)
                            and (
                                _m["content"].startswith(_DEFAULT_AUTO_CONTINUE_NUDGE[:20])
                                or _m["content"].startswith("上一段连续在")
                            )
                        ):
                            _nudge_filtered.append(_i)
                    for _i in reversed(_nudge_filtered):
                        chat_sess.messages.pop(_i)
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
                with contextlib.suppress(Exception):
                    chat_sess.messages.pop()
                return JSONResponse({"detail": str(e)}, status_code=502)
            finally:
                set_active_llm_session(None)
                set_active_project_episodic(False)
                if emitter_token:
                    with contextlib.suppress(Exception):
                        reset_chat_event_emitter(emitter_token)

        finally:
            _running_sessions.discard(_run_mkey)
            PENDING_INJECTIONS.pop(_run_mkey, None)
            ACTIVE_CHAT_CANCELS.pop(_run_mkey, None)
            if _cancel_token is not None:
                with contextlib.suppress(Exception):
                    reset_chat_cancel_checker(_cancel_token)

    async def api_chat_stop(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        from . import ACTIVE_CHAT_CANCELS, _memkey
        session_id = (body.get("session_id") or "web-chat").strip()
        agent_id = (body.get("agent_id") or "").strip() or "default"
        _run_mkey = _memkey(agent_id, session_id)
        cancel_event = ACTIVE_CHAT_CANCELS.get(_run_mkey)
        if cancel_event:
            cancel_event.set()
            return JSONResponse({"cancelled": True})
        return JSONResponse({"cancelled": False, "reason": "not_running"})

    def _resolve_site_icon_path() -> Path | None:
        """``icon.png`` may live next to the ``codeagent`` package, inside ``server/``, or at the repo root."""
        pkg_root = Path(__file__).resolve().parent.parent
        for candidate in (
            pkg_root / "server" / "icon.png",   # shipped with the package
            pkg_root / "icon.png",               # next to the codeagent package
            pkg_root.parent / "icon.png",        # at the repo / project root
        ):
            if candidate.is_file():
                return candidate
        return None

    async def icon_png(_: Request) -> Response:
        p = _resolve_site_icon_path()
        if p is None:
            return Response(status_code=404)
        return Response(content=p.read_bytes(), media_type="image/png")

    async def favicon_ico(_: Request) -> Response:
        """Browsers default to /favicon.ico; serve same PNG as /icon.png."""
        p = _resolve_site_icon_path()
        if p is None:
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
            ws_by_session[mkey].add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            if sid:
                ws_by_session[mkey].discard(websocket)

    middleware: list[Any] = []
    tok = get_webui_token(project_root)
    if tok:
        middleware.append(Middleware(WebUIAuthMiddleware, project_root=project_root))

    # ── Cron：Starlette 1.x 用 lifespan（on_startup 已移除）；且 AsyncIOScheduler 需要已有运行中的 loop ──
    @asynccontextmanager
    async def _lifespan(_app: Starlette):
        try:
            from seed.integrations.cron_sched import start_cron_scheduler

            start_cron_scheduler()
        except Exception as exc:
            logger.warning("cron scheduler startup failed: %s", exc)
        yield
        try:
            from seed.integrations.cron_sched import shutdown_cron_scheduler

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
