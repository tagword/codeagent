"""Artifact persistence helpers"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from seed.tools.shell_helpers import _active_agent_and_session, _env_truthy

logger = logging.getLogger(__name__)

# Session tracking for artifacts (singleton-like in-memory state)
_last_artifact_dir = None
_session_start = datetime.now(timezone.utc)

def _artifact_write_text(*, kind: str, name_hint: str, text: str) -> Optional[str]:
    """
    Persist large tool outputs to disk and return the absolute artifact path.
    Controlled by:
      - CODEAGENT_TOOL_ARTIFACTS=1
      - CODEAGENT_TOOL_ARTIFACTS_MIN_CHARS (default 20000)
    """
    if not _env_truthy("CODEAGENT_TOOL_ARTIFACTS", "1"):
        return None
    try:
        min_chars = int(os.environ.get("CODEAGENT_TOOL_ARTIFACTS_MIN_CHARS", "20000") or 20000)
    except Exception:
        min_chars = 20000
    if min_chars > 0 and len(text or "") < min_chars:
        return None
    try:
        from seed.llm_sess import llm_sessions_dir

        agent_id, session_id = _active_agent_and_session()
        base = os.path.join(str(llm_sessions_dir(agent_id)), "_artifacts", session_id)
        os.makedirs(base, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_kind = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (kind or "tool"))[:48]
        safe_hint = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (name_hint or "output"))[:64]
        path = os.path.join(base, f"{ts}_{safe_kind}_{safe_hint}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "")
        return path
    except Exception:
        return None


def _artifact_summary(*, title: str, text: str, path: Optional[str]) -> str:
    """
    Return a compact response that keeps context small while leaving a breadcrumb to full text.
    """
    try:
        keep = int(os.environ.get("CODEAGENT_TOOL_ARTIFACTS_SUMMARY_CHARS", "4000") or 4000)
    except Exception:
        keep = 4000
    keep = max(200, min(keep, 20000))
    t = (text or "").strip()
    if len(t) > keep:
        head = keep // 2
        tail = keep - head
        excerpt = t[:head] + "\n...[中间省略]...\n" + t[-tail:]
        note = f"（原文 {len(t)} chars，已保存：{path}）" if path else f"（原文 {len(t)} chars）"
        return f"{title}\n{note}\n\n{excerpt}"
    note = f"（已保存：{path}）" if path else ""
    return f"{title}{note}\n\n{t}"


def _summarize_text_with_fallback(*, text: str, max_tokens: int) -> str:
    """
    Summarize text using an optional cheaper model, otherwise fall back to the main chat model.

    Env (optional):
      - CODEAGENT_TOOL_SUMMARY_BASEURL
      - CODEAGENT_TOOL_SUMMARY_MODEL
      - CODEAGENT_LLM_BASEURL / CODEAGENT_LLM_MODEL (fallback)
    """
    from seed.llm_exec import get_llm_executor

    baseurl = (
        os.environ.get("CODEAGENT_TOOL_SUMMARY_BASEURL", "").strip().rstrip("/")
        or os.environ.get("CODEAGENT_LLM_BASEURL", "").strip().rstrip("/")
    )
    model = (
        os.environ.get("CODEAGENT_TOOL_SUMMARY_MODEL", "").strip()
        or os.environ.get("CODEAGENT_LLM_MODEL", "").strip()
        or "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4"
    )
    if not baseurl:
        t = (text or "").strip()
        cap = 12000
        if len(t) <= cap:
            return t
        half = cap // 2
        return (
            t[:half]
            + "\n...[未配置 CODEAGENT_TOOL_SUMMARY_BASEURL / CODEAGENT_LLM_BASEURL，无法调用摘要模型；已截断]...\n"
            + t[-half:]
        )
    llm = get_llm_executor(baseURL=baseurl, model=model)
    sys = (
        "你是一个摘要助手。请将输入压缩成便于后续执行的摘要（中文输出）。\n"
        "要求：\n"
        "- 保留关键目标、约束、数字、路径、命令、接口、错误信息、决策点。\n"
        "- 以 5-12 条要点输出；必要时给出 TODO 与风险点。\n"
        "- 不要编造不存在的信息。\n"
        "- 摘要尽量短且信息密度高。"
    )
    content, _meta = llm.generate(
        [{"role": "system", "content": sys}, {"role": "user", "content": (text or "").strip()}],
        tools=None,
        max_tokens=max_tokens,
    )
    return (content or "").strip()




