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

    from codeagent.core import env as ca_env

    if not logging_mod.getLogger().handlers:
        logging_mod.basicConfig(
            level=ca_env.pick_default("INFO", ca_env.LOG_LEVEL).upper(),
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
    from codeagent.core.bootstrap import bootstrap_codeagent_runtime

    bootstrap_codeagent_runtime()

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
            build_context_usage_snapshot,
            estimate_context_usage,
            maybe_compact_context_messages,
            merge_llm_tail_into_full,
            persist_compact_summary,
            run_llm_tool_loop,
            strip_ephemeral_message_fields,
        )
        from codeagent.runtime.prompt_enrichment import (
            build_skills_suffix,
            fresh_system_prompt,
            record_chat_turn_diary,
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
        from codeagent.core import env as ca_env
        from seed.core.env_access import (
            CHAT_AUTO_CONTINUE_MAX_SEGMENTS,
            CHAT_AUTO_CONTINUE_ON_LIMIT,
            CHAT_USER_ROUNDS,
            MAX_TOOL_ROUNDS,
            env_truthy,
            pick_int,
        )

        agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
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

            fresh_sys = fresh_system_prompt(agent_id=agent_id)
            if not chat_sess.messages:
                chat_sess.messages = [{"role": "system", "content": fresh_sys}]
            else:
                chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

            if isinstance(chat_sess.metadata, dict) and chat_sess.metadata.get("cursor"):
                chat_sess.metadata.pop("cursor", None)

            chat_sess.messages.append({"role": "user", "content": message})
            try:
                from seed.integrations.transcript_store import append_transcript_entries

                append_transcript_entries(session_id, [chat_sess.messages[-1]], agent_id=agent_id)
            except Exception:
                pass

            max_hist = pick_int(12, *CHAT_USER_ROUNDS)
            max_rounds = pick_int(24, *MAX_TOOL_ROUNDS)

            llm = llm_executor_from_resolved(resolve_preset(None))
            reg, exe = tools_for_agent(agent_id)
            set_active_llm_session(session_id)
            from seed.core.agent_context import (
                clear_active_project_workspace,
                set_active_project_episodic,
                set_active_project_workspace,
            )
            from seed.core.proj_reg import get_project, resolve_project_path
            if project_id:
                set_active_project_episodic(True, project_id)
            else:
                set_active_project_episodic(False)
                set_active_project_workspace(None)

            # backward-compat: seed 1.0.0 没有 cursor 参数
            import inspect as _inspect
            _sig = _inspect.signature(build_api_projection_messages)
            _cursor_supported = "cursor" in _sig.parameters
            _kwargs = {}
            if _cursor_supported:
                _kwargs["cursor"] = (
                    chat_sess.metadata.get("cursor")
                    if isinstance(chat_sess.metadata, dict) else None
                )
            # ── 工作目录注入 ──
            _work_dir_suffix = ""
            if project_id:
                _wd = resolve_project_path(agent_id, project_id)
                if _wd:
                    set_active_project_workspace(_wd)
                else:
                    set_active_project_workspace(None)
                _proj = get_project(agent_id, project_id)
                if _proj and _wd:
                    _work_dir_suffix = (
                        "\n\n"
                        "## Workspace\n\n"
                        f"当前工作目录：`{_wd}`\n\n"
                        "执行 shell 命令时，工作目录默认为此路径。"
                        "除非有充分理由，否则请在此目录下操作，不要 cd 到其他目录。\n"
                    )

            _skills_suffix = build_skills_suffix(
                agent_id,
                user_text=message,
                workspace_suffix=_work_dir_suffix,
            )
            api_msgs = build_api_projection_messages(
                chat_sess.messages,
                max_user_rounds=max_hist,
                skills_suffix=_skills_suffix,
                **_kwargs,
            )
            compact_result = await asyncio.to_thread(maybe_compact_context_messages, api_msgs, llm)
            persist_compact_summary(chat_sess.messages, compact_result)
            strip_ephemeral_message_fields(api_msgs)
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
                    new_tail = [
                        message
                        for message in api_msgs[n_before_ref[0]:]
                        if not (
                            isinstance(message, dict)
                            and (
                                message.get("_auto_continue_nudge")
                                or (
                                    message.get("role") == "user"
                                    and isinstance(message.get("content"), str)
                                    and (
                                        message["content"].startswith(_DEFAULT_AUTO_CONTINUE_NUDGE[:20])
                                        or message["content"].startswith("上一段连续在")
                                    )
                                )
                            )
                        )
                    ]
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
                            persisted_rest = []
                            for message in rest:
                                if not isinstance(message, dict):
                                    persisted_rest.append(message)
                                    continue
                                copied = dict(message)
                                strip_ephemeral_message_fields([copied])
                                persisted_rest.append(copied)
                            chat_sess.messages.extend(persisted_rest)
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
                _ac_on = env_truthy(*CHAT_AUTO_CONTINUE_ON_LIMIT, default="0")
                _max_seg = pick_int(4, *CHAT_AUTO_CONTINUE_MAX_SEGMENTS)
                _max_seg = max(1, min(_max_seg, 50))

                if _ac_on:
                    from . import _auto_continue_nudge

                    _segment = 0
                    _all_trace: list[dict] = []
                    _all_used: list[str] = []
                    _final_reply = ""
                    _final_meta: dict = {}
                    _acc_usage: dict = {}
                    from seed.core.usage_accumulator import (
                        begin_usage_accumulation,
                        end_usage_accumulation,
                        reset_usage_accumulation,
                    )

                    while _segment < _max_seg:
                        _seg_token = begin_usage_accumulation()
                        try:
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
                        except Exception:
                            reset_usage_accumulation(_seg_token)
                            raise
                        else:
                            _seg_usage = end_usage_accumulation(_seg_token)

                        _all_trace.extend(_seg_trace or [])
                        for _t in (_seg_used or []):
                            if _t not in _all_used:
                                _all_used.append(_t)
                        if _seg_reply:
                            _final_reply = _seg_reply
                        _final_meta = _seg_meta or {}
                        # 累加每个 segment 的 usage
                        if _seg_usage:
                            for _k in ("prompt_tokens", "completion_tokens", "total_tokens",
                                       "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                                _v = _seg_usage.get(_k, 0)
                                if isinstance(_v, (int, float)):
                                    _acc_usage[_k] = _acc_usage.get(_k, 0) + int(_v)

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
                        api_msgs.append(
                            {
                                "role": "user",
                                "content": _nudge,
                                "_auto_continue_nudge": True,
                            }
                        )

                    reply = _final_reply
                    tools_used = _all_used
                    tool_trace = _all_trace
                    _loop_meta = _final_meta
                    if _acc_usage:
                        _loop_meta["usage_summary"] = _acc_usage
                else:
                    from seed.core.usage_accumulator import (
                        begin_usage_accumulation,
                        end_usage_accumulation,
                        reset_usage_accumulation,
                    )

                    _norm_token = begin_usage_accumulation()
                    try:
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
                    except Exception:
                        reset_usage_accumulation(_norm_token)
                        raise
                    else:
                        _norm_usage = end_usage_accumulation(_norm_token)
                        if _norm_usage:
                            _loop_meta["usage_summary"] = _norm_usage

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
                    record_chat_turn_diary(
                        agent_id,
                        user_text=message,
                        reply=reply or "",
                        tools_used=tools_used,
                        project_id=project_id or None,
                    )
                except Exception:
                    pass
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
                # ── Token 用量精确计算（基于 API 返回的 usage） ──
                _acc = {}
                _cost_info = {}
                _total_cost_info = {}
                _api_usage = {}
                _ctx: dict[str, Any] = {}
                _model_name = getattr(llm, "model", "")
                try:
                    from codeagent.core.usage_billing import merge_accumulated_usage

                    _api_usage = dict(_loop_meta.get("usage_summary", {}) or {})
                    _model_name = getattr(llm, "model", "") or _model_name
                    _prev = chat_sess.metadata.get("accumulated_usage", {}) or {}
                    _acc, _cost_info, _total_cost_info = merge_accumulated_usage(
                        _prev, _model_name, _api_usage
                    )
                    chat_sess.metadata["accumulated_usage"] = _acc

                    _proj_ctx = build_api_projection_messages(
                        chat_sess.messages,
                        max_user_rounds=max_hist,
                        skills_suffix=_skills_suffix,
                        **_kwargs,
                    )
                    _ctx = build_context_usage_snapshot(
                        _proj_ctx,
                        _loop_meta if isinstance(_loop_meta, dict) else None,
                    )

                    # 5. 构造 WS 事件（body_bytes = 下次请求上下文体积，非计费 token）
                    _ws_evt = {
                        "type": "context_usage",
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "body_bytes": _ctx.get("body_bytes", 0),
                        "compact_min_bytes": _ctx.get("compact_min_bytes", 0),
                        "message_count": _ctx.get("message_count", 0),
                        "token_usage": _api_usage,
                        "accumulated_usage": _acc,
                        "cost": _cost_info,
                        "accumulated_cost": _total_cost_info,
                        "model": _model_name,
                    }
                    asyncio.run_coroutine_threadsafe(
                        _broadcast_session_event(agent_id, session_id, _ws_evt), main_loop
                    )
                except Exception:
                    _api_usage = {}
                    _cost_info = {}
                if not _ctx:
                    with contextlib.suppress(Exception):
                        _ctx = estimate_context_usage(
                            build_api_projection_messages(
                                chat_sess.messages,
                                max_user_rounds=max_hist,
                                skills_suffix=_skills_suffix,
                                **_kwargs,
                            )
                        )
                return JSONResponse(
                    {
                        "reply": reply,
                        "session_id": session_id,
                        "tools_used": tools_used,
                        "tool_trace": trace_out,
                        "token_usage": _api_usage,
                        "context": _ctx,
                        "cost": _cost_info,
                        "accumulated_cost": _total_cost_info,
                        "accumulated_usage": _acc,
                        "model": _model_name,
                    }
                )
            except LLMError as e:
                with contextlib.suppress(Exception):
                    chat_sess.messages.pop()
                return JSONResponse({"detail": str(e)}, status_code=502)
            finally:
                set_active_llm_session(None)
                set_active_project_episodic(False)
                clear_active_project_workspace()
                if emitter_token:
                    with contextlib.suppress(Exception):
                        reset_chat_event_emitter(emitter_token)

        except asyncio.CancelledError:
            _ev = ACTIVE_CHAT_CANCELS.get(_run_mkey)
            if _ev is not None:
                _ev.set()
            raise
        finally:
            _running_sessions.discard(_run_mkey)
            PENDING_INJECTIONS.pop(_run_mkey, None)
            _ev = ACTIVE_CHAT_CANCELS.get(_run_mkey)
            if _ev is not None:
                _ev.set()
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

    async def api_chat_rollback(request: Request) -> JSONResponse:
        """Roll back session to a given message index — subsequent turns will project from there.

        POST body::

            {"session_id": "...", "agent_id": "...", "message_idx": 42}

        Response::

            {"ok": true, "message_idx": 42, "messages_since": [<messages from idx onwards>]}
        """
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        from . import _running_sessions, _memkey

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)

        session_id = str(body.get("session_id") or "web-chat").strip() or "web-chat"
        from codeagent.core import env as ca_env
        from seed.core.env_access import (
            CHAT_AUTO_CONTINUE_MAX_SEGMENTS,
            CHAT_AUTO_CONTINUE_ON_LIMIT,
            CHAT_USER_ROUNDS,
            MAX_TOOL_ROUNDS,
            env_truthy,
            pick_int,
        )

        agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
        # 0 = system message, so minimal sensible value is 1
        message_idx = int(body.get("message_idx", 1))

        _run_mkey = _memkey(agent_id, session_id)
        if _run_mkey in _running_sessions:
            return JSONResponse({"detail": "session is currently running, stop it first"}, status_code=409)

        chat_sess = load_or_create_chat_session(session_id, agent_id)

        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}

        # Clamp to valid range
        max_idx = len(chat_sess.messages) - 1
        if message_idx < 0:
            message_idx = 0
        if message_idx > max_idx:
            return JSONResponse(
                {"detail": f"message_idx {message_idx} out of range (max {max_idx})"},
                status_code=422,
            )

        chat_sess.metadata["cursor"] = {
            "mode": "head",
            "from_idx": message_idx,
        }
        persist_chat_session(chat_sess, agent_id)

        # Broadcast rollback event via websocket
        try:
            await _broadcast_session_event(agent_id, session_id, {
                "type": "rollback",
                "message_idx": message_idx,
            })
        except Exception:
            pass

        # Return messages from rollback point for UI refresh
        messages_since = chat_sess.messages[message_idx:]
        return JSONResponse({
            "ok": True,
            "message_idx": message_idx,
            "messages_since": messages_since,
        })

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
            from seed.core._session_cache import cancel_all_active_chats

            n = cancel_all_active_chats()
            if n:
                logger.info("shutdown: signalled %s active chat(s) to stop", n)
        except Exception:
            pass
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
        Route("/api/chat/rollback", api_chat_rollback, methods=["POST"]),
        WebSocketRoute("/ws", websocket_chat),
        WebSocketRoute("/ws/{path:path}", websocket_chat),
    ]

    return Starlette(debug=False, routes=routes, middleware=middleware, lifespan=_lifespan)
