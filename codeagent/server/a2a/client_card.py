"""Agent Card 解析 — A2A 客户端侧的发现模型。

服务端 ``agent_card.build_agent_card`` 是「写名片」，
本模块是「读名片」：把对方返回的 JSON 解析成可查询的对象。

规范 8.3.2 对客户端有 MUST 级要求：
- 解析 ``supportedInterfaces``，选第一个**自己支持**的传输
- 多个可选时优先靠前的条目
- 用所选接口的 URL，而非猜测
- 请求要带该接口声明的 ``tenant``（未声明则省略）

因此本模块的核心价值是把「猜」变成「按声明读」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 本客户端实现的传输协议（目前只有 JSONRPC over HTTP）
SUPPORTED_TRANSPORTS = frozenset({"JSONRPC"})


@dataclass
class AgentInterface:
    """规范 4.4.6：一个可调用的传输接口。"""

    url: str
    transport: str
    tenant: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentInterface:
        return cls(
            url=str(d.get("url") or "").strip(),
            transport=str(d.get("transport") or "").strip().upper(),
            tenant=str(d.get("tenant") or "").strip(),
        )


@dataclass
class AgentSkill:
    """规范 4.4.5：Agent 声明的能力项。"""

    id: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentSkill:
        return cls(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or ""),
            description=str(d.get("description") or ""),
            tags=[str(t) for t in (d.get("tags") or [])],
        )


@dataclass
class AgentCard:
    """规范 4.4.1：Agent 名片（客户端视角）。"""

    name: str = ""
    description: str = ""
    url: str = ""
    version: str = ""
    protocol_version: str = ""
    preferred_transport: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    skills: list[AgentSkill] = field(default_factory=list)
    interfaces: list[AgentInterface] = field(default_factory=list)
    security_schemes: dict[str, Any] = field(default_factory=dict)
    security: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentCard:
        raw_ifaces = d.get("supportedInterfaces")
        interfaces: list[AgentInterface] = []
        if isinstance(raw_ifaces, list):
            interfaces = [
                AgentInterface.from_dict(x) for x in raw_ifaces if isinstance(x, dict)
            ]
        # 兼容旧名片：没有 supportedInterfaces 时用顶层 url + preferredTransport
        if not interfaces and d.get("url"):
            interfaces = [
                AgentInterface(
                    url=str(d.get("url") or ""),
                    transport=str(d.get("preferredTransport") or "JSONRPC").upper(),
                )
            ]

        caps = d.get("capabilities")
        return cls(
            name=str(d.get("name") or ""),
            description=str(d.get("description") or ""),
            url=str(d.get("url") or ""),
            version=str(d.get("version") or ""),
            protocol_version=str(d.get("protocolVersion") or ""),
            preferred_transport=str(d.get("preferredTransport") or "").upper(),
            capabilities=caps if isinstance(caps, dict) else {},
            skills=[AgentSkill.from_dict(s) for s in (d.get("skills") or []) if isinstance(s, dict)],
            interfaces=interfaces,
            security_schemes=d.get("securitySchemes") if isinstance(d.get("securitySchemes"), dict) else {},
            security=[s for s in (d.get("security") or []) if isinstance(s, dict)],
            raw=d,
        )

    # ── 能力查询 ────────────────────────────────────────────────
    @property
    def supports_streaming(self) -> bool:
        return bool(self.capabilities.get("streaming"))

    @property
    def supports_push_notifications(self) -> bool:
        return bool(self.capabilities.get("pushNotifications"))

    def select_interface(self) -> AgentInterface:
        """按规范 8.3.2 选择传输接口：第一个自己支持的。

        找不到时抛 ``ValueError``——**不猜测**，因为猜错 URL/传输
        比直接失败更难排查。
        """
        for iface in self.interfaces:
            if iface.transport in SUPPORTED_TRANSPORTS and iface.url:
                return iface
        available = ", ".join(f"{i.transport}({i.url})" for i in self.interfaces) or "无"
        raise ValueError(
            f"agent '{self.name}' 没有本客户端支持的传输接口；"
            f"对方声明: {available}；本客户端支持: {sorted(SUPPORTED_TRANSPORTS)}"
        )

    def requires_auth(self) -> bool:
        """是否需要认证（声明了 security 或 securitySchemes）。"""
        return bool(self.security) or bool(self.security_schemes)
