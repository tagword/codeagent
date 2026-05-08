"""LLM executor (compat wrapper)."""

from __future__ import annotations

from seed.llm_exec import (  # noqa: F401
    LLMAPIExecutor,
    LLMError,
    assistant_toolcall_content_placeholder,
    get_llm_executor,
    reset_llm_executor,
)

