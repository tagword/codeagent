"""Package: llm_exec_pkg"""

from src.llm_exec_pkg._llm_exec_pkg_merged import LLMAPIExecutor
import src.llm_exec_pkg._llm_exec_pkg_merged as _LLMAPIExecutor_p2
import src.llm_exec_pkg._llm_exec_pkg_merged as _LLMAPIExecutor_p3
from src.llm_exec_pkg._llm_exec_pkg_merged import (
    LLMError,
    _extract_tool_calls,
    _is_deepseek_url,
    _msg_text_to_str,
    _openai_chat_messages,
    assistant_toolcall_content_placeholder,
)
from src.llm_exec_pkg._llm_exec_pkg_merged import get_llm_executor, reset_llm_executor

LLMAPIExecutor.generate = _LLMAPIExecutor_p2.generate
LLMAPIExecutor.generate_stream = _LLMAPIExecutor_p3.generate_stream
LLMAPIExecutor.count_tokens = _LLMAPIExecutor_p3.count_tokens
