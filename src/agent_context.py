"""Thread-local active LLM session id (for tools and logging during a turn)."""
from __future__ import annotations

import threading
from typing import Optional

_local = threading.local()


def set_active_llm_session(session_id: Optional[str]) -> None:
    if session_id:
        _local.session_id = session_id
    elif hasattr(_local, "session_id"):
        delattr(_local, "session_id")


def get_active_llm_session() -> Optional[str]:
    return getattr(_local, "session_id", None)


def set_active_project_episodic(scoped: bool, project_id: str = "") -> None:
    """
    Web UI chat: scoped=True 时 episodic 注入与 memory_search 按 project_id 隔离。
    project_id 为空表示「无项目」会话，只匹配未带 ## Project 的经验文件。
    CLI/cron：不要调用或 scoped=False，保持原有「不按项目过滤」行为。
    """
    _local.episodic_project_scoped = bool(scoped)
    _local.episodic_project_id = (project_id or "").strip() if scoped else ""


def clear_active_project_episodic() -> None:
    if hasattr(_local, "episodic_project_scoped"):
        delattr(_local, "episodic_project_scoped")
    if hasattr(_local, "episodic_project_id"):
        delattr(_local, "episodic_project_id")


def episodic_project_scope_active() -> bool:
    return bool(getattr(_local, "episodic_project_scoped", False))


def active_episodic_project_id() -> str:
    """当前 Web 请求下的项目 id（仅当 scope 开启时有效；否则返回空字符串）。"""
    if not episodic_project_scope_active():
        return ""
    return getattr(_local, "episodic_project_id", "") or ""
