"""LLM executor (compat wrapper)."""

from __future__ import annotations

from seed.core.llm_exec import (  # noqa: F401
    LLMAPIExecutor,
    LLMError,
    assistant_toolcall_content_placeholder,
    ensure_llm_executor_methods,
    get_llm_executor,
    reset_llm_executor,
)

# Idempotent; seed.core.llm_exec also runs this at import.
ensure_llm_executor_methods()
