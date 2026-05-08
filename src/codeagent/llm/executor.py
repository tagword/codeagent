"""LLM executor (compat wrapper)."""

from __future__ import annotations

from src.llm_exec_pkg import (  # noqa: F401
    LLMAPIExecutor,
    LLMError,
    assistant_toolcall_content_placeholder,
    get_llm_executor,
    reset_llm_executor,
)

