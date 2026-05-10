"""LLM executor (compat wrapper)."""

from __future__ import annotations

import seed.core.llm_exec as _seed_llm_exec
from seed.core.llm_exec import (  # noqa: F401
    LLMAPIExecutor,
    LLMError,
    assistant_toolcall_content_placeholder,
    get_llm_executor,
    reset_llm_executor,
)


def apply_llm_executor_method_patch() -> None:
    """Bind ``seed``'s chat helpers onto :class:`LLMAPIExecutor` when missing.

    Some ``seed`` wheels define ``generate`` / ``generate_stream`` / ``count_tokens``
    as module-level functions (first arg ``self``) but never attach them to the class.
    :func:`seed.core.agent_runtime.run_llm_tool_loop` then fails with
    ``AttributeError: 'LLMAPIExecutor' object has no attribute 'generate_stream'``.
    """
    if callable(getattr(LLMAPIExecutor, "generate_stream", None)):
        return
    # Same-module implementations used by OpenAI-compatible HTTP client.
    LLMAPIExecutor.generate = _seed_llm_exec.generate  # type: ignore[assignment]
    LLMAPIExecutor.generate_stream = _seed_llm_exec.generate_stream  # type: ignore[assignment]
    LLMAPIExecutor.count_tokens = _seed_llm_exec.count_tokens  # type: ignore[assignment]


apply_llm_executor_method_patch()
