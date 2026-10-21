"""A2A 数据模型 — 最小子集（对齐 A2A 规范 v0.2.x 的 JSON 形状）。

只实现本项目需要的部分：Message / Part / Task / TaskStatus / Artifact。
全部用 dataclass + ``to_dict``，避免引入 pydantic 依赖（seed 环境已有，
但 A2A 层保持轻量，便于单测）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Task 状态（A2A 规范状态机子集）──────────────────────────────
STATE_SUBMITTED = "submitted"
STATE_WORKING = "working"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELED = "canceled"
STATE_INPUT_REQUIRED = "input-required"

TERMINAL_STATES = frozenset({STATE_COMPLETED, STATE_FAILED, STATE_CANCELED})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ── Part / Message ─────────────────────────────────────────────
@dataclass
class Part:
    """A2A Part：内容容器（text / data / url / raw 四选一）。"""

    kind: str = "text"
    text: str = ""
    data: dict[str, Any] | None = None
    url: str = ""
    media_type: str = "text/plain"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Part:
        # 兼容两种写法：{"kind":"text","text":...} 与 {"text":...}
        kind = str(d.get("kind") or ("text" if "text" in d else "data"))
        return cls(
            kind=kind,
            text=str(d.get("text") or ""),
            data=d.get("data") if isinstance(d.get("data"), dict) else None,
            url=str(d.get("url") or ""),
            media_type=str(d.get("mediaType") or "text/plain"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind == "text":
            out["text"] = self.text
        elif self.kind == "data":
            out["data"] = self.data or {}
        elif self.kind == "url":
            out["url"] = self.url
            out["mediaType"] = self.media_type
        return out


@dataclass
class Message:
    """A2A Message：单轮通信。"""

    role: str = "user"
    parts: list[Part] = field(default_factory=list)
    message_id: str = ""
    context_id: str = ""
    task_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Message:
        return cls(
            role=str(d.get("role") or "user"),
            parts=[Part.from_dict(p) for p in (d.get("parts") or [])],
            message_id=str(d.get("messageId") or new_id("msg")),
            context_id=str(d.get("contextId") or ""),
            task_id=str(d.get("taskId") or ""),
        )

    def text(self) -> str:
        """拼接所有 text part。"""
        return "".join(p.text for p in self.parts if p.kind == "text")


# ── Artifact / Task ────────────────────────────────────────────
@dataclass
class Artifact:
    """A2A Artifact：实体产出。"""

    artifact_id: str
    name: str
    parts: list[Part]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "name": self.name,
            "description": self.description,
            "parts": [p.to_dict() for p in self.parts],
        }


@dataclass
class TaskStatus:
    state: str = STATE_SUBMITTED
    timestamp: str = field(default_factory=_now_iso)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"state": self.state, "timestamp": self.timestamp}
        if self.message:
            out["message"] = self.message
        return out


@dataclass
class Task:
    """A2A Task：有状态工作单元。"""

    id: str
    context_id: str
    status: TaskStatus
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "task",
            "id": self.id,
            "contextId": self.context_id,
            "status": self.status.to_dict(),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata,
        }
