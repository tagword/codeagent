"""A2A (Agent2Agent) 协议适配层 — 让 codeagent-rsi 作为标准 A2A Server 被调用。

为什么需要它
------------
此前主 Agent 与副本通信靠「逆向 WebUI 内部接口 + 模拟浏览器 cookie」——
脆弱、非标准、换版本即失效。A2A 是 agent 间通信的开放标准（Linux Foundation），
用 Agent Card 声明能力（不透明性），用 Task 生命周期管理长任务。

本包零侵入：只包装既有 ``run_chat_turn``，不改动 WebUI 路径。

模块：
- ``models``      A2A 数据模型（Message / Part / Task / TaskStatus）
- ``agent_card``  Agent Card 构建（发现端点）
- ``handlers``    JSON-RPC 处理器（message/send、message/stream、tasks/get）
- ``streaming``   SSE 流式支持（message/stream）
- ``context``     统一上下文解析（contextId / taskId 反查 / projectId 校验）
- ``client_card`` Agent Card 解析模型（发送端）
- ``client``      A2A 客户端（发现 → 协商 → 调用），供 ``a2a`` 工具使用
"""

from .agent_card import build_agent_card
from .client import A2AClient, A2AError, StreamEvent
from .client_card import AgentCard
from .handlers import a2a_agent_card, a2a_jsonrpc
from .streaming import stream_message, stream_response

__all__ = [
    "build_agent_card",
    "a2a_agent_card",
    "a2a_jsonrpc",
    "stream_message",
    "stream_response",
    "A2AClient",
    "A2AError",
    "StreamEvent",
    "AgentCard",
]
