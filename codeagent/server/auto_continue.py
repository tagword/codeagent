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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 视为"未完成"的状态
PENDING_STATUSES = frozenset({"pending", "in_progress", "todo", "doing"})

# 陈旧 pending 阈值（小时）：超过此时间未更新的待办不再阻止停止。
# 为什么需要：Agent 可能忘记更新 todo 状态，残留的 pending 项会导致
# auto-continue 反复触发（直到 max_segments 用尽），既浪费 token 又
# 违背"任务完成后自动停"的设计目标。
STALE_PENDING_HOURS = 24.0

# task.md 里的复选框（`- [ ]` 未完成 / `- [x]` 已完成）
_RE_TASK_UNCHECKED = re.compile(r"^\s*[-*]\s*\[\s*\]\s*(.+?)\s*$", re.M)
_RE_TASK_CHECKED = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.+?)\s*$", re.M)
# Wave 标题（`## Wave 2: ...`）——用于给出更有指向性的续跑提示
_RE_WAVE_HEADING = re.compile(r"^#{2,4}\s*(Wave\s*\d+[^\n]*)$", re.M | re.I)


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


def resolve_project_id(agent_id: str, project_id: str) -> str:
    """把可能是"名字"的 project_id 解析成真实 id。

    背景（端到端实测发现）：A2A / WebUI 传入的 ``projectId`` 可能是项目
    **名字**（如 ``ui-proj``）而非 id，导致 ``list_todos`` 查不到任何待办
    → 课题 2（未完成事项驱动续跑）静默失效。

    解析策略：
    1. 若已是有效 id（``get_project`` 能查到）→ 原样返回
    2. 否则在注册表里按 name / path 匹配 → 返回匹配到的 id
    3. 都失败 → 返回原值（调用方保守处理）
    """
    pid = (project_id or "").strip()
    if not pid:
        return ""
    try:
        from seed.core.proj_reg import get_project, list_projects

        if get_project(agent_id, pid):
            return pid
        # 按名字 / 路径匹配
        try:
            projects = list_projects(agent_id) or []
        except Exception:
            projects = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            path = str(p.get("path") or "").strip()
            if pid in (name, path) or (path and path.endswith("/" + pid)):
                return str(p.get("id") or pid)
    except Exception as e:  # noqa: BLE001
        logger.debug("resolve_project_id failed: %s", e)
    return pid


def _is_stale(item: dict[str, Any]) -> bool:
    """判断待办是否已陈旧（超过 STALE_PENDING_HOURS 未更新）。

    解析失败时返回 False（保守：宁可继续，不可漏掉真实待办）。
    """
    import time as _t
    from datetime import datetime

    raw = str(item.get("updated_at") or item.get("created_at") or "").strip()
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.astimezone()
        age_h = (_t.time() - dt.timestamp()) / 3600.0
        return age_h > STALE_PENDING_HOURS
    except Exception:  # noqa: BLE001
        return False


def get_pending_todos(
    agent_id: str,
    project_id: str,
    session_id: str = "",
) -> PendingSummary:
    """查询未完成事项（只读，失败保守返回空）。

    Args:
        agent_id: Agent 标识
        project_id: 项目标识（可为名字，内部会解析成 id）
        session_id: **已弃用**，保留仅为兼容签名。
            待办是**项目级**任务，跨会话有效——按 session 过滤会导致
            A2A/新会话查不到既有待办（端到端实测发现的静默失效）。

    Returns:
        PendingSummary（永不抛异常）
    """
    if not project_id:
        return PendingSummary()
    try:
        from seed.core.proj_todos import list_todos

        pid = resolve_project_id(agent_id, project_id)
        # 不传 session_id：待办是项目级的，跨会话/跨轮次都应可见。
        items = list_todos(agent_id, pid) or []
        pending = [
            it for it in items
            if isinstance(it, dict)
            and str(it.get("status") or "").strip().lower() in PENDING_STATUSES
            and not _is_stale(it)
        ]
        stale_n = sum(
            1 for it in items
            if isinstance(it, dict)
            and str(it.get("status") or "").strip().lower() in PENDING_STATUSES
            and _is_stale(it)
        )
        if stale_n:
            logger.info("ignored %d stale pending todos (>%sh)", stale_n, STALE_PENDING_HOURS)
        return PendingSummary(count=len(pending), items=pending)
    except Exception as e:  # noqa: BLE001
        logger.debug("get_pending_todos failed (conservative empty): %s", e)
        return PendingSummary(error=str(e))


def get_pending_plan(
    agent_id: str,
    project_id: str,
) -> PendingSummary:
    """从项目 ``$DOCS/task.md`` 读未完成的 Wave / 任务项。

    为什么需要（数据依据）
    ----------------------
    对 76 条「继续」类消息的上下文分析显示：
    - 7.9% 的 Agent 回复结尾是"要不要继续 / 确认后继续"
    - 5.3% 列出下一步等指示
    - 典型样例：「**进入 Wave 2 — 首页开发**？...**确认后继续** 🚀」

    即：**Agent 做完一个 Wave 就停下来问**，用户必须说「继续」。
    而 todo 方案覆盖不到这种场景——用户说"开发一个网站"时，
    Agent 并不会主动建 todo。

    ``task.md`` 是项目全流程的**强制产出**（见 skills.md Phase 3），
    格式固定（``- [ ]`` / ``- [x]``），因此是比 todo 更可靠的信号源。

    Returns:
        PendingSummary（永不抛异常）
    """
    if not project_id:
        return PendingSummary()
    try:
        from seed.core.proj_reg import resolve_project_path

        pid = resolve_project_id(agent_id, project_id)
        root = resolve_project_path(agent_id, pid) or ""
        if not root:
            return PendingSummary()
        task_md = Path(root) / ".codeagent" / "default" / "docs" / "task.md"
        if not task_md.is_file():
            return PendingSummary()
        text = task_md.read_text(encoding="utf-8", errors="replace")

        unchecked = [m.strip() for m in _RE_TASK_UNCHECKED.findall(text)]
        if not unchecked:
            return PendingSummary()

        # 找出这些未完成项所属的 Wave（就近向上找最近标题）
        items: list[dict[str, Any]] = []
        for line in unchecked[:20]:
            items.append({"content": line, "status": "pending", "source": "task.md"})
        return PendingSummary(count=len(unchecked), items=items)
    except Exception as e:  # noqa: BLE001
        logger.debug("get_pending_plan failed (conservative empty): %s", e)
        return PendingSummary(error=str(e))


def get_pending_all(
    agent_id: str,
    project_id: str,
    session_id: str = "",
) -> PendingSummary:
    """合并 todo 与 task.md 两个信号源（去重后返回）。

    设计：todo 反映"Agent 自己记的待办"，task.md 反映"项目计划"。
    两者都为空才算真正完成。

    安全约束：本函数是 chat_turn 续跑判定的入口，一旦抛异常会被
    ``except Exception: logger.debug(...)`` 静默吞掉 → Agent 误判
    "无未完成" 而停止（静默停止的隐形来源）。故自身兜底所有异常。
    """
    try:
        a = get_pending_todos(agent_id, project_id, session_id)
        b = get_pending_plan(agent_id, project_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("get_pending_all failed (conservative empty): %s", e)
        return PendingSummary(error=str(e))
    if a.error and b.error:
        return PendingSummary(error=a.error)
    if not a.has_pending and not b.has_pending:
        return PendingSummary()

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in list(a.items) + list(b.items):
        key = str(it.get("content") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(it)
    return PendingSummary(count=len(merged), items=merged)


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

    summary = get_pending_all(agent_id, project_id, session_id)
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
    has_plan = any(str(it.get("source")) == "task.md" for it in summary.items)
    lines = [
        f"【未完成事项】还有 {summary.count} 项未完成，请**继续推进**，"
        "不要停下来问用户「要不要继续」：",
    ]
    for it in summary.items[:6]:
        title = str(it.get("content") or it.get("title") or "").strip()
        st = str(it.get("status") or "").strip()
        src = str(it.get("source") or "")
        tag = "计划" if src == "task.md" else st
        if title:
            lines.append(f"- [{tag}] {title[:80]}")
    if has_plan:
        lines.append(
            "以上来自项目 task.md 计划。请直接开始下一项，"
            "完成后勾选 `- [x]` 并继续下一项，**不要请求确认**。"
        )
    else:
        lines.append("完成一项就更新它的状态；全部完成后直接总结结果。")
    return "\n".join(lines)
