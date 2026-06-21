"""LLM worker: isolated tool loop per agent_id."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from seed.core.agent_context import set_active_llm_session
from seed.core.agent_runtime import (
    build_api_projection_messages,
    maybe_compact_context_messages,
    merge_llm_tail_into_full,
    persist_compact_summary,
    resolve_compact_trigger_tokens,
    run_llm_tool_loop,
    strip_ephemeral_message_fields,
)
from seed.core.llm_exec import LLMError
from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
from seed.core.llm_sess import load_or_create_chat_session, merge_fresh_system, persist_chat_session
from seed.core.mem_bridge import finalize_episodic_for_llm

from codeagent.runtime.prompt_enrichment import build_skills_suffix, fresh_system_prompt, get_cached_system_prompt
from codeagent.tools.agent_tools import get_tools_for_agent


@dataclass
class LLMWorker:
    """Run one user turn with per-agent tools and optional project scope."""

    agent_id: str = "default"
    project_id: str = ""

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        tools: list[dict[str, Any]] | None = None,
        max_tool_rounds: int = 16,
    ) -> tuple[str, dict[str, Any]]:
        aid = (self.agent_id or "default").strip() or "default"
        sid = (session_id or "worker").strip() or "worker"
        mkey = f"{aid}::{sid}"

        reg, exe = get_tools_for_agent(aid)
        llm = llm_executor_from_resolved(resolve_preset(None))

        chat_sess = load_or_create_chat_session(sid, aid, self.project_id or None)
        fresh_sys = get_cached_system_prompt(chat_sess, agent_id=aid)
        if not chat_sess.messages:
            chat_sess.messages = [{"role": "system", "content": fresh_sys}]
        else:
            chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

        chat_sess.messages.append({"role": "user", "content": user_text})
        skills_suffix = build_skills_suffix(aid, user_text=user_text)
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            skills_suffix=skills_suffix,
        )
        _prev_cu = (
            chat_sess.metadata.get("context_usage")
            if isinstance(chat_sess.metadata, dict)
            else None
        )
        _compact_pt = resolve_compact_trigger_tokens(
            persisted=_prev_cu if isinstance(_prev_cu, dict) else None,
        ) or None
        compact_result = maybe_compact_context_messages(
            api_msgs,
            llm,
            api_prompt_tokens=_compact_pt,
            persisted_context_usage=_prev_cu if isinstance(_prev_cu, dict) else None,
        )
        persist_compact_summary(chat_sess.messages, compact_result)
        strip_ephemeral_message_fields(api_msgs)
        from codeagent.runtime.compact_state import inject_state_into_system

        if compact_result:
            inject_state_into_system(
                api_msgs,
                aid,
            )
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        finalize_episodic_for_llm(
            api_msgs,
            chat_sess.metadata,
            agent_id=aid,
            session_id=sid,
            project_id=self.project_id or None,
            compact_happened=compact_result is not None,
        )

        set_active_llm_session(mkey)
        try:
            n_before = len(api_msgs)
            reply, meta, tools_used, tool_trace, loop_meta = asyncio.run(
                run_llm_tool_loop(
                    llm,
                    exe,
                    messages=api_msgs,
                    registry=reg,
                    max_tool_rounds=max_tool_rounds,
                )
            )
            merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before)
            persist_chat_session(chat_sess, aid)
            out_meta = dict(meta or {})
            out_meta.update(loop_meta or {})
            out_meta["agent_id"] = aid
            out_meta["tools_used"] = tools_used
            out_meta["tool_trace"] = tool_trace
            return reply or "", out_meta
        except LLMError as e:
            return f"[LLM error] {e}", {"agent_id": aid, "error": str(e)}
        finally:
            set_active_llm_session(None)

