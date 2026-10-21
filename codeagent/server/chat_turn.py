"""run_chat_turn — 单轮 chat 执行核心（WebUI api_chat 与 cron 共用）。

WebUI 的 ``api_chat`` 薄壳只负责 HTTP 解析/多模态校验/``/skill`` 命令，
核心逻辑全部在本模块；cron 通过注入的 handler 直接调用本函数，获得与
WebUI 一致的 running 状态、消息注入（插话）、可停止、WS 广播、上下文
压缩与持久化行为。

调用方职责：
- 构造完整的 ``user_msg``（role/content/ts）
- 决定 ``if_busy``：WebUI 用 ``"queue"``（忙则入队插话），cron 用 ``"skip"``
- 处理 LLMError（本函数已回滚 user 消息后重新抛出）
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

from codeagent.server import (  # noqa: E402
    _DEFAULT_AUTO_CONTINUE_NUDGE,
    ACTIVE_CHAT_CANCELS,
    PENDING_INJECTIONS,
    SESSIONS,
    _auto_continue_nudge,
    _memkey,
    _running_add,
    _running_contains,
    _running_discard,
    tools_for_agent,
)


async def run_chat_turn(
    *,
    agent_id: str,
    session_id: str,
    user_msg: dict,
    llm_id: str = "",
    vision_llm_id: str = "",
    image_gen_llm_id: str = "",
    audio_llm_id: str = "",
    music_llm_id: str = "",
    video_gen_llm_id: str = "",
    project_id: str = "",
    max_tool_rounds: int | None = None,
    enable_thinking: bool | None = None,
    reasoning_effort: str = "",
    clear_vision_context: bool = False,
    channel: str = "",
    source: str = "",
    extra_metadata: dict | None = None,
    refresh_title: bool = True,
    log_diary: bool = True,
    emit_ws: bool = True,
    broadcast_fn: Callable[..., Awaitable[None]] | None = None,
    if_busy: str = "queue",
    forced_skill_suffix: str = "",
    with_evidence: bool = False,
) -> dict:
    """执行一轮 chat turn（追加 user 消息 → LLM 工具循环 → 合并/持久化）。

    返回 dict（reply/session_id/tools_used/tool_trace/token_usage/context/
    cost/accumulated_cost/accumulated_usage/model/cancelled），或
    ``{"queued": True}``（if_busy=queue 且 session 忙碌）、
    ``{"skipped": True}``（if_busy=skip 且 session 忙碌）。
    LLMError 会回滚追加的 user 消息后重新抛出，由调用方决定错误响应。
    """
    from codeagent.core.attachments import content_text_for_skills
    from codeagent.core.image_understanding import MCP_VISION_SENTINEL
    from codeagent.core.vision_models import resolve_main_llm
    from codeagent.runtime.prompt_enrichment import (
        build_skills_suffix,
        get_cached_system_prompt,
        record_chat_turn_diary,
    )
    from seed.core.agent_context import set_active_llm_session
    from seed.core.agent_runtime import (
        apply_context_usage_metadata,
        build_api_projection_messages,
        build_context_usage_from_run,
        maybe_compact_context_messages,
        merge_llm_tail_into_full,
        persist_compact_summary,
        resolve_compact_trigger_tokens,
        run_llm_tool_loop,
        strip_ephemeral_message_fields,
    )
    from seed.core.chat_events import (
        reset_chat_cancel_checker,
        reset_chat_event_emitter,
        set_chat_cancel_checker,
        set_chat_event_emitter,
    )
    from seed.core.env_access import (
        CHAT_AUTO_CONTINUE_MAX_SEGMENTS,
        CHAT_AUTO_CONTINUE_ON_LIMIT,
        MAX_TOOL_ROUNDS,
        env_truthy,
        pick_int,
    )
    from seed.core.llm_exec import LLMError
    from seed.core.llm_sess import (
        load_or_create_chat_session,
        merge_fresh_system,
        persist_chat_session,
    )
    from seed.core.mem_bridge import finalize_episodic_for_llm
    from seed.integrations.session_title import maybe_llm_refresh_session_title

    message = str(user_msg.get("content") or "").strip()
    _run_started = False
    _run_was_cancelled = False
    _run_mkey = _memkey(agent_id, session_id)
    _cancel_token = None
    emitter_token = None

    try:
        # ── 同 session 并发注入 ──
        # 仅当 session 确实在跑时才入队；否则清掉残留 queue 并正常发起新 run
        if not _running_contains(_run_mkey):
            PENDING_INJECTIONS.pop(_run_mkey, None)
        existing_queue = PENDING_INJECTIONS.get(_run_mkey)
        if existing_queue is not None and _running_contains(_run_mkey):
            if if_busy == "skip":
                # cron 语义：忙则跳过本次触发（不堆积，等下次 cron）
                return {
                    "skipped": True,
                    "session_id": session_id,
                    "agent_id": agent_id,
                }
            queued = dict(user_msg)
            queued.setdefault("ts", datetime.now(timezone.utc).isoformat())
            existing_queue.append(queued)
            if emit_ws and broadcast_fn is not None:
                with contextlib.suppress(Exception):
                    await broadcast_fn(agent_id, session_id, {"type": "message_queued"})
            return {"queued": True, "session_id": session_id, "agent_id": agent_id}
        PENDING_INJECTIONS[_run_mkey] = []
        _running_add(_run_mkey)
        _run_started = True
        # 停止信号必须在 _running_add 后立即注册，消除
        # _running_sessions 与 ACTIVE_CHAT_CANCELS 之间的时间窗口
        try:
            _cancel_event = ACTIVE_CHAT_CANCELS.setdefault(_run_mkey, threading.Event())
            _cancel_token = set_chat_cancel_checker(lambda: _cancel_event.is_set())
        except Exception:
            pass

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

        if clear_vision_context and isinstance(chat_sess.metadata, dict):
            chat_sess.metadata.pop("vision_context", None)

        chat_sess.messages.append(user_msg)

        # ── 频道标记（cron: channel=Cron / source=cron:jid；WebUI 不写） ──
        if (channel or source or extra_metadata) and isinstance(chat_sess.metadata, dict):
            if channel:
                chat_sess.metadata["channel"] = channel
            if source:
                chat_sess.metadata["source"] = source
            if isinstance(extra_metadata, dict):
                chat_sess.metadata.update(extra_metadata)

        if max_tool_rounds is not None:
            try:
                max_rounds = max(1, int(max_tool_rounds))
            except (TypeError, ValueError):
                max_rounds = pick_int(24, *MAX_TOOL_ROUNDS)
        else:
            max_rounds = pick_int(24, *MAX_TOOL_ROUNDS)

        llm = resolve_main_llm(llm_id or None)
        chat_enable_thinking = None if enable_thinking is None else bool(enable_thinking)
        chat_reasoning_effort = reasoning_effort.strip().lower() if (reasoning_effort or "").strip() else None
        reg, exe = tools_for_agent(agent_id)
        from seed.core.agent_context import (
            clear_active_project_workspace,
            set_active_agent_id,
            set_active_audio_preset,
            set_active_image_gen_preset,
            set_active_music_preset,
            set_active_project_episodic,
            set_active_project_workspace,
            set_active_video_gen_preset,
            set_active_vision_preset,
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
                if isinstance(chat_sess.metadata, dict)
                else None
            )
        # ── 工作目录注入 ──
        _work_dir_suffix = ""
        _wd = None
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
            project_path=_wd,
        )
        if forced_skill_suffix:
            _skills_suffix = (_skills_suffix or "").rstrip() + forced_skill_suffix
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            skills_suffix=_skills_suffix,
            **_kwargs,
        )
        _api_pt = None
        _prev_cu = None
        if isinstance(chat_sess.metadata, dict):
            _prev_cu = chat_sess.metadata.get("context_usage")
            if isinstance(_prev_cu, dict):
                _api_pt = resolve_compact_trigger_tokens(persisted=_prev_cu) or None
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        # episodic 在 compact 前注入，使 compact 判断与 LLM 实际输入一致
        await asyncio.to_thread(
            finalize_episodic_for_llm,
            api_msgs,
            chat_sess.metadata,
            agent_id=agent_id,
            session_id=session_id,
            project_id=project_id or None,
            compact_happened=False,
        )
        compact_result = await asyncio.to_thread(
            maybe_compact_context_messages,
            api_msgs,
            llm,
            api_prompt_tokens=_api_pt,
            persisted_context_usage=_prev_cu if isinstance(_prev_cu, dict) else None,
        )
        persist_compact_summary(chat_sess.messages, compact_result)
        strip_ephemeral_message_fields(api_msgs)

        from codeagent.runtime.compact_state import inject_state_into_system

        if compact_result:
            await asyncio.to_thread(
                inject_state_into_system,
                api_msgs,
                agent_id,
            )
            await asyncio.to_thread(
                finalize_episodic_for_llm,
                api_msgs,
                chat_sess.metadata,
                agent_id=agent_id,
                session_id=session_id,
                project_id=project_id or None,
                compact_happened=True,
            )

        def _on_mid_compact(compact_result: dict | None) -> None:
            if not compact_result:
                return
            persist_compact_summary(chat_sess.messages, compact_result)
            inject_state_into_system(api_msgs, agent_id)

        # ── WS 广播回调 ──
        main_loop = asyncio.get_event_loop()

        def _emit_progress_from_worker(evt: dict) -> None:
            if not (emit_ws and broadcast_fn is not None):
                return
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    broadcast_fn(agent_id, session_id, evt), main_loop
                )

        if emit_ws and broadcast_fn is not None:
            emitter_token = set_chat_event_emitter(_emit_progress_from_worker)

        if emit_ws and broadcast_fn is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    broadcast_fn(agent_id, session_id, {"type": "run_started"}),
                    main_loop,
                )

        n_before = len(api_msgs)
        n_before_ref = [n_before]
        _last_trace_len = [0]
        _stream_placeholder_created = [False]

        def _on_tool_round_persist(tt: list, tu: list) -> None:
            try:
                # mid-loop compact 会原地重建 api_msgs（长度骤减），使 n_before_ref
                # 索引失效、后续增量 tail 恒为空 → 本轮输出丢失。退化为「最后一条
                # user 之后」为合并起点（与 merge_llm_tail_into_full 的容错一致）。
                _start = n_before_ref[0]
                if len(api_msgs) < _start:
                    _last_ui = -1
                    for _i2, _m2 in enumerate(api_msgs):
                        if isinstance(_m2, dict) and _m2.get("role") == "user":
                            _last_ui = _i2
                    _start = _last_ui + 1
                    n_before_ref[0] = _start
                new_tail = [
                    message
                    for message in api_msgs[_start:]
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
                    rest = new_tail
                    if rest:
                        # ── 移除上一个流式占位符（_streaming=True），防止重复落盘 ──
                        if _stream_placeholder_created[0]:
                            for _pi in range(len(chat_sess.messages) - 1, -1, -1):
                                _pm = chat_sess.messages[_pi]
                                if isinstance(_pm, dict) and _pm.get("_streaming"):
                                    del chat_sess.messages[_pi]
                                    break
                            _stream_placeholder_created[0] = False

                        persisted_rest = []
                        for message in rest:
                            if not isinstance(message, dict):
                                persisted_rest.append(message)
                                continue
                            copied = dict(message)
                            strip_ephemeral_message_fields([copied])
                            if "ts" not in copied or not copied.get("ts"):
                                copied["ts"] = datetime.now(timezone.utc).isoformat()
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
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    _stream_placeholder_created[0] = True
                if chat_sess.messages and chat_sess.messages[-1].get("_streaming"):
                    chat_sess.messages[-1]["content"] = full_text
                if emit_ws and broadcast_fn is not None:
                    with contextlib.suppress(Exception):
                        asyncio.run_coroutine_threadsafe(
                            broadcast_fn(agent_id, session_id, {
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
                _segment = 0
                _all_trace: list[dict] = []
                _all_used: list[str] = []
                _final_reply = ""
                _final_meta: dict = {}
                _acc_usage: dict = {}
                _seg_last_meta: dict = {}
                _peak_across_segments = 0
                _pending_nudge = ""
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
                            on_compact=_on_mid_compact,
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
                    _peak_across_segments = max(
                        _peak_across_segments,
                        int((_seg_meta or {}).get("peak_prompt_tokens") or 0),
                    )
                    # 累加每个 segment 的 usage
                    if _seg_usage:
                        for _k in ("prompt_tokens", "completion_tokens", "total_tokens",
                                   "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                            _v = _seg_usage.get(_k, 0)
                            if isinstance(_v, (int, float)):
                                _acc_usage[_k] = _acc_usage.get(_k, 0) + int(_v)

                    _stop_reason = _seg_meta.get("stopped_reason")
                    # ── 续跑判定（v1.2.2 修复静默停止）──
                    # 数据依据：5293 条用户消息中「继续」74 次（最高频）。
                    # 两条续跑路径：
                    #   A. max_tool_rounds 用尽 → 续跑（v1.1.36 原有行为）
                    #   B. Agent 自认为完成但仍有 pending todo → 也续跑
                    #
                    # v1.2.0 缺陷：pending 检查被塞进
                    # `if _stop_reason != "max_tool_rounds":` 分支 → 路径 A 时
                    # 整块跳过、_pending_continue 恒 False → 撞满轮次直接 break
                    # 静默停止。等于用新能力换掉旧能力，而非叠加。
                    # 修复：把 pending 检查提到 max_tool_rounds 判断之外。
                    _pending_continue = False
                    _pending_nudge = ""
                    if _stop_reason == "cancelled":
                        _run_was_cancelled = True
                        break

                    # 轮数用尽只说明"话没说完"，不代表"活干完了" → 应续跑。
                    # 不依赖 pending 查询：查询失败也不能静默停止。
                    _limit_hit = _stop_reason == "max_tool_rounds"
                    if _limit_hit:
                        _pending_continue = True
                        _pending_nudge = (
                            f"上一段用完了 {max_rounds} 轮工具调用预算，任务尚未完成。"
                            "请继续未完成的工作，不要停下来征询。"
                        )
                        logger.info(
                            "auto-continue: tool-round limit hit, continuing (segment %d/%d)",
                            _segment + 1, _max_seg,
                        )

                    # 检查是否真有未完成事项（路径 B）
                    # 两个信号源：① 项目 todo ② task.md 未勾选项
                    # （后者覆盖"Agent 做完一个 Wave 就问要不要继续"）
                    if not _limit_hit and (_segment + 1) < _max_seg:
                        try:
                            from codeagent.server.auto_continue import (
                                build_continue_nudge,
                                get_pending_all,
                            )

                            _pend = get_pending_all(agent_id, project_id or "", session_id)
                            if _pend.has_pending and (_segment + 1) < _max_seg:
                                _pending_continue = True
                                _pending_nudge = build_continue_nudge(_pend)
                                logger.info(
                                    "auto-continue: %d pending items, continuing (segment %d/%d)",
                                    _pend.count, _segment + 1, _max_seg,
                                )
                        except Exception:
                            logger.debug("pending-todo check failed", exc_info=True)

                    if not _pending_continue:
                        break

                    _segment += 1
                    if _segment >= _max_seg:
                        break

                    # Reset per-segment markers for next loop
                    _last_trace_len[0] = 0
                    _seg_peak = int((_seg_meta or {}).get("peak_prompt_tokens") or 0)
                    _seg_compact = await asyncio.to_thread(
                        maybe_compact_context_messages,
                        api_msgs,
                        llm,
                        api_prompt_tokens=_seg_peak or None,
                        loop_meta=_seg_meta if isinstance(_seg_meta, dict) else None,
                    )
                    persist_compact_summary(chat_sess.messages, _seg_compact)
                    if _seg_compact:
                        strip_ephemeral_message_fields(api_msgs)
                        await asyncio.to_thread(
                            inject_state_into_system,
                            api_msgs,
                            agent_id,
                        )
                        await asyncio.to_thread(
                            finalize_episodic_for_llm,
                            api_msgs,
                            chat_sess.metadata,
                            agent_id=agent_id,
                            session_id=session_id,
                            project_id=project_id or None,
                            compact_happened=True,
                        )
                    # Inject nudge as user message to continue
                    # n_before_ref deliberately NOT reset — nudge must be
                    # picked up by _on_tool_round_persist in the next segment
                    # 优先用"未完成事项"提示（更有指向性），否则用通用 nudge
                    _nudge = _pending_nudge or _auto_continue_nudge(_seg_meta)
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
                if _peak_across_segments > 0:
                    _loop_meta["peak_prompt_tokens"] = max(
                        int(_loop_meta.get("peak_prompt_tokens") or 0),
                        _peak_across_segments,
                    )
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
                        on_compact=_on_mid_compact,
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
            if emit_ws and broadcast_fn is not None:
                with contextlib.suppress(Exception):
                    asyncio.run_coroutine_threadsafe(
                        broadcast_fn(agent_id, session_id, {
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
                        broadcast_fn(agent_id, session_id, {
                            "type": "reply",
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "text": reply or "",
                            "tool_trace": trace_out_ws,
                            "tools_used": tools_used or [],
                        }), main_loop
                    )

            # ── 移除流式占位符，防止纯文本回复路径（无 tool rounds）重复落盘 ──
            if _stream_placeholder_created[0]:
                for _pi in range(len(chat_sess.messages) - 1, -1, -1):
                    _pm = chat_sess.messages[_pi]
                    if isinstance(_pm, dict) and _pm.get("_streaming"):
                        del chat_sess.messages[_pi]
                        break
                _stream_placeholder_created[0] = False

            merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before_ref[0])
            _model_name = getattr(llm, "model", "")
            _ctx: dict[str, Any] = {}
            # 先写入 context_usage（含 peak），避免后续异步 persist 落盘旧值
            try:
                _proj_ctx = build_api_projection_messages(
                    chat_sess.messages,
                    skills_suffix=_skills_suffix,
                    **_kwargs,
                )
                await asyncio.to_thread(
                    finalize_episodic_for_llm,
                    _proj_ctx,
                    chat_sess.metadata,
                    agent_id=agent_id,
                    session_id=session_id,
                    project_id=project_id or None,
                    compact_happened=False,
                )
                _ctx = build_context_usage_from_run(
                    _proj_ctx,
                    loop_meta=_loop_meta,
                    last_meta=_last_meta if isinstance(_last_meta, dict) else None,
                    model_name=_model_name,
                )
            except Exception:
                logger.exception("build context_usage snapshot failed")
                with contextlib.suppress(Exception):
                    _ctx = build_context_usage_from_run(
                        api_msgs,
                        loop_meta=_loop_meta,
                        last_meta=_last_meta if isinstance(_last_meta, dict) else None,
                        model_name=_model_name,
                    )
            try:
                if isinstance(_ctx, dict) and _ctx:
                    if not isinstance(chat_sess.metadata, dict):
                        chat_sess.metadata = {}
                    apply_context_usage_metadata(
                        chat_sess.metadata,
                        _ctx,
                        updated_at=chat_sess.updated_at or "",
                    )
                    persist_chat_session(chat_sess, agent_id)
            except Exception:
                logger.exception("persist context_usage failed")
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, persist_chat_session, chat_sess, agent_id)
            except Exception:
                logger.exception("persist_chat_session failed")
            if log_diary:
                try:
                    record_chat_turn_diary(
                        agent_id,
                        user_text=message,
                        reply=reply or "",
                        tools_used=tools_used,
                        project_id=project_id or None,
                    )
                except Exception:
                    logger.debug("record_chat_turn_diary failed", exc_info=True)
            try:
                if refresh_title:
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
            # ── 交付证据链：把工具执行轨迹提炼成证据块，附在回复末尾 ──
            # 目的：Agent 说"完成"时给出可验证证据，用户无需再问"验证一下"
            # （数据依据：5293 条用户消息中验证类占 9%，是最大一类）
            # 默认关闭（with_evidence=False），避免改变既有行为。
            _evidence_block = ""
            if with_evidence:
                try:
                    from codeagent.server.evidence import build_evidence_appendix

                    _evidence_block = build_evidence_appendix(trace_out)
                except Exception:
                    logger.exception("build evidence appendix failed")
                    _evidence_block = ""
            if _evidence_block:
                reply = (reply or "") + "\n" + _evidence_block
            # ── Token 用量精确计算（基于 API 返回的 usage） ──
            _acc = {}
            _cost_info = {}
            _total_cost_info = {}
            _api_usage = {}
            try:
                from codeagent.core.usage_billing import merge_accumulated_usage

                _api_usage = dict(_loop_meta.get("usage_summary", {}) or {})
                _model_name = getattr(llm, "model", "") or _model_name
                _prev = chat_sess.metadata.get("accumulated_usage", {}) or {}
                _acc, _cost_info, _total_cost_info = merge_accumulated_usage(
                    _prev, _model_name, _api_usage
                )
                chat_sess.metadata["accumulated_usage"] = _acc
                from seed.core.agent_runtime import _get_compact_min_tokens as _get_cmt

                _ctx_pt = int(_ctx.get("prompt_tokens") or 0)
                _ws_evt = {
                    "type": "context_usage",
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "prompt_tokens": _ctx_pt,
                    "peak_prompt_tokens": int(_ctx.get("peak_prompt_tokens") or _ctx_pt),
                    "context_limit": _ctx.get("context_limit", 0),
                    "compact_min_tokens": _get_cmt(),
                    "message_count": _ctx.get("message_count", 0),
                    "token_usage": _api_usage,
                    "accumulated_usage": _acc,
                    "cost": _cost_info,
                    "accumulated_cost": _total_cost_info,
                    "model": _model_name,
                }
                if emit_ws and broadcast_fn is not None:
                    asyncio.run_coroutine_threadsafe(
                        broadcast_fn(agent_id, session_id, _ws_evt), main_loop
                    )
            except Exception:
                logger.exception("merge accumulated usage failed")
                _api_usage = {}
                _cost_info = {}
            try:
                persist_chat_session(chat_sess, agent_id)
            except Exception:
                logger.exception("persist session after billing failed")

            return {
                "reply": reply,
                "session_id": session_id,
                "tools_used": tools_used,
                "tool_trace": trace_out,
                "evidence": _evidence_block,
                "token_usage": _api_usage,
                "context": _ctx,
                "cost": _cost_info,
                "accumulated_cost": _total_cost_info,
                "accumulated_usage": _acc,
                "model": _model_name,
                "cancelled": bool(_run_was_cancelled),
            }
        except LLMError:
            with contextlib.suppress(Exception):
                chat_sess.messages.pop()
            raise
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
        if emit_ws and broadcast_fn is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    broadcast_fn(agent_id, session_id, {
                        "type": "run_finished",
                        "cancelled": bool(_run_was_cancelled),
                    }), main_loop
                )
                if _run_was_cancelled:
                    asyncio.run_coroutine_threadsafe(
                        broadcast_fn(agent_id, session_id, {
                            "type": "chat_cancelled",
                        }), main_loop
                    )
