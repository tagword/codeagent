"""A2A Bearer 认证 — 复用 WebUI token。

设计要点：
- **单一 token 源**：复用 `codeagent.web.auth_impl.get_webui_token()`，
  即 `CODEAGENT_WEBUI_TOKEN` 环境变量或 `config/webui.token` 文件。
  不引入第二套密钥，避免运维分裂。
- **未配置 token 时放行**：与 WebUI 行为一致（未设 token = 本机开发模式，
  WebUI 本身也不鉴权）。此时 Agent Card 不声明 security，客户端不会带 token。
- **常量时间比较**：`hmac.compare_digest` 防时序侧信道。
- **认证在 JSON-RPC 入口统一做**：所有方法（含 `message/stream` SSE）
  都经过 `a2a_jsonrpc`，故一处拦截即全覆盖。
"""

from __future__ import annotations

import hmac
import logging

from starlette.requests import Request

logger = logging.getLogger(__name__)

# JSON-RPC 错误码：-32001 = 未授权（A2A/实现自定义区间 -32000..-32099）
ERR_UNAUTHORIZED = -32001


def get_a2a_token() -> str:
    """返回期望的 Bearer token；空字符串表示未启用认证。"""
    try:
        from codeagent.web.auth_impl import get_webui_token

        return get_webui_token()
    except Exception:  # noqa: BLE001 - 认证不可用时不阻断服务
        logger.warning("a2a: 无法读取 webui token，A2A 认证降级为关闭", exc_info=True)
        return ""


def auth_enabled() -> bool:
    """是否启用 A2A 认证（配置了 token 才启用）。"""
    return bool(get_a2a_token())


def _extract_bearer(request: Request) -> str:
    raw = request.headers.get("authorization") or ""
    parts = raw.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def check_request(request: Request) -> bool:
    """校验请求是否通过认证。未配置 token 时恒为 True。"""
    expected = get_a2a_token()
    if not expected:
        return True
    got = _extract_bearer(request)
    if not got:
        return False
    return hmac.compare_digest(got.encode("utf-8"), expected.encode("utf-8"))
