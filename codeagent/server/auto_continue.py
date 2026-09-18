"""未完成事项驱动续跑 — 让 Agent 自主跑完一批，而非做完一步就停。

为什么需要（数据依据）
----------------------
对 5293 条真实用户消息的分析显示：
- **`继续` 出现 74 次，是最高频消息**
- 根因：Agent 架构是响应式的——做完一步就停，等用户说"继续"
- 现有 `auto_continue` 机制只在 **max_tool_rounds 用尽**时触发，
  无法覆盖"Agent 自己觉得做完了，但任务其实没完"的场景

本模块提供**判断依据**：会话/项目里是否还有未完成事项（todo）。
若有，则 auto-continue 应继续跑，而不是停下等用户推。

设计原则
--------
- **零侵入**：纯查询函数，不修改 todo 存储；调用方决定是否续跑
- **安全**：只读，且失败时返回"无未完成"（保守，不会导致无限跑）
- **可审计**：返回具体未完成项，便于日志/调试
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 视为"未完成"的状态
PENDING_STATUSES = frozenset({"pending", "in_progress", "todo", "doing"})


@dataclass
class PendingSummary:
    """未完成事项摘要。"""

    count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def has_pending(self) -> bool:
        return self.count > 0

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "items": self.items[:10], "error": self.error}


def get_pending_todos(
    agent_id: str,
    project_id: str,
    session_id: str = "",
) -> PendingSummary:
    """查询未完成事项（只读，失败保守返回空）。

    Args:
        agent_id: Agent 标识
        project_id: 项目标识（空则无法查询，返回空）
        session_id: 可选，限定到当前会话

    Returns:
        PendingSummary（永不抛异常）
    """
    if not project_id:
        return PendingSummary()
    try:
        from seed.core.proj_todos import list_todos

        items = list_todos(agent_id, project_id, session_id=session_id or None) or []
        pending = [
            it for it in items
            if isinstance(it, dict)
            and str(it.get("status") or "").strip().lower() in PENDING_STATUSES
        ]
        return PendingSummary(count=len(pending), items=pending)
    except Exception as e:  # noqa: BLE001
        logger.debug("get_pending_todos failed (conservative empty): %s", e)
        return PendingSummary(error=str(e))


def should_continue(
    agent_id: str,
    project_id: str,
    session_id: str = "",
    *,
    segments_used: int = 0,
    max_segments: int = 4,
) -> tuple[bool, str]:
    """判断是否应该继续跑（而非停下等用户）。

    返回 ``(should, reason)``：
    - ``should=True`` 表示还有未完成事项，应继续
    - ``reason`` 是给日志/调试的说明

    安全约束：
    - 达到 max_segments 硬上限 → 不继续（防失控）
    - 查询失败 → 不继续（保守）
    """
    if segments_used >= max_segments:
        return False, f"已达分段上限 {max_segments}"

    summary = get_pending_todos(agent_id, project_id, session_id)
    if summary.error:
        return False, f"查询失败（保守停止）: {summary.error}"
    if not summary.has_pending:
        return False, "无未完成事项"

    first = summary.items[0] if summary.items else {}
    title = str(first.get("content") or first.get("title") or "")[:40]
    return True, f"还有 {summary.count} 项未完成（如「{title}」）"


def build_continue_nudge(summary: PendingSummary) -> str:
    """为"未完成事项"生成续跑提示（比通用 nudge 更有指向性）。"""
    if not summary.has_pending:
        return ""
    lines = [
        f"【未完成事项】还有 {summary.count} 项待办，请继续推进，不要停下等用户：",
    ]
    for it in summary.items[:5]:
        title = str(it.get("content") or it.get("title") or "").strip()
        st = str(it.get("status") or "").strip()
        if title:
            lines.append(f"- [{st}] {title[:80]}")
    lines.append("完成一项就更新它的状态；全部完成后直接总结结果。")
    return "\n".join(lines)
