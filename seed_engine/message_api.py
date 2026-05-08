"""Projection layer: chat dicts on disk vs payloads acceptable to OpenAI-style APIs.

- ``internal`` and other non-standard roles are stripped in ``llm_executor._openai_chat_messages``.
- Use ``build_api_projection_messages`` / ``merge_llm_tail_into_full`` in ``agent_runtime`` for
  full-history vs LLM-window separation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from seed_engine.llm_exec import _openai_chat_messages


def to_openai_chat_payload(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a copy safe for HTTP chat/completions (roles + known keys only)."""
    return _openai_chat_messages(messages)
