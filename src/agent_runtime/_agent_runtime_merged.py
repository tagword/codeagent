"""LLM + tool registry: OpenAI-style multi-turn tool loop."""
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations
from __future__ import annotations


from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


def _message_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


_COMPACT_BLOCK = re.compile(
    r"\n<<<CODEAGENT_COMPACT>>>\n.*?\n<<<END_CODEAGENT_COMPACT>>>\n",
    re.DOTALL,
)


# Grouping of tool names into "failure domains". When a loop ends with a streak
# of same-domain errors, the outer server loop can use this to switch strategy
# instead of naively replaying "please continue".
_FAILURE_DOMAIN_PREFIXES: Tuple[str, ...] = (
    "browser_",
    "bash_exec",
    "bash_tool",
    "file_",
    "web_",
)


def _classify_failure_domain(name: str) -> Optional[str]:
    if not name:
        return None
    for p in _FAILURE_DOMAIN_PREFIXES:
        if name.startswith(p):
            return p
    return None


def _is_tool_error_payload(payload: str) -> bool:
    """Heuristic: did this tool result represent a failure the model should
    NOT blindly retry with the same parameters?

    We match:
    - ``error:`` / ``Error:`` prefix produced by our executor wrappers
    - raw Python exceptions that still made it through: ``Tool '...' execution error: ...``
    - CDP timeouts that surface as normal tool strings containing
      ``CDP timeout`` / ``timeout calling``
    """
    if not isinstance(payload, str):
        return False
    s = payload.lstrip()
    if not s:
        return False
    low = s[:512].lower()
    if low.startswith("error:"):
        return True
    if "execution error" in low:
        return True
    if "cdp timeout" in low or "timeout calling" in low:
        return True
    return False


def _detect_failure_streak(
    outcomes: List[Tuple[str, bool, str]],
    *,
    min_streak: int = 3,
) -> Optional[Dict[str, Any]]:
    """Return info about a tail streak of same-domain errors, or ``None``.

    ``outcomes``: list of ``(tool_name, is_error, payload_excerpt)`` in call order.
    """
    if not outcomes:
        return None
    tail: List[Tuple[str, str]] = []
    for name, is_err, msg in reversed(outcomes):
        if is_err:
            tail.append((name, msg))
        else:
            break
    if len(tail) < min_streak:
        return None
    domains = {_classify_failure_domain(n) for n, _ in tail}
    if len(domains) != 1:
        return None
    dom = next(iter(domains))
    if dom is None:
        return None
    tail.reverse()
    return {
        "domain": dom,
        "streak": len(tail),
        "recent_errors": [
            {"tool": n, "error": (m or "")[:400]} for n, m in tail[-min_streak * 2 :]
        ],
    }





from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.tools.registry import ToolRegistry


def _consecutive_error_tail_count(outcomes: List[Tuple[str, bool, str]]) -> int:
    n = 0
    for _name, is_err, _msg in reversed(outcomes):
        if is_err:
            n += 1
        else:
            break
    return n


def _last_consecutive_error_block(
    outcomes: List[Tuple[str, bool, str]], k: int
) -> List[Tuple[str, str]]:
    """Most recent ``k`` outcomes among the trailing error run (newest last)."""
    buf: List[Tuple[str, str]] = []
    for name, is_err, msg in reversed(outcomes):
        if not is_err:
            break
        buf.append((name or "", (msg or "")[:500]))
        if len(buf) >= k:
            break
    buf.reverse()
    return buf


def _format_tool_error_streak_nudge(block: List[Tuple[str, str]]) -> str:
    lines = [
        "[CodeAgent] 已连续多次工具调用返回错误。请阅读下列摘要，**换一种策略**"
        "（换工具、换参数、或先排查环境），不要重复同一失败路径。",
        "",
        "最近错误摘要：",
    ]
    for i, (name, excerpt) in enumerate(block, 1):
        lines.append(f"{i}. `{name}`: {excerpt[:320]}{'…' if len(excerpt) > 320 else ''}")
    return "\n".join(lines)


def format_tool_segment_summary(
    tools_used: List[str],
    tool_trace: List[Dict[str, str]],
    *,
    max_trace: int = 8,
) -> str:
    """工具链调用摘要已禁用。保留签名兼容，始终返回空字符串。"""
    _ = tools_used, tool_trace, max_trace  # 标记参数已用（避免 lint warning）
    return ""


DEFAULT_SYSTEM = """你是 CodeAgent：谨慎的编程与系统助手（此为配置缺失时的后备 system）。

工具纪律：
- 问候、闲聊、致谢或无需文件/命令/搜索的一般问答：**只用自然语言回复，不要调工具**。
- 仅在用户明确需要执行时调用工具：读写文件、运行命令、搜索/代码分析、`calculate` 等。
- 若信息不足：先简短回答，**最多提一个**澄清问题，不要用工具瞎试。

合法调用工具后，用简短文字向用户归纳结果。"""


def registry_to_openai_tools(
    registry: ToolRegistry,
    *,
    exclude_prefixes: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Build Chat Completions `tools` from claw-style ToolRegistry."""
    tools: List[Dict[str, Any]] = []
    # Stable ordering matters for cache-prefix reuse (e.g. DeepSeek KV cache).
    # Sort by tool name so plugin load order does not perturb the tools schema.
    for tool in sorted(registry.list_all(), key=lambda t: (t.name or "")):
        if exclude_prefixes and any(
            tool.name.startswith(p) for p in exclude_prefixes if p
        ):
            continue
        props: Dict[str, Any] = {}
        required: List[str] = []
        for pname, pdef in (tool.parameters or {}).items():
            props[pname] = {
                "type": pdef.get("type", "string"),
                "description": pdef.get("description", ""),
            }
            if pdef.get("required"):
                required.append(pname)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            }
        )
    return tools




import re

# Chain-of-thought / reasoning markup (Qwen, DeepSeek, some proxies). Stripped
# before persisting assistant content so history does not reinforce repetition.
_THINK_BLOCK_RE = re.compile(
    r"(?:"
    r"<\s*think\s*>[\s\S]*?<\s*/\s*think\s*>"
    r"|"
    r"<\s*redacted_thinking\s*>[\s\S]*?<\s*/\s*redacted_thinking\s*>"
    r")",
    re.IGNORECASE,
)
_THINK_CLOSE_RE = re.compile(r"<\s*/\s*(?:think|redacted_thinking)\s*>", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<\s*(?:think|redacted_thinking)\s*>", re.IGNORECASE)
_HARMONY_CHANNEL_RE = re.compile(
    r"<\|(?:start|channel|message|end|constrain|return)\|>",
    re.IGNORECASE,
)


def _strip_think_markup(text: str) -> str:
    """Remove <think>...</think> chain-of-thought from assistant content.

    Handles three forms we have seen in the wild:
    - balanced ``<think>...</think>``
    - dangling ``</think>`` only (upstream stripped opening tag but left body)
    - dangling ``<think>`` only (stream truncated before closing tag)
    """
    if not text:
        return text
    t = _THINK_BLOCK_RE.sub("", text)
    # Dangling closing tag: treat everything up to and including it as thought.
    m_close = _THINK_CLOSE_RE.search(t)
    if m_close:
        t = t[m_close.end():]
    # Dangling opening tag: treat everything from it to end as thought.
    m_open = _THINK_OPEN_RE.search(t)
    if m_open:
        t = t[:m_open.start()]
    t = _HARMONY_CHANNEL_RE.sub("", t)
    return t


# ---------------------------------------------------------------------------
# Bare chain-of-thought detection.
#
# Some local stacks (sglang without --reasoning-parser, plain vLLM, certain
# Ollama builds) stream Qwen3 / DeepSeek-R1 "thinking tokens" straight into
# ``content`` with NO ``<think>`` markup at all. The model then sees these
# prose thought monologues in its own history and produces more of them,
# which looks to the user like infinite repetition / "表演思考".
#
# Observed pathological prefixes (20k+ char bodies):
#   "Here's a thinking process that leads to the suggested response: ..."
#   "The user wants to confirm if ..."
#   "User says ... I need to clarify ... Plan: 1. ... 2. ..."
#   "用户纠正了我对...的理解。用户指出：1. ..."
#   "我需要重新调整...的定义 ... **修正后的...**:"
#
# We can't strip partial CoT (no anchor), so we detect the whole-message
# pattern and redact it to an empty string. Upstream callers see assistant
# content=""/None and must either produce real output or call a tool.
# ---------------------------------------------------------------------------

# Strong CoT opener signals (single hit is enough when combined with length).
_BARE_COT_STRONG_OPENERS = (
    # English (gpt-oss / R1-distill / Qwen3-Thinking leak)
    "here's a thinking process",
    "here is a thinking process",
    "here is my thinking process",
    "here's my thinking",
    "let me think step by step",
    "let me analyze this",
    "let me analyze the user",
    "let me analyze what",
    "let me break this down",
    "let me think through this",
    "okay, let me think",
    "okay, so the user",
    "ok, so the user",
    "the user wants to",
    "the user is asking",
    "the user says",
    "the user's comment",
    "the user's feedback",
    "the user's question",
    "the user is essentially",
    "user wants to confirm",
    "user says",
    "user states",
    "i need to clarify",
    "i need to analyze",
    "i need to understand",
    "i need to figure out",
    "first, i need to",
    "first, let me",
    "my plan is",
    "plan:\n1.",
    "plan:\n- ",
    "plan:\n* ",
    "step 1:",
    "step 1.",
    # Chinese CoT (observed in ae507677 / f7de03f6)
    "用户纠正了我",
    "用户指出：",
    "用户指出:",
    "用户说的是",
    "用户的意思是",
    "用户想要确认",
    "用户想让我",
    "用户希望我",
    "用户的核心需求",
    "我需要重新调整",
    "我需要分析一下",
    "我需要澄清",
    "我需要先",
    "我需要弄清楚",
    "让我想一想",
    "让我分析一下",
    "让我思考一下",
    "让我先",
    "好的，让我",
    "好的，我来思考",
    "好，我来想一下",
    "我的失误",
    "修正后的",
    "修正版分析",
    "修正后角色定位",
    "思考过程：",
    "思维过程：",
    "分析用户的",
    "分析一下用户",
)

# Structural markers that amplify suspicion. Any single hit in the opening
# of the body is enough to classify a CoT-prefixed message as a monologue.
_BARE_COT_STRUCTURE_MARKERS = (
    re.compile(r"(?im)^\s*(?:plan|steps?|thinking)\s*[:：]\s*$"),
    re.compile(r"(?im)^\s*\d+\.\s+\*\*(?:analyze|evaluate|identify|determine|check|confirm|verify|explain|clarify)\b"),
    re.compile(r"(?im)^\s*\*\*(?:analyze|evaluate|identify|determine)\s"),
    re.compile(r"(?im)^\s*\d+\.\s+\*\*\s*(?:分析|评估|识别|确认|澄清|思考|判断|检查)"),
    re.compile(r"(?im)^\s*\*\s+\*\*(?:user|agent|model)'s?\s"),
    # Enumerated self-quote of user statements ("用户指出:" followed by "1. ... 2. ...").
    re.compile(r"(?s)用户(?:指出|说的是|的意思|想要|希望)[：:].{0,30}\n\s*\d+\."),
    # Self-plan heading in English ("Plan:\n1." or "Steps:\n1.")
    re.compile(r"(?im)^\s*(?:plan|steps?|outline)\s*[:：]\s*\n\s*\d+\."),
    # Two or more "Let me ..." / "I need to ..." / "First, I ..." in a row
    # strongly signal a monologue.
    re.compile(r"(?is)\blet me\b.{1,200}\b(?:let me|i need to|first,? i|then i|next,? i)\b"),
    re.compile(r"(?is)我需要.{1,200}(?:我需要|首先|然后|接下来|让我)"),
    re.compile(r"(?is)用户.{1,300}\b(?:我需要|我应该|我必须|我来|让我)"),
)


def _is_bare_chain_of_thought(text: str) -> bool:
    """Heuristic: does this assistant content look like raw chain-of-thought
    leaked into the message body (without any ``<think>`` markup)?

    Design goals:
    - Extremely high precision on multi-kilobyte CoT dumps like
      "Here's a thinking process that leads to the suggested response: ..."
    - Near-zero false positives on real answers. A real answer might start
      with "我需要" once, but will not also contain the Plan/Step/Analyze
      skeleton *and* be >1200 chars.

    We require BOTH:
    1. The opening (first 400 chars, lower-cased) hits a strong CoT phrase.
    2. Either (a) the body is long (>1200 chars) OR (b) there is at least one
       structural marker (numbered analyze/evaluate/identify skeleton).
    """
    if not text:
        return False
    body = text.strip()
    if len(body) < 400:
        # Short replies are almost never full CoT dumps; leave them alone.
        return False
    head = body[:400].lower()
    strong = False
    for needle in _BARE_COT_STRONG_OPENERS:
        if needle in head:
            strong = True
            break
    if not strong:
        return False
    # Length alone is sufficient once we're past the soft threshold, because
    # the opener already matched and real answers rarely exceed ~600 chars
    # while still opening with "Let me analyze" / "我需要" / "The user wants".
    if len(body) > 600:
        return True
    for rx in _BARE_COT_STRUCTURE_MARKERS:
        if rx.search(body[:2000]):
            return True
    return False


def scrub_bare_cot_from_assistant_text(text: str) -> str:
    """If the content is a bare CoT monologue, redact to empty so it doesn't
    pollute the next turn's context. Otherwise return as-is.

    This runs AFTER ``_strip_think_markup`` in the assistant-content pipeline,
    so by the time we get here we are looking at markup-free prose.
    """
    if not text:
        return text
    if _is_bare_chain_of_thought(text):
        return ""
    return text





import json
import os
import re
from typing import Any, Dict, List, Optional

from src.llm_exec_pkg import LLMAPIExecutor

_COMPACT_BLOCK = re.compile(
    r"\n<<<CODEAGENT_COMPACT>>>\n.*?\n<<<END_CODEAGENT_COMPACT>>>\n",
    re.DOTALL,
)


def _clean_orphaned_tool_calls(messages: List[Dict[str, Any]]) -> None:
    """In-place: remove assistant tool_calls that lack matching tool responses.

    When the tool loop is interrupted mid-execution (crash, disconnect, restart),
    the messages list may end with an assistant message containing ``tool_calls``
    but no corresponding ``tool`` role responses.  DeepSeek (and other strict
    OpenAI-compatible APIs) reject such incomplete histories with HTTP 400.

    This function scans backwards for orphaned tool_calls and either:
    - strips ``tool_calls`` from the assistant message (if it has text content)
    - removes the entire message (if content is empty or whitespace-only)
    """
    if not messages:
        return
    i = len(messages) - 1
    while i >= 0:
        msg = messages[i]
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            i -= 1
            continue
        raw_tc = msg.get("tool_calls")
        if not raw_tc:
            i -= 1
            continue
        # Collect tool_call_ids from this assistant message
        call_ids = set()
        for tc in raw_tc:
            if isinstance(tc, dict):
                tid = (tc.get("id") or "").strip()
                if tid:
                    call_ids.add(tid)
        if not call_ids:
            i -= 1
            continue
        # Check messages after this position for matching tool responses
        following = messages[i + 1:]
        responded_ids = set()
        for fm in following:
            if isinstance(fm, dict) and fm.get("role") == "tool":
                tid = (fm.get("tool_call_id") or "").strip()
                if tid in call_ids:
                    responded_ids.add(tid)
        missing = call_ids - responded_ids
        if missing:
            content = msg.get("content") or ""
            if content.strip():
                # Keep assistant message as regular text, drop tool_calls
                del msg["tool_calls"]
                logger.warning(
                    "Cleaned orphaned tool_calls from assistant msg "
                    "(missing %d tool response(s)): %s",
                    len(missing), sorted(missing)[:3],
                )
            else:
                # No text content → remove the entire orphaned message
                messages.pop(i)
                logger.warning(
                    "Removed empty assistant msg with orphaned tool_calls "
                    "(missing %d tool response(s)): %s",
                    len(missing), sorted(missing)[:3],
                )
        i -= 1


def build_api_projection_messages(
    full_messages: List[Dict[str, Any]],
    *,
    max_user_rounds: int,
    skills_suffix: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Deep-copy ``full_messages`` and apply in-memory-only shaping for the LLM:
    optional skills suffix on ``system``, then ``trim_messages_by_user_rounds``.

    Pass the result to ``maybe_compact_context_messages`` / ``run_llm_tool_loop``;
    do not replace persisted ``Session.messages`` with this list.
    """
    import copy as _copy

    api = _copy.deepcopy(full_messages)
    if skills_suffix and api and api[0].get("role") == "system":
        api[0]["content"] = str(api[0].get("content") or "").rstrip() + skills_suffix
    if max_user_rounds > 0:
        api[:] = trim_messages_by_user_rounds(api, max_user_rounds)
    _clean_orphaned_tool_calls(api)
    return api


def merge_llm_tail_into_full(
    full_messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    n_before_llm: int,
) -> List[Dict[str, Any]]:
    """Append messages produced during ``run_llm_tool_loop`` (``api_messages[n_before_llm:]``) onto ``full_messages``."""
    if n_before_llm < 0:
        n_before_llm = 0
    tail = api_messages[n_before_llm:]
    if tail:
        # If the last message in full is a streaming placeholder and tail starts
        # with an assistant message, replace the placeholder to avoid duplicate.
        if (full_messages
                and full_messages[-1].get("_streaming")
                and tail[0].get("role") == "assistant"):
            full_messages[-1] = tail[0]
            full_messages.extend(tail[1:])
        else:
            full_messages.extend(tail)
    return tail


def trim_messages_by_user_rounds(
    messages: List[Dict[str, Any]],
    max_user_rounds: int,
) -> List[Dict[str, Any]]:
    """
    Keep the system message (if present) and the last N user-started conversation blocks.
    Prevents unbounded growth of `messages` when tool outputs are large.
    """
    if max_user_rounds <= 0 or len(messages) <= 2:
        return messages
    has_system = bool(messages and messages[0].get("role") == "system")
    body_start = 1 if has_system else 0
    body = messages[body_start:]
    user_idx = [i for i, m in enumerate(body) if m.get("role") == "user"]
    if len(user_idx) <= max_user_rounds:
        return messages
    cut = user_idx[len(user_idx) - max_user_rounds]
    trimmed = body[cut:]
    if has_system:
        return [messages[0]] + trimmed
    return trimmed


def strip_compact_block_from_system(system_text: str) -> str:
    """Remove a previously injected compact summary from system prompt text."""
    return _COMPACT_BLOCK.sub("\n", system_text).strip()


def _context_compact_enabled() -> bool:
    return os.environ.get("CODEAGENT_CONTEXT_COMPACT", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _messages_body_json_bytes(messages: List[Dict[str, Any]], body_start: int) -> int:
    body = messages[body_start:]
    raw = json.dumps(body, ensure_ascii=False)
    return len(raw.encode("utf-8"))


def _format_transcript_for_summary(chunks: List[Dict[str, Any]], max_chars: int) -> str:
    lines: List[str] = []
    for m in chunks:
        role = m.get("role", "?")
        content = m.get("content")
        if content is None and m.get("tool_calls"):
            content = json.dumps(m.get("tool_calls"), ensure_ascii=False)[:2000]
        text = (content or "").strip()
        if len(text) > 8000:
            text = text[:4000] + "\n...[mid omitted]...\n" + text[-4000:]
        lines.append(f"### {role}\n{text}\n")
    blob = "\n".join(lines)
    if len(blob) <= max_chars:
        return blob
    head = max_chars // 2
    tail = max_chars - head
    return (
        blob[:head]
        + "\n\n...[transcript truncated for summarizer input]...\n\n"
        + blob[-tail:]
    )


def _summarizer_llm(fallback: LLMAPIExecutor) -> LLMAPIExecutor:
    """If CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL/MODEL are set, create a
    dedicated summarizer executor; otherwise return the fallback (main LLM).

    Inherits API key and auth scheme from the main LLM (fallback) so the
    summarizer can authenticate even when ``CODEAGENT_LLM_API_KEY`` is not set
    as an environment variable (e.g. credentials come from a preset)."""
    url = os.environ.get("CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL", "").strip()
    mod = os.environ.get("CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL", "").strip()
    if url and mod:
        from src.llm_exec_pkg import get_llm_executor

        return get_llm_executor(
            baseURL=url,
            model=mod,
            api_key=fallback.api_key,
            auth_scheme=fallback.auth_scheme,
        )
    return fallback




import os



def default_system_prompt() -> str:
    """Explicit env override, else config plane (if resolvable), else built-in default."""
    explicit = os.environ.get("CODEAGENT_SYSTEM_PROMPT")
    if explicit is not None and explicit.strip():
        return explicit.strip()
    try:
        from src.config_plane_pkg import build_system_prompt

        base = build_system_prompt()
        # Multi-agent core memory (persona/memory.md) — best-effort append.
        try:
            from src.codeagent.core.paths import agent_id_default, agent_persona_memory_path

            aid = agent_id_default()
            p = agent_persona_memory_path(aid)
            if p.is_file():
                try:
                    text = p.read_text(encoding="utf-8").strip()
                except OSError:
                    text = ""
                if text:
                    max_chars = int(os.environ.get("CODEAGENT_PERSONA_MEMORY_MAX_CHARS", "4000"))
                    max_chars = max(200, min(max_chars, 50_000))
                    if len(text) > max_chars:
                        text = text[: max_chars - 20].rstrip() + "\n…[已截断]"
                    base = (
                        base.rstrip()
                        + "\n\n---\n"
                        + f"## Persona core memory (`agents/{aid}/persona/memory.md`)\n\n"
                        + text
                        + "\n"
                    )
        except Exception:
            pass
        return base
    except Exception:
        return DEFAULT_SYSTEM



import logging
import os
from typing import Any, Dict, List

from src.chat_events import emit_chat_event
from src.llm_exec_pkg import LLMAPIExecutor, LLMError


logger = logging.getLogger(__name__)


def maybe_compact_context_messages(
    messages: List[Dict[str, Any]],
    llm: LLMAPIExecutor,
) -> None:
    """
    If enabled and the message tail (excluding system) exceeds a threshold (either
    ``MIN_BYTES`` or ``MIN_ROUNDS``), summarize older turns into the system prompt and
    drop older raw messages — keeps the last ``KEEP_USER_ROUNDS`` (default 3) verbatim.

    Env:
      CODEAGENT_CONTEXT_COMPACT=1
      CODEAGENT_CONTEXT_COMPACT_MIN_BYTES      (default 90000) — body JSON byte threshold
      CODEAGENT_CONTEXT_COMPACT_MIN_ROUNDS      (default 0, disabled) — user-round trigger
      CODEAGENT_CONTEXT_COMPACT_KEEP_USER_ROUNDS (default 3) — full turns to preserve
      CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_BASEURL — dedicated summarizer URL (optional)
      CODEAGENT_CONTEXT_COMPACT_SUMMARIZER_MODEL   — dedicated summarizer model (optional)
      CODEAGENT_CONTEXT_SUMMARIZER_MAX_INPUT     (default 120000) — cap for summarizer input chars
    """
    if not _context_compact_enabled():
        return
    if not messages:
        return
    has_system = messages[0].get("role") == "system"
    body_start = 1 if has_system else 0
    if body_start and len(messages) < 3:
        return

    min_bytes = int(os.environ.get("CODEAGENT_CONTEXT_COMPACT_MIN_BYTES", "90000"))
    min_rounds = int(os.environ.get("CODEAGENT_CONTEXT_COMPACT_MIN_ROUNDS", "0") or 0)
    keep_rounds = int(os.environ.get("CODEAGENT_CONTEXT_COMPACT_KEEP_USER_ROUNDS", "3"))
    max_in = int(os.environ.get("CODEAGENT_CONTEXT_SUMMARIZER_MAX_INPUT", "120000"))
    if keep_rounds < 1:
        return

    cur_bytes = _messages_body_json_bytes(messages, body_start)
    try:
        warn_ratio = float(os.environ.get("CODEAGENT_CONTEXT_COMPACT_WARN_RATIO", "0.85") or 0.85)
    except Exception:
        warn_ratio = 0.85
    warn_ratio = max(0.1, min(warn_ratio, 0.99))
    if cur_bytes >= int(min_bytes * warn_ratio):
        emit_chat_event(
            {
                "type": "context_usage",
                "body_bytes": int(cur_bytes),
                "compact_min_bytes": int(min_bytes),
                "warn_ratio": warn_ratio,
                "message_count": int(len(messages)),
            }
        )

    # Determine if compaction should trigger: either bytes exceed threshold,
    # or user rounds exceed the round-based threshold.
    body = messages[body_start:]
    user_idx = [i for i, m in enumerate(body) if m.get("role") == "user"]
    exceeds_bytes = cur_bytes >= min_bytes
    exceeds_rounds = (min_rounds > 0) and (len(user_idx) >= min_rounds)

    if not exceeds_bytes and not exceeds_rounds:
        return

    if len(user_idx) <= keep_rounds:
        return

    cut = user_idx[len(user_idx) - keep_rounds]
    old = body[:cut]
    recent = body[cut:]
    if not old:
        return

    transcript = _format_transcript_for_summary(old, max_in)
    sum_messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You compress prior agent chat for continuation. "
                "Output concise bullet points in the same language as the transcript. "
                "Preserve: file paths, shell commands, error messages, user goals, "
                "tool names used, and unresolved questions. "
                "Do not invent facts.\n\n"
                "TRANSIENT-FACT RULE (CRITICAL): Any runtime state that can change "
                "silently — e.g. process PIDs, listening ports, 'running/stopped' "
                "status, temp files, cwd, currently-open sessions — MUST be written "
                "as a snapshot, not as a lasting fact. Format such lines like:\n"
                "  - 『截至压缩时』PID 26364 监听 3001（需重新核对）\n"
                "  - 『As of compression』port 3000 was listening on PID 18064 (re-verify before use)\n"
                "Never write an unqualified 'PID X is running' / 'port Y is up' — "
                "the downstream agent will treat that as current truth and skip "
                "re-checking, which causes wrong conclusions when the process has "
                "since died.\n\n"
                "Max ~800 Chinese characters or ~500 English words."
            ),
        },
        {
            "role": "user",
            "content": "Transcript to compress:\n\n" + transcript,
        },
    ]
    summarizer = _summarizer_llm(llm)
    try:
        summary, _meta = summarizer.generate(sum_messages, tools=None)
    except LLMError as e:
        logger.warning("Context compact skipped (summarizer LLM error): %s", e)
        return

    summary = (summary or "").strip()
    if not summary:
        logger.warning("Context compact skipped (empty summary)")
        return

    sys_msg = messages[0]
    base = strip_compact_block_from_system(str(sys_msg.get("content") or ""))
    block = (
        "\n\n<<<CODEAGENT_COMPACT>>>\n"
        "## Earlier conversation (compressed)\n"
        f"{summary}\n"
        "<<<END_CODEAGENT_COMPACT>>>\n"
    )
    sys_msg["content"] = base + block
    messages[:] = [sys_msg] + recent
    emit_chat_event(
        {
            "type": "context_compact",
            "dropped_messages": int(len(old)),
            "kept_user_rounds": int(keep_rounds),
            "summary_chars": int(len(summary)),
            "compact_min_bytes": int(min_bytes),
            "body_bytes_before": int(cur_bytes),
        }
    )
    logger.info(
        "Context compact: dropped %s messages, kept %s user rounds verbatim",
        len(old),
        keep_rounds,
    )


def _truncate_tool_output(text: str) -> str:
    max_c = int(os.environ.get("CODEAGENT_TOOL_OUTPUT_MAX_CHARS", "48000"))
    if max_c <= 0 or len(text) <= max_c:
        return text
    drop = len(text) - max_c
    return text[:max_c] + f"\n...[truncated {drop} chars for context limit]"


"""OpenAI-style chat completions loop with tool execution."""


import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.chat_events import emit_chat_event
from src.llm_exec_pkg import LLMAPIExecutor
from src.tools import ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)


def _stream_llm_round(
    llm: LLMAPIExecutor,
    messages: List[Dict[str, Any]],
    tool_schema: Optional[List[Dict[str, Any]]],
    on_text_delta: Optional[Callable[[str], None]],
    on_reasoning_delta: Optional[Callable[[str], None]],
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Run one LLM round with per-token streaming (called in a thread).

    ``on_text_delta`` receives the **cumulative** text (full round text so far)
    so the frontend can compute the delta internally.
    """
    full_text = ""
    tool_calls: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}

    for event in llm.generate_stream(messages, tools=tool_schema):
        et = event.get("type")
        if et == "delta":
            text = event.get("text", "")
            full_text += text
            if on_text_delta:
                try:
                    on_text_delta(full_text)
                except Exception:
                    pass
        elif et == "reasoning_delta":
            text = event.get("text", "")
            if on_reasoning_delta:
                try:
                    on_reasoning_delta(text)
                except Exception:
                    pass
        elif et == "done":
            tool_calls = event.get("tool_calls") or []
            metadata = event.get("metadata", {})
            break

    return full_text, tool_calls, metadata


async def run_llm_tool_loop(
    llm: LLMAPIExecutor,
    executor: ToolExecutor,
    *,
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    max_tool_rounds: int = 16,
    on_round_persist: Optional[Callable[[List[Dict[str, str]], List[str]], None]] = None,
    on_text_delta: Optional[Callable[[str], None]] = None,
    on_reasoning_delta: Optional[Callable[[str], None]] = None,
) -> Tuple[str, Dict[str, Any], List[str], List[Dict[str, str]], Dict[str, Any]]:
    tools_used: List[str] = []
    tool_trace: List[Dict[str, str]] = []
    loop_meta: Dict[str, Any] = {"rounds": 0, "stopped_reason": None}

    oai_tools = registry_to_openai_tools(registry)
    tool_schema = oai_tools if oai_tools else None

    last_meta: Dict[str, Any] = {}

    for round_i in range(max(1, int(max_tool_rounds))):
        loop_meta["rounds"] = round_i + 1

        # --- Streaming LLM round (per-token) ---
        content, tool_calls, meta = await asyncio.to_thread(
            _stream_llm_round,
            llm,
            messages,
            tool_schema,
            on_text_delta,
            on_reasoning_delta,
        )
        last_meta = meta or {}

        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
        rc = last_meta.get("reasoning_content")
        if rc is not None:
            assistant_msg["reasoning_content"] = rc
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            if on_round_persist:
                try:
                    on_round_persist(list(tool_trace), list(tools_used))
                except Exception:
                    pass
            loop_meta["stopped_reason"] = "no_tool_calls"
            return content, last_meta, tools_used, tool_trace, loop_meta

        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            name = (fn.get("name") or "").strip()
            raw_args = fn.get("arguments") if isinstance(fn.get("arguments"), str) else "{}"
            if not isinstance(raw_args, str):
                raw_args = json.dumps(raw_args or {}, ensure_ascii=False)
            tid = str(tc.get("id") or "")
            tools_used.append(name)
            row: Dict[str, str] = {"name": name, "arguments": raw_args}
            tool_trace.append(row)

            event_id = str(uuid.uuid4())
            emit_chat_event(
                {
                    "type": "tool_start",
                    "event_id": event_id,
                    "tool": name,
                    "arguments": raw_args,
                }
            )
            try:
                try:
                    args_obj = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    args_obj = {}
                result = await executor.execute_with_validation_async(name, args_obj)
                out = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.exception("tool %s failed", name)
                out = f"Error executing tool {name!r}: {e}"

            snippet = out if len(out) <= 4000 else out[:4000] + "…"
            row["result"] = snippet

            if out:
                chunk = 8000
                for i in range(0, len(out), chunk):
                    emit_chat_event(
                        {
                            "type": "tool_output",
                            "event_id": event_id,
                            "tool": name,
                            "text": out[i : i + chunk],
                        }
                    )
            emit_chat_event(
                {
                    "type": "tool_end",
                    "event_id": event_id,
                    "tool": name,
                    "arguments": raw_args,
                    "result": snippet,
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tid,
                    "name": name,
                    "content": out,
                }
            )

        if on_round_persist:
            try:
                on_round_persist(list(tool_trace), list(tools_used))
            except Exception:
                pass

    loop_meta["stopped_reason"] = "max_tool_rounds"
    reply = ""
    if on_round_persist:
        try:
            on_round_persist(list(tool_trace), list(tools_used))
        except Exception:
            pass
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "assistant":
            c = m.get("content")
            reply = c if isinstance(c, str) else str(c or "")
            break
    return reply, last_meta, tools_used, tool_trace, loop_meta



import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.tools.registry import ToolRegistry

_TOOL_CALL_WRAPPER_RE = re.compile(
    r"<tool_call>\s*[\s\S]*?</tool_call>", re.IGNORECASE
)
_FUNCTION_BLOCK_RE = re.compile(
    r"<\s*function\s*=\s*(\w+)>\s*([\s\S]*?)</\s*function\s*>",
    re.IGNORECASE,
)
_PARAMETER_RE = re.compile(
    r"<\s*parameter\s*=\s*(\w+)>\s*([\s\S]*?)\s*</\s*parameter\s*>",
    re.IGNORECASE,
)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_ORPHAN_TOOL_CLOSE_RE = re.compile(
    r"</\s*(?:parameter|function|tool_call)\s*>",
    re.IGNORECASE,
)
_LOOSE_TOOL_OPEN_RE = re.compile(
    r"<\s*tool_call\s*>",
    re.IGNORECASE,
)
_LOOSE_FUNCTION_OPEN_RE = re.compile(
    r"<\s*function\s*=\s*\w+\s*>",
    re.IGNORECASE,
)
_LOOSE_PARAMETER_OPEN_RE = re.compile(
    r"<\s*parameter\s*=\s*\w+\s*>",
    re.IGNORECASE,
)


def strip_inline_tool_markup_from_assistant_text(text: str) -> str:
    """Remove Qwen-style pseudo-tool XML from assistant content before storing.

    Also strips orphan closing tags (e.g. ``</tool_call>``) left when HTML/Markdown
    sanitizers remove unknown opening tags, and stray opening tags without pairs.
    Additionally strips ``<think>...</think>`` chain-of-thought so it is not
    replayed into the next turn and cause self-reinforcing repetition.
    """
    if not text:
        return ""
    t = _strip_think_markup(text)
    t = _TOOL_CALL_WRAPPER_RE.sub("", t)
    t = _FUNCTION_BLOCK_RE.sub("", t)
    t = _PARAMETER_RE.sub("", t)
    t = _ORPHAN_TOOL_CLOSE_RE.sub("", t)
    t = _LOOSE_TOOL_OPEN_RE.sub("", t)
    t = _LOOSE_FUNCTION_OPEN_RE.sub("", t)
    t = _LOOSE_PARAMETER_OPEN_RE.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    # Final pass: redact bare chain-of-thought (no <think> markup at all,
    # just prose like "Here's a thinking process..." or "用户纠正了我...").
    # Required after markup strip because the markup pass is a no-op on these
    # leaks yet they still pollute history and re-trigger the model.
    t = scrub_bare_cot_from_assistant_text(t)
    return t


def parse_inline_qwen_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls that some models emit inside plain text, e.g.:

        <tool_call>
        <function=example_tool_name>
        <parameter=body>...</parameter>
        </function>
        </tool_call>

    Returns OpenAI-shaped tool_call dicts (ids are synthetic).
    """
    if not text or not re.search(r"<\s*function\s*=", text, re.IGNORECASE):
        return []
    out: List[Dict[str, Any]] = []
    for m in _FUNCTION_BLOCK_RE.finditer(text):
        name, inner = m.group(1), m.group(2)
        args: Dict[str, str] = {}
        for pm in _PARAMETER_RE.finditer(inner):
            k, v = pm.group(1), pm.group(2).strip()
            args[k] = v
        if not name:
            continue
        out.append(
            {
                "id": f"call_inline_{uuid.uuid4().hex[:16]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return out


def parse_inline_json_tool_calls(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse ```json ... ``` blocks that look like
    {"name": "tool", "arguments": {...}} or a list of such dicts.
    Returns (openai-shaped tool_calls, raw fence strings to strip from transcript).
    """
    out: List[Dict[str, Any]] = []
    consumed_fences: List[str] = []
    if not text or "```" not in text:
        return out, consumed_fences
    for m in _JSON_FENCE_RE.finditer(text):
        raw_inner = (m.group(1) or "").strip()
        if not raw_inner or '"' not in raw_inner:
            continue
        try:
            obj = json.loads(raw_inner)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        items: List[Dict[str, Any]] = []
        if isinstance(obj, dict):
            items = [obj]
        elif isinstance(obj, list):
            items = [x for x in obj if isinstance(x, dict)]
        batch: List[Dict[str, Any]] = []
        for item in items:
            name = item.get("name") or item.get("tool")
            if not name or not isinstance(name, str):
                continue
            args = item.get("arguments")
            if args is None:
                args = item.get("args") or item.get("parameters")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError, ValueError):
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if not args:
                args = {
                    k: v
                    for k, v in item.items()
                    if k
                    not in ("name", "tool", "type", "id", "arguments", "args", "parameters")
                }
            batch.append(
                {
                    "id": f"call_inline_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {
                        "name": name.strip(),
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        if batch:
            out.extend(batch)
            consumed_fences.append(m.group(0))
    return out, consumed_fences


def _strip_json_fences_once_each(text: str, fences: List[str]) -> str:
    t = text
    for f in fences:
        if f in t:
            t = t.replace(f, "", 1)
    return t.strip()


def _inline_tool_parse_enabled() -> bool:
    return os.environ.get("CODEAGENT_INLINE_TOOL_PARSE", "1").lower() not in (
        "0",
        "false",
        "no",
    )


def _allowed_tool_names_for_loop(
    registry: ToolRegistry,
    exclude_prefixes: Optional[Sequence[str]],
) -> set:
    names = {t.name for t in registry.list_all()}
    if exclude_prefixes:
        names = {
            n
            for n in names
            if not any(n.startswith(p) for p in exclude_prefixes if p)
        }
    return names


