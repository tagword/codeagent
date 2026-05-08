"""Use LLM to set Session.metadata['display_title'] for Web UI session list."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from seed_engine.llm_sess import persist_chat_session
from seed_engine.models import Session

logger = logging.getLogger(__name__)

# 不把助手思维链/英文 CoT 喂给标题模型（否则会生成 “Thinking Process…” 类标题）
_THINKING_LINE = re.compile(
    r"(?is)^(thinking\s*process|思考过程|思维链|chain\s*of\s*thought|<redacted_thinking|<think\b|\*\*thinking)",
)
_BULLET_ANALYZE = re.compile(r"^\s*\d+\.\s*\*\*\s*analyze\b", re.I)


def _strip_assistant_noise_for_title(text: str) -> str:
    t = str(text or "").strip().replace("\r\n", "\n")
    if not t:
        return ""
    if _THINKING_LINE.search(t[:400]) or _BULLET_ANALYZE.search(t[:500]):
        return ""
    # 去掉常见 <think>…</think>
    t = re.sub(r"(?is)<think>.*?</think>", "", t).strip()
    return t


def _user_context_for_title(messages: List[Dict[str, Any]], *, max_msgs: int = 4, max_chars: int = 200) -> str:
    """标题只依据用户原话，避免助手正文/思维链污染。"""
    users: List[str] = []
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        raw = str(m.get("content") or "").strip().replace("\r\n", "\n")
        if not raw:
            continue
        if len(raw) > max_chars:
            raw = raw[:max_chars] + "…"
        users.append(raw)
        if len(users) >= max_msgs:
            break
    if not users:
        return ""
    users.reverse()
    return "\n".join(f"用户: {u}" for u in users)


def _fallback_title_from_users(messages: List[Dict[str, Any]], max_chars: int = 36) -> Optional[str]:
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        t = str(m.get("content") or "").strip().replace("\r\n", " ")
        if not t:
            continue
        t = re.sub(r"\s+", " ", t)
        if len(t) > max_chars:
            t = t[: max_chars - 1].rstrip() + "…"
        return t
    return None


def _title_looks_like_thinking_or_cot(title: str) -> bool:
    s = (title or "").strip()
    if not s:
        return True
    low = s.lower()
    if "thinking process" in low or "analyze the" in low:
        return True
    if re.match(r"^\d+\.\s*\*+", s):
        return True
    if s.startswith("**") and "analyze" in low[:80]:
        return True
    return False


def _sanitize_title(raw: str, max_chars: int) -> str:
    s = (raw or "").strip()
    s = re.sub(r'^[\"\'「」『』【】\[\]()（）]+|[\"\'「」『』【】\[\]()（）]+$', "", s)
    s = re.sub(r"\s+", " ", s).replace("\n", " ").strip()
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def llm_generate_display_title(llm: Any, session: Session) -> Optional[str]:
    from seed.llm_exec import LLMError

    ctx = _user_context_for_title(session.messages or [])
    if not ctx.strip():
        ctx = _strip_assistant_noise_for_title(
            str(
                next(
                    (
                        m.get("content")
                        for m in reversed(session.messages or [])
                        if isinstance(m, dict) and m.get("role") == "assistant"
                    ),
                    "",
                )
            )
        )
        if ctx:
            ctx = "助手摘要（已去思维链）:\n" + ctx[:400]
    if not ctx.strip():
        return None
    try:
        max_c = int(os.environ.get("CODEAGENT_SESSION_TITLE_MAX_CHARS", "36"))
    except ValueError:
        max_c = 36
    max_c = max(8, min(max_c, 80))
    sys_msg = (
        "你是会话标题生成器。输入仅为「用户」说过的话（每行一条）。"
        "请根据用户主题输出仅一行标题：简短自然，中文优先；"
        "不要英文、不要模仿思考步骤、不要 “Thinking/Analyze” 等词；"
        "不要引号、不要用「关于」开头、不要结尾句号，不要“会话”“聊天室”等泛词。"
    )
    user_msg = f"用户原话：\n{ctx}\n\n只输出一行标题，不超过{max_c}个字。"
    try:
        tok = int(os.environ.get("CODEAGENT_SESSION_TITLE_MAX_TOKENS", "96"))
    except ValueError:
        tok = 96
    tok = max(24, min(tok, 256))
    try:
        content, meta = llm.generate(
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            tools=None,
            max_turns=1,
            temperature=0.25,
            max_tokens=tok,
        )
    except LLMError as e:
        logger.warning("session title LLM failed: %s", e)
        return None
    if meta.get("tool_calls"):
        logger.warning("session title LLM returned tool_calls, ignoring")
    title = _sanitize_title(content, max_c)
    if not title:
        return _fallback_title_from_users(session.messages or [], max_c)
    if _title_looks_like_thinking_or_cot(title):
        logger.info("session title rejected as CoT-like, using user fallback")
        return _fallback_title_from_users(session.messages or [], max_c)
    return title


def maybe_llm_refresh_session_title(llm: Any, session: Session) -> None:
    """
    Writes metadata.display_title via LLM and re-persists session.

    CODEAGENT_SESSION_TITLE_LLM: default 1; set 0 to disable.
    CODEAGENT_SESSION_TITLE_MODE: default ``first`` (标题仅在首次成功生成后固定);
    设为 ``every`` 则每轮对话后重新提炼。
    """
    raw = os.environ.get("CODEAGENT_SESSION_TITLE_LLM", "1").lower()
    if raw in ("0", "false", "no", "off"):
        return
    mode = os.environ.get("CODEAGENT_SESSION_TITLE_MODE", "first").strip().lower()
    if mode not in ("first", "every"):
        mode = "first"
    if mode == "first" and session.metadata.get("display_title_source") == "llm":
        return
    title = llm_generate_display_title(llm, session)
    if not title:
        return
    session.metadata["display_title"] = title
    session.metadata["display_title_source"] = "llm"
    try:
        persist_chat_session(session)
    except Exception:
        logger.exception("persist after session title failed")
