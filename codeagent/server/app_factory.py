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

    async def homepage(request: Request) -> HTMLResponse:
        from starlette.responses import RedirectResponse, Response

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
        html, etag = get_app_html()
        if_none = request.headers.get("if-none-match")
        if if_none and if_none == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return HTMLResponse(
            html,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )

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
            get_cached_system_prompt,
            record_chat_turn_diary,
        )
        from seed.core.llm_exec import LLMError
        from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
        from seed.core.llm_sess import load_or_create_chat_session, merge_fresh_system, persist_chat_session
        from seed.core.mem_bridge import finalize_episodic_for_llm
        from seed.core.chat_events import set_chat_cancel_checker, reset_chat_cancel_checker
        from seed.integrations.session_title import maybe_llm_refresh_session_title
        import threading

        from . import SESSIONS, _DEFAULT_AUTO_CONTINUE_NUDGE, _running_add, _running_discard, _running_contains, tools_for_agent, ACTIVE_CHAT_CANCELS, PENDING_INJECTIONS

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

        _run_started = False
        _run_was_cancelled = False
        _run_mkey = ""
        _cancel_token = None

        try:
            agent_id = str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
            body["agent_id"] = agent_id
            body["session_id"] = session_id
            _run_mkey = _memkey(agent_id, session_id)

            llm_id = str(body.get("llm_id") or "").strip()
            vision_llm_id = str(body.get("vision_llm_id") or "").strip()
            image_gen_llm_id = str(body.get("image_gen_llm_id") or "").strip()
            audio_llm_id = str(body.get("audio_llm_id") or "").strip()
            music_llm_id = str(body.get("music_llm_id") or "").strip()
            video_gen_llm_id = str(body.get("video_gen_llm_id") or "").strip()

            from codeagent.server.attachment_api import parse_chat_multimodal_body
            from codeagent.core.attachments import content_text_for_skills
            from codeagent.core.audio_models import preset_supports_audio_id
            from codeagent.core.vision_models import resolve_main_llm

            try:
                user_msg, _att_ids, has_image, _extra = parse_chat_multimodal_body(body)
            except ValueError as e:
                return JSONResponse({"detail": str(e)}, status_code=400)

            has_video = bool(_extra.get("has_video"))
            has_audio = bool(_extra.get("has_audio"))

            message = str(user_msg.get("content") or "").strip()
            from codeagent.core.image_understanding import (
                MCP_VISION_SENTINEL,
                image_attachment_allowed,
                video_attachment_allowed,
            )

            if has_image and not image_attachment_allowed(vision_llm_id):
                return JSONResponse(
                    {
                        "detail": (
                            "发送图片需要 supports_vision 的多模态预设，"
                            "或已配置 MiniMax MCP（understand_image）"
                        )
                    },
                    status_code=400,
                )
            if has_video and not video_attachment_allowed(vision_llm_id):
                return JSONResponse(
                    {"detail": "发送视频需要选择支持多模态的模型 (vision_llm_id)"},
                    status_code=400,
                )
            if has_audio:
                if not audio_llm_id or not preset_supports_audio_id(audio_llm_id):
                    return JSONResponse(
                        {"detail": "需要选择支持音频转写的模型 (audio_llm_id)"},
                        status_code=400,
                    )

            project_id = str(body.get("project_id") or "").strip()
            if project_id == "__unassigned__":
                project_id = ""

            # ── 同 session 并发注入 ──
            # 仅当 session 确实在跑时才入队；否则清掉残留 queue 并正常发起新 run
            if not _running_contains(_run_mkey):
                PENDING_INJECTIONS.pop(_run_mkey, None)
            existing_queue = PENDING_INJECTIONS.get(_run_mkey)
            if existing_queue is not None and _running_contains(_run_mkey):
                from datetime import datetime, timezone
                queued = dict(user_msg)
                queued.setdefault("ts", datetime.now(timezone.utc).isoformat())
                existing_queue.append(queued)
                with contextlib.suppress(Exception):
                    await _broadcast_session_event(agent_id, session_id, {
                        "type": "message_queued",
                    })
                return JSONResponse(
                    {"queued": True, "session_id": session_id, "agent_id": agent_id},
                    status_code=202,
                )
            PENDING_INJECTIONS[_run_mkey] = []
            _running_add(_run_mkey)
            _run_started = True

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

            fresh_sys = get_cached_system_prompt(chat_sess, agent_id=agent_id)
            if not chat_sess.messages:
                chat_sess.messages = [{"role": "system", "content": fresh_sys}]
            else:
                chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

            if isinstance(chat_sess.metadata, dict) and chat_sess.metadata.get("cursor"):
                chat_sess.metadata.pop("cursor", None)

            if body.get("clear_vision_context") and isinstance(chat_sess.metadata, dict):
                chat_sess.metadata.pop("vision_context", None)

            chat_sess.messages.append(user_msg)

            max_hist = pick_int(12, *CHAT_USER_ROUNDS)
            max_rounds = pick_int(24, *MAX_TOOL_ROUNDS)

            llm = resolve_main_llm(llm_id or None)
            _raw_thinking = body.get("enable_thinking")
            if _raw_thinking is None:
                chat_enable_thinking = None
            else:
                chat_enable_thinking = bool(_raw_thinking)
            _raw_effort = str(body.get("reasoning_effort") or "").strip().lower()
            chat_reasoning_effort = _raw_effort if _raw_effort else None
            reg, exe = tools_for_agent(agent_id)
            from seed.core.agent_context import (
                clear_active_project_workspace,
                set_active_agent_id,
                set_active_project_episodic,
                set_active_project_workspace,
                set_active_vision_preset,
                set_active_image_gen_preset,
                set_active_audio_preset,
                set_active_music_preset,
                set_active_video_gen_preset,
            )

            set_active_llm_session(f"{agent_id}::{session_id}")
            set_active_agent_id(agent_id)
            _vision_preset = vision_llm_id or None
            if _vision_preset == MCP_VISION_SENTINEL:
                _vision_preset = None
            set_active_vision_preset(_vision_preset)
            set_active_image_gen_preset(image_gen_llm_id or None)
            set_active_audio_preset(audio_llm_id or None)
            set_active_music_preset(music_llm_id or None)
            set_active_video_gen_preset(video_gen_llm_id or None)
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
                user_text=content_text_for_skills(message),
                workspace_suffix=_work_dir_suffix,
            )
            api_msgs = build_api_projection_messages(
                chat_sess.messages,
                max_user_rounds=max_hist,
                skills_suffix=_skills_suffix,
                **_kwargs,
            )
            _api_pt = None
            if isinstance(chat_sess.metadata, dict):
                _prev_cu = chat_sess.metadata.get("context_usage")
                if isinstance(_prev_cu, dict):
                    _api_pt = int(_prev_cu.get("prompt_tokens") or 0) or None
            compact_result = await asyncio.to_thread(maybe_compact_context_messages, api_msgs, llm, api_prompt_tokens=_api_pt)
            persist_compact_summary(chat_sess.messages, compact_result)
            strip_ephemeral_message_fields(api_msgs)
            if not isinstance(chat_sess.metadata, dict):
                chat_sess.metadata = {}
            await asyncio.to_thread(
                finalize_episodic_for_llm,
                api_msgs,
                chat_sess.metadata,
                agent_id=agent_id,
                session_id=session_id,
                project_id=project_id or None,
                compact_happened=compact_result is not None,
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

            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    _broadcast_session_event(agent_id, session_id, {"type": "run_started"}),
                    main_loop,
                )

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
                    _seg_last_meta: dict = {}
                    from seed.core.usage_accumulator import (
                        begin_usage_accumulation,
                        end_usage_accumulation,
                        reset_usage_accumulation,
                    )

                    while _segment < _max_seg:
                        _seg_token = begin_usage_accumulation()
                        try:
                            _seg_reply, _seg_last_meta, _seg_used, _seg_trace, _seg_meta = await run_llm_tool_loop(
                                llm, exe,
                                messages=api_msgs,
                                registry=reg,
                                max_tool_rounds=max_rounds,
                                on_round_persist=_on_tool_round_persist,
                                on_text_delta=_on_text_delta,
                                on_reasoning_delta=_on_reasoning_delta,
                                on_check_pending_messages=_drain_pending_injections,
                                enable_thinking=chat_enable_thinking,
                                reasoning_effort=chat_reasoning_effort,
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
                            if _seg_meta.get("stopped_reason") == "cancelled":
                                _run_was_cancelled = True
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
                    _last_meta = _seg_last_meta or {}
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
                            enable_thinking=chat_enable_thinking,
                            reasoning_effort=chat_reasoning_effort,
                        )
                        _last_meta = _meta or {}
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
                        _last_meta if isinstance(_last_meta, dict) else None,
                        model_name=_model_name,
                    )
                    # 5. 构造 WS 事件（prompt_tokens = LLM API 精确值或服务端估算）
                    # NOTE: _ctx 来自 build_context_usage_snapshot，prompt_tokens
                    #       优先使用 API usage.prompt_tokens，无 API 时 fallback 估算。
                    from seed.core.agent_runtime import _get_compact_min_tokens as _get_cmt
                    _ctx_pt = int(_ctx.get("prompt_tokens") or 0)
                    _ctx_est = int(_ctx.get("estimated_tokens") or 0)
                    _ws_evt = {
                        "type": "context_usage",
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "prompt_tokens": _ctx_pt,
                        "context_limit": _ctx.get("context_limit", 0),
                        "estimated_tokens": _ctx_est if _ctx_pt <= 0 else 0,
                        "compact_min_tokens": _get_cmt(),
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
                # 持久化当前 context_usage 到 session 元数据，刷新页面后可立即恢复
                try:
                    if isinstance(_ctx, dict) and _ctx:
                        if not isinstance(chat_sess.metadata, dict):
                            chat_sess.metadata = {}
                        _snap = {
                            "prompt_tokens": int(_ctx.get("prompt_tokens") or 0),
                            "context_limit": int(_ctx.get("context_limit") or 0),
                            "message_count": int(_ctx.get("message_count") or 0),
                            "estimated_tokens": int(_ctx.get("estimated_tokens") or 0),
                            "updated_at": chat_sess.updated_at or "",
                        }
                        chat_sess.metadata["context_usage"] = _snap
                        from seed.core.llm_sess import persist_chat_session
                        persist_chat_session(chat_sess, agent_id)
                except Exception:
                    logger.exception("persist context_usage failed")
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
                        "cancelled": bool(_run_was_cancelled),
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
            if _run_started:
                _running_discard(_run_mkey)
                PENDING_INJECTIONS.pop(_run_mkey, None)
                _ev = ACTIVE_CHAT_CANCELS.get(_run_mkey)
                if _ev is not None:
                    _ev.set()
                ACTIVE_CHAT_CANCELS.pop(_run_mkey, None)
                if _cancel_token is not None:
                    with contextlib.suppress(Exception):
                        reset_chat_cancel_checker(_cancel_token)
                with contextlib.suppress(Exception):
                    await _broadcast_session_event(agent_id, session_id, {
                        "type": "run_finished",
                        "cancelled": bool(_run_was_cancelled),
                    })
                    if _run_was_cancelled:
                        await _broadcast_session_event(agent_id, session_id, {
                            "type": "chat_cancelled",
                        })

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
            with contextlib.suppress(Exception):
                await _broadcast_session_event(agent_id, session_id, {
                    "type": "chat_stop_requested",
                })
            return JSONResponse({"cancelled": True})
        return JSONResponse({"cancelled": False, "reason": "not_running"})

    # ---- Per-session model stack override (Session.metadata) ----
    # Stored keys on Session.metadata:
    #   llm_id, vision_llm_id, image_gen_llm_id,
    #   audio_llm_id, music_llm_id, video_gen_llm_id
    _MODEL_STACK_KEYS = (
        "llm_id",
        "vision_llm_id",
        "image_gen_llm_id",
        "audio_llm_id",
        "music_llm_id",
        "video_gen_llm_id",
    )

    def _read_model_stack_from_metadata(metadata):
        if not isinstance(metadata, dict):
            return {}
        out = {}
        for k in _MODEL_STACK_KEYS:
            v = metadata.get(k)
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out

    def _resolve_session_agent_id(body):
        from codeagent.core import env as ca_env
        return (
            str(body.get("agent_id") or ca_env.default_agent_id()).strip() or "default"
        )

    async def api_session_model_stack_get(request: Request) -> JSONResponse:
        """GET /api/ui/session/model-stack?session_id=...&agent_id=...

        Returns the per-session model overrides stored in Session.metadata.
        Empty fields mean "use the global default".
        """
        from seed.core.llm_sess import load_or_create_chat_session
        try:
            body = dict(request.query_params)
        except Exception:
            body = {}
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        overrides = _read_model_stack_from_metadata(chat_sess.metadata)
        return JSONResponse(
            {"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": overrides}
        )

    async def api_session_model_stack_set(request: Request) -> JSONResponse:
        """POST /api/ui/session/model-stack

        Body: {"session_id": "...", "agent_id": "...", "overrides": {<key>: <preset_id|"" >, ...}}

        Empty string or null for a key clears that override (back to global default).
        Unknown keys are ignored. Returns the persisted overrides.
        """
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        overrides_in = body.get("overrides")
        if not isinstance(overrides_in, dict):
            return JSONResponse({"detail": "overrides must be an object"}, status_code=400)
        # Running sessions must be stopped first (consistency with rollback endpoint)
        from . import _running_contains, _memkey
        if _running_contains(_memkey(agent_id, session_id)):
            return JSONResponse(
                {"detail": "session is currently running, stop it first"}, status_code=409
            )
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        for k in _MODEL_STACK_KEYS:
            if k not in overrides_in:
                continue
            v = overrides_in.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                chat_sess.metadata.pop(k, None)
            else:
                chat_sess.metadata[k] = str(v).strip()
        persist_chat_session(chat_sess, agent_id)
        persisted = _read_model_stack_from_metadata(chat_sess.metadata)
        return JSONResponse(
            {"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": persisted}
        )

    async def api_session_model_stack_clear(request: Request) -> JSONResponse:
        """POST /api/ui/session/model-stack/clear — convenience: remove all 6 overrides."""
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return JSONResponse({"detail": "session_id required"}, status_code=400)
        agent_id = _resolve_session_agent_id(body)
        from . import _running_contains, _memkey
        if _running_contains(_memkey(agent_id, session_id)):
            return JSONResponse(
                {"detail": "session is currently running, stop it first"}, status_code=409
            )
        chat_sess = load_or_create_chat_session(session_id, agent_id)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        for k in _MODEL_STACK_KEYS:
            chat_sess.metadata.pop(k, None)
        persist_chat_session(chat_sess, agent_id)
        return JSONResponse({"ok": True, "session_id": session_id, "agent_id": agent_id, "overrides": {}})

    async def api_compact_config_get(request: Request) -> JSONResponse:
        """GET /api/ui/compact-config — return current compact min tokens."""
        from seed.core.agent_runtime import _get_compact_min_tokens, _compact_min_tokens_override
        return JSONResponse({
            "compact_min_tokens": _get_compact_min_tokens(),
            "runtime_override": _compact_min_tokens_override,
        })

    async def api_compact_config_set(request: Request) -> JSONResponse:
        """POST /api/ui/compact-config — set compact min tokens at runtime."""
        from seed.core.agent_runtime import set_compact_min_tokens
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid json"}, status_code=400)
        val = body.get("compact_min_tokens")
        if val is None:
            return JSONResponse({"detail": "compact_min_tokens required"}, status_code=400)
        try:
            val = int(val)
        except (ValueError, TypeError):
            return JSONResponse({"detail": "compact_min_tokens must be integer"}, status_code=400)
        set_compact_min_tokens(val)
        return JSONResponse({"ok": True, "compact_min_tokens": max(0, val)})

    async def api_chat_rollback(request: Request) -> JSONResponse:
        """Roll back session to a given message index — subsequent turns will project from there.

        POST body::

            {"session_id": "...", "agent_id": "...", "message_idx": 42}

        Response::

            {"ok": true, "message_idx": 42, "messages_since": [<messages from idx onwards>]}
        """
        from seed.core.llm_sess import load_or_create_chat_session, persist_chat_session
        from . import _running_contains, _memkey

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
        if _running_contains(_run_mkey):
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
        chat_sess.metadata.pop("vision_context", None)
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

    from codeagent.server.attachment_api import (
        api_attachment_batch,
        api_attachment_get,
        api_attachment_upload,
    )
    from codeagent.server.tts_api import api_tts

    routes = [
        Route("/", homepage),
        Route("/setup", setup_page),
        Route("/health", health),
        Route("/icon.png", icon_png),
        Route("/favicon.ico", favicon_ico),
        # NOTE: routes under /api/ui/session/model-stack must be registered
        # BEFORE the /api/ui Mount, otherwise Starlette will dispatch them
        # to build_webui_api_app first.
        Route(
            "/api/ui/session/model-stack",
            api_session_model_stack_get,
            methods=["GET"],
        ),
        Route(
            "/api/ui/session/model-stack",
            api_session_model_stack_set,
            methods=["POST"],
        ),
        Route(
            "/api/ui/session/model-stack/clear",
            api_session_model_stack_clear,
            methods=["POST"],
        ),
        Route(
            "/api/ui/compact-config",
            api_compact_config_get,
            methods=["GET"],
        ),
        Route(
            "/api/ui/compact-config",
            api_compact_config_set,
            methods=["POST"],
        ),
        Mount("/api/ui", app=build_webui_api_app(project_root)),
        Route("/api/attachments", api_attachment_upload, methods=["POST"]),
        Route("/api/attachments/batch", api_attachment_batch, methods=["POST"]),
        Route("/api/attachments/{attachment_id}", api_attachment_get, methods=["GET"]),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/chat/stop", api_chat_stop, methods=["POST"]),
        Route("/api/chat/rollback", api_chat_rollback, methods=["POST"]),
        Route("/api/tts", api_tts, methods=["POST"]),
        WebSocketRoute("/ws", websocket_chat),
        WebSocketRoute("/ws/{path:path}", websocket_chat),
    ]

    return Starlette(debug=False, routes=routes, middleware=middleware, lifespan=_lifespan)
