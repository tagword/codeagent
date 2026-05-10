"""Resolve tool registry + executor for an agent (HTTP / cron)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from codeagent.core.models import Session


def tools_for_agent(agent_id: str):
    try:
        from codeagent.tools.agent_tools import get_tools_for_agent

        return get_tools_for_agent(agent_id)
    except Exception:
        from seed_tools import setup_builtin_tools

        return setup_builtin_tools()


_tools_for_agent = tools_for_agent


"""
HTTP + WebSocket + webhook (Starlette). Install: pip install 'codeagent[server]'
"""

logger = logging.getLogger(__name__)

# Shared with ``seed`` cron / runtime — re-export for ``app_factory`` / ``webui_api_app`` ``from . import``.
from seed.core._session_cache import (  # noqa: E402
    ACTIVE_CHAT_CANCELS,
    SESSIONS,
    WS_BY_SESSION,
    _memkey,
)

# 当前正在执行中的会话集合（mkey 格式：agent_id::session_id）
# 用于页面刷新后前端恢复运行状态指示
_running_sessions: set[str] = set()

def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


_DEFAULT_AUTO_CONTINUE_NUDGE = (
    "请继续完成未完成事项；基于已执行的工具结果继续推进，避免重复无效操作。"
    "若已完成请直接总结结果。"
)


async def _module_icon_png(_: Request) -> Response:
    """Serve icon.png (module-level to avoid Cython closure signature loss)."""
    p = Path(__file__).resolve().parent / "icon.png"
    if not p.is_file():
        return Response(status_code=404)
    return Response(
        content=p.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _module_favicon(_: Request) -> Response:
    """Serve favicon.ico → icon.png (module-level to avoid Cython closure signature loss)."""
    p = Path(__file__).resolve().parent / "icon.png"
    if not p.is_file():
        return Response(status_code=404)
    return Response(
        content=p.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# Domain-specific "switch strategy" playbooks. Triggered when the previous
# tool-loop segment ended with a tail streak of same-domain errors. The goal
# is NOT to halt, but to keep the agent going with a *different* approach
# (different tool, different resource, or HTTP-layer fallback) so the user's
# task actually progresses instead of looping on a broken path.
_AUTO_CONTINUE_DOMAIN_PLAYBOOKS: dict[str, str] = {
    "browser_": (
        "上一段连续在 browser_* 域失败（调试超时 / 目标 ws 僵尸 / 405 /json/new）。"
        "**禁止**再对同一 target_ws_url 重试同一操作。请换一条思路继续完成用户原本的任务：\n"
        "1) **回退到 HTTP 层验证**：用 `bash_exec` 执行 `curl.exe -sSi <url>` 或 `Invoke-WebRequest`，"
        "或调用 `web_fetch` 直接取 HTML/JSON，跳过浏览器层即可回答用户问题；\n"
        "2) **重建浏览器调试会话**：先调 `browser_targets` 查出现有 type=page 列表；"
        "若有其它存活目标，将 `target_ws_url` 改为 `'active'` 或该目标的 ws 再试一次；"
        "若没有，调 `browser_new_page`（已加 Target.createTarget 回退，可用）再做；\n"
        "3) **退一步排查底层**：`bash_exec` 跑 `netstat -ano | findstr :<port>` 和 "
        "`tasklist | findstr <image>` 确认服务/端口/进程是否还活着，判明根因后再决定是否继续 UI 层调试。\n"
        "请在下一步里选上面任意一条执行；不要把前面已失败的调用再重复一遍。"
    ),
    "bash_exec": (
        "上一段连续在 bash_exec 域失败。请换思路：\n"
        "1) 若启动的是长驻服务，请在下一次调用里显式 `detach=true`；\n"
        "2) 若是跨盘 `cd` / `&&` 失败，请使用 PowerShell 7 (pwsh) 语法，或改用分步多次 `bash_exec`；\n"
        "3) 先 `tasklist` / `netstat` 查状态，再决定后续命令。"
    ),
    "bash_tool": (
        "上一段连续在 bash_tool 域失败。请换思路：考虑改用 `bash_exec` 并显式声明 shell、timeout、detach，"
        "或先查当前环境变量/可执行路径再执行。"
    ),
    "file_": (
        "上一段连续在 file_* 域失败。请换思路：\n"
        "1) 先 `file_read` 核对实际内容，确认 `old_text` 与文件现状逐字符匹配（空格/制表符/换行）；\n"
        "2) 必要时改用 `file_write_tool` 重写小文件；\n"
        "3) 路径疑问用 `bash_exec` 先 `ls` / `Test-Path` 确认。"
    ),
    "web_": (
        "上一段连续在网络类工具失败。请换思路：\n"
        "1) 改用 `bash_exec` 跑 `curl.exe -sSi` 看实际 HTTP 状态与 body；\n"
        "2) 若 401/403，检查是否缺 Authorization header / token；\n"
        "3) 若超时，先确认本地网络可达性（ping / Test-NetConnection）。"
    ),
}


def _auto_continue_nudge(loop_meta: dict[str, Any] | None) -> str:
    """Pick the auto-continue message for the next segment.

    If the previous segment ended with a tail streak of same-domain failures,
    inject a domain-specific "switch strategy" playbook so the agent moves to a
    different approach instead of re-running the broken chain. Otherwise fall
    back to the generic "please continue" nudge.
    """
    if not isinstance(loop_meta, dict):
        return _DEFAULT_AUTO_CONTINUE_NUDGE
    dom = loop_meta.get("failure_domain")
    if not dom:
        return _DEFAULT_AUTO_CONTINUE_NUDGE
    playbook = _AUTO_CONTINUE_DOMAIN_PLAYBOOKS.get(str(dom))
    if not playbook:
        return _DEFAULT_AUTO_CONTINUE_NUDGE
    streak = int(loop_meta.get("failure_streak") or 0)
    recent_errors = loop_meta.get("recent_errors") or []
    lines: list[str] = [
        f"【策略切换触发】上一段连续 {streak} 次 tool 调用失败，均落在 `{dom}` 域。",
    ]
    if isinstance(recent_errors, list) and recent_errors:
        lines.append("最近错误节选：")
        for item in recent_errors[-3:]:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool") or "?")
            err_msg = str(item.get("error") or "")
            if len(err_msg) > 200:
                err_msg = err_msg[:200] + "…"
            lines.append(f"  - {tool_name}: {err_msg}")
    lines.append("")
    lines.append(playbook)
    return "\n".join(lines)


def _reply_append_tool_summary(reply: str, seg_summary: str) -> str:
    """Append a tool-chain Markdown summary to the user-visible reply (final segment)."""
    if not (seg_summary or "").strip():
        return reply or ""
    try:
        base = (os.environ.get("CODEAGENT_LLM_BASEURL", "") or "").lower()
        if "api.deepseek.com" in base and os.environ.get(
            "CODEAGENT_REPLY_TOOL_SUMMARY_DEEPSEEK", ""
        ).lower() not in ("1", "true", "yes", "on"):
            return reply or ""
    except Exception:
        pass
    if os.environ.get("CODEAGENT_REPLY_TOOL_SUMMARY", "1").lower() in (
        "0",
        "false",
        "no",
    ):
        return reply or ""
    r = (reply or "").rstrip()
    s = seg_summary.strip()
    return (r + "\n\n" + s) if r else s


def _webui_transcript_rows_from_session(sess: Session, max_chars: int) -> list[dict[str, Any]]:
    """Flatten session to user/assistant rows for Web UI replay (same shape as before)."""
    try:
        rc_max = int(os.environ.get("CODEAGENT_WEBUI_TRANSCRIPT_REASONING_MAX_CHARS", "50000"))
    except ValueError:
        rc_max = 50000
    rc_max = max(0, min(rc_max, 500_000))
    raw: list[dict[str, Any]] = []
    for m in sess.messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        if m.get("_streaming"):
            continue
        c = str(m.get("content") or "")
        if len(c) > max_chars:
            c = c[: max_chars - 24] + "\n…[内容已截断]"
        row: dict[str, Any] = {"role": str(role), "content": c}
        tt = m.get("tool_trace")
        if isinstance(tt, list) and tt:
            row["tool_trace"] = tt
        ts = m.get("ts")
        if ts is not None and str(ts).strip():
            row["ts"] = str(ts).strip()
        raw.append(row)
    return raw


def _webui_transcript_partition_user_blocks(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Each block starts at a user message; following assistant rows attach until the next user."""
    blocks: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for row in rows:
        if row.get("role") == "user":
            if cur:
                blocks.append(cur)
            cur = [row]
        else:
            if not cur:
                cur = [row]
            else:
                cur.append(row)
    if cur:
        blocks.append(cur)
    return blocks


def _listens_on_all_interfaces(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("0.0.0.0", "::", "*", "")


def _request_listen_port(request: Any) -> int:
    """TCP port for building Webhook URLs (URL, Host header, or CODEAGENT_PORT / 8765)."""
    try:
        p = request.url.port
        if p:
            return int(p)
    except Exception:
        pass
    host = (request.headers.get("host") or "").strip()
    if host.startswith("[") and "]:" in host:
        tail = host.split("]:", 1)[1]
        if tail.isdigit():
            return int(tail)
    if ":" in host and not host.startswith("["):
        tail = host.rsplit(":", 1)[1]
        if tail.isdigit():
            return int(tail)
    try:
        return int(os.environ.get("CODEAGENT_PORT", "8765"))
    except ValueError:
        return 8765


def _guess_lan_ipv4_addresses() -> list[str]:
    """Best-effort LAN IPv4 list for sharing Web UI / webhook URL (no extra deps)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(ip: str) -> None:
        if not ip or ip.startswith("127."):
            return
        if ip in seen:
            return
        seen.add(ip)
        ordered.append(ip)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.25)
            s.connect(("8.8.8.8", 80))
            add(s.getsockname()[0])
        except OSError:
            pass
        finally:
            s.close()
    except OSError:
        pass

    try:
        _, _, addr_list = socket.gethostbyname_ex(socket.gethostname())
        for a in addr_list:
            if a:
                add(a)
    except OSError:
        pass

    return ordered


def _print_serve_access_hints(host: str, port: int) -> None:
    """Help users open the Web UI from other devices and paste URLs into webhook config."""
    print()
    print(f"CodeAgent 本机访问: http://127.0.0.1:{port}/")
    if _listens_on_all_interfaces(host):
        ips = _guess_lan_ipv4_addresses()
        if ips:
            print("局域网访问（其它设备浏览器、Webhook 等可填下列地址）:")
            for ip in ips:
                print(f"  http://{ip}:{port}/")
            print(f"  示例 Webhook: http://{ips[0]}:{port}/webhook/in")
        else:
            print(
                f"未能自动检测局域网 IP，请在本机用 ipconfig / ifconfig 查看后手动填写 "
                f"http://<本机IP>:{port}/"
            )
    else:
        h = (host or "").strip()
        print(f"已绑定 {h}，访问: http://{h}:{port}/")
    print()


def main(host: str = "0.0.0.0", port: int = 8765) -> None:
    import uvicorn


    # Cron 调度在 Starlette on_startup 里启动（AsyncIOScheduler 需要已有运行中的事件循环）。
    _print_serve_access_hints(host, port)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


def _webui_root() -> Path:
    # server/../ -> codeagent/ (webui.html and webui/ live here)
    return Path(__file__).resolve().parent.parent


def _persist_long_user_input(*, agent_id: str, session_id: str, text: str) -> str | None:
    """
    Save long raw user input to disk and return an absolute path hint.
    Best-effort; failures do not block chat.
    """
    try:
        from seed.core.llm_sess import llm_sessions_dir

        base = Path(llm_sessions_dir(agent_id)) / "_user_inputs"
        base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        p = base / f"{session_id}_{ts}.txt"
        p.write_text(text, encoding="utf-8")
        return str(p)
    except Exception:
        return None


def _summarize_user_input_with_fallback(
    *,
    raw_text: str,
    baseurl: str,
    model: str,
    max_tokens: int,
) -> str:
    from seed.core.llm_exec import get_llm_executor

    sum_url = os.environ.get("CODEAGENT_USER_INPUT_SUMMARY_BASEURL", "").strip()
    sum_model = os.environ.get("CODEAGENT_USER_INPUT_SUMMARY_MODEL", "").strip()
    exec_url = (sum_url or baseurl).rstrip("/")
    exec_model = sum_model or model
    llm = get_llm_executor(baseURL=exec_url, model=exec_model)

    try:
        max_in = int(os.environ.get("CODEAGENT_USER_INPUT_SUMMARY_MAX_INPUT_CHARS", "60000") or 60000)
    except Exception:
        max_in = 60000
    max_in = max(2000, min(max_in, 400_000))

    blob = (raw_text or "").strip()
    if len(blob) > max_in:
        head = max_in // 2
        tail = max_in - head
        blob = blob[:head] + "\n\n...[内容过长，已截断中间部分用于摘要]...\n\n" + blob[-tail:]

    sys_prompt = (
        "你是一个摘要助手。请将用户提供的超长材料压缩成便于后续执行的摘要（中文输出）。\n"
        "要求：\n"
        "- 保留关键目标、约束、数字、路径、命令、接口、错误信息、决策点。\n"
        "- 将任务拆成 5-12 条要点；必要时给出 TODO 列表与风险点。\n"
        "- 不要编造不存在的信息。\n"
        "- 输出尽量短（建议 600-1500 汉字）。"
    )
    content, _meta = llm.generate(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": blob}],
        tools=None,
        max_tokens=max_tokens,
    )
    return (content or "").strip()


def _verify_webhook_signature(body: bytes, sig: str | None) -> bool:
    secret = os.environ.get("CODEAGENT_WEBHOOK_SECRET", "").strip()
    if not secret:
        logger.warning("CODEAGENT_WEBHOOK_SECRET unset — rejecting all webhook/in requests")
        return False
    if not sig or not sig.startswith("sha256="):
        logger.warning("webhook/in missing or malformed signature header")
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig[7:], expected):
        logger.warning("webhook/in signature mismatch")
        return False
    return True


def get_app_html() -> str:
    root = _webui_root()
    shell = root / "webui.html"
    parts_dir = root / "webui"
    body_primary = parts_dir / "body.html"

    shell_html = shell.read_text(encoding="utf-8")
    css_files = sorted(p for p in parts_dir.glob("*.css"))
    styles = "\n\n".join(p.read_text(encoding="utf-8") for p in css_files)
    body = (
        body_primary.read_text(encoding="utf-8")
        if body_primary.is_file()
        else "<div class=\"app\"><p>Web UI body 缺失：缺少 webui/body.html</p></div>"
    )

    js_files = sorted(p for p in parts_dir.glob("*.js"))
    scripts = "\n\n".join(p.read_text(encoding="utf-8") for p in js_files)

    return (
        shell_html.replace("/*{{STYLES}}*/", styles).replace("{{BODY}}", body).replace("{{SCRIPTS}}", scripts)
    )


def get_setup_html() -> str:
    """Full-page HTML for ``GET /setup``. Prefer repo-root ``web_setup.html`` if present."""
    root = _webui_root()
    single = root / "web_setup.html"
    if single.is_file():
        return single.read_text(encoding="utf-8")

    parts_dir = root / "webui" / "setup"
    names = (
        "setup_head.html",
        "setup_form.html",
        "setup_test.html",
        "setup_tail.html",
    )
    parts: list[str] = []
    for name in names:
        p = parts_dir / name
        if not p.is_file():
            logger.warning("setup wizard fragment missing: %s", p)
            parts = []
            break
        parts.append(p.read_text(encoding="utf-8"))
    if parts:
        return "".join(parts)

    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><meta charset=\"utf-8\"/>"
        "<title>CodeAgent Setup</title><body><h1>初始化</h1>"
        "<p>缺少向导片段（<code>seed/setup/*.html</code>）。"
        "可在仓库根放置 <code>web_setup.html</code>，或运行 <code>codeagent config init</code>。"
        "</p></body></html>"
    )


# --- Re-exports ---

from codeagent.server.app_factory import create_app  # noqa: E402
