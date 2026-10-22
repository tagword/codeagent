"""Agent Card 构建 — A2A 发现端点。

Agent Card 是 A2A Server 的「数字名片」：客户端据此判断该 agent 是否合适、
如何构造请求、如何安全通信。核心价值是**不透明性**——客户端无需读源码，
只靠声明的能力协作。
"""

from __future__ import annotations

import os
from typing import Any

from .auth import auth_enabled

PROTOCOL_VERSION = "0.2.5"


def _base_url() -> str:
    """A2A 服务基址（可用环境变量覆盖，便于容器/远程部署）。"""
    explicit = os.environ.get("CODEAGENT_A2A_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("CODEAGENT_A2A_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.environ.get("PICTUREBOOK_PORT", "").strip()  # 兼容误用
    port = os.environ.get("CODEAGENT_WEBUI_PORT", port or "18898").strip() or "18898"
    return f"http://{host}:{port}"


def build_agent_card() -> dict[str, Any]:
    """构建 Agent Card（对齐 A2A 规范字段）。"""
    base = _base_url()
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "name": "codeagent-rsi",
        "description": (
            "RSI 隔离实验副本 — 接收开发任务并自主执行："
            "探查代码 → 修改 → 写测试 → 自测 → 报告。"
        ),
        "url": f"{base}/a2a",
        "preferredTransport": "JSONRPC",
        # 规范 8.3.1：按优先级声明支持的传输组合，客户端据此选择。
        # 首个条目即首选接口（8.3.2 客户端 MUST 选第一个支持的传输）。
        "supportedInterfaces": [
            {
                "url": f"{base}/a2a",
                "transport": "JSONRPC",
            }
        ],
        "version": "1.0.0",
        "provider": {
            "organization": "CodeAgent RSI Lab",
            "url": base,
        },
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "dev-task",
                "name": "开发任务",
                "description": (
                    "接收自然语言描述的开发任务，自主完成代码修改与验证。"
                    "适用于：功能改造、缺陷修复、测试补充、代码审查。"
                ),
                "tags": ["development", "coding", "testing", "refactor"],
                "examples": [
                    "把 X 功能从 A 方案改成 B 方案",
                    "修复 Y 缺陷并补上回归测试",
                    "审查 Z 模块并报告问题",
                ],
                "inputModes": ["text"],
                "outputModes": ["text"],
            }
        ],
        # 认证声明与真实行为一致：未配置 token 时不声明 security，
        # 否则客户端会带 token 而服务端根本不校验（声明与实现脱节）。
        **(
            {
                "securitySchemes": {
                    "bearer": {
                        "type": "http",
                        "scheme": "bearer",
                        "description": "Bearer token（复用 WebUI token，见 config/webui.token）",
                    }
                },
                "security": [{"bearer": []}],
            }
            if auth_enabled()
            else {}
        ),
    }
