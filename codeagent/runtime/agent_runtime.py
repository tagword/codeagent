"""Agent runtime (compat wrapper)."""

from __future__ import annotations

from seed.agent_runtime import (  # noqa: F401
    build_api_projection_messages,
    default_system_prompt,
    format_tool_segment_summary,
    maybe_compact_context_messages,
    merge_llm_tail_into_full,
    parse_inline_json_tool_calls,
    parse_inline_qwen_tool_calls,
    registry_to_openai_tools,
    scrub_bare_cot_from_assistant_text,
    strip_compact_block_from_system,
    strip_inline_tool_markup_from_assistant_text,
    trim_messages_by_user_rounds,
)

