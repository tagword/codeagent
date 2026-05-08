from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Callable, Dict, Optional

_EMITTER: ContextVar[Optional[Callable[[Dict[str, Any]], None]]] = ContextVar(
    "codeagent_chat_event_emitter",
    default=None,
)
_CURRENT_TOOL: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "codeagent_current_tool_context",
    default=None,
)
_CANCEL_CHECKER: ContextVar[Optional[Callable[[], bool]]] = ContextVar(
    "codeagent_chat_cancel_checker",
    default=None,
)


def set_chat_event_emitter(
    emitter: Optional[Callable[[Dict[str, Any]], None]]
) -> Token[Optional[Callable[[Dict[str, Any]], None]]]:
    return _EMITTER.set(emitter)


def reset_chat_event_emitter(token: Token[Optional[Callable[[Dict[str, Any]], None]]]) -> None:
    _EMITTER.reset(token)


def emit_chat_event(event: Dict[str, Any]) -> None:
    emitter = _EMITTER.get()
    if not emitter:
        return
    try:
        emitter(dict(event))
    except Exception:
        return


def set_current_tool_context(ctx: Optional[Dict[str, Any]]) -> Token[Optional[Dict[str, Any]]]:
    return _CURRENT_TOOL.set(ctx)


def reset_current_tool_context(token: Token[Optional[Dict[str, Any]]]) -> None:
    _CURRENT_TOOL.reset(token)


def get_current_tool_context() -> Optional[Dict[str, Any]]:
    ctx = _CURRENT_TOOL.get()
    return dict(ctx) if isinstance(ctx, dict) else None


def set_chat_cancel_checker(
    checker: Optional[Callable[[], bool]]
) -> Token[Optional[Callable[[], bool]]]:
    return _CANCEL_CHECKER.set(checker)


def reset_chat_cancel_checker(token: Token[Optional[Callable[[], bool]]]) -> None:
    _CANCEL_CHECKER.reset(token)


def is_chat_cancelled() -> bool:
    checker = _CANCEL_CHECKER.get()
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception:
        return False
