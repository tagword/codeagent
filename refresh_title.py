#!/usr/bin/env python3
"""
手动刷新会话标题：基于最早的用户消息（过滤 nudge），重新生成并持久化。
用法：
    python3 refresh_title.py <session_id_or_file>
    
示例：
    python3 refresh_title.py 71152ea2-2952-42d8-bc88-784111535ff0
    python3 refresh_title.py /path/to/session.json
    python3 refresh_title.py web-chat     # 默认 webui 会话
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from seed.core import env_access as _ea
from seed.core.llm_exec import LLMError
from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
from seed.core.llm_sess import llm_sessions_dir, load_or_create_chat_session, persist_chat_session

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# 跟 app_factory.py 保持一致 — 过滤 auto-continue 注入的 nudge
_DEFAULT_NUDGE_PREFIX = "请继续完成未完成事项"


def _is_nudge(msg: dict) -> bool:
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    c = str(msg.get("content") or "")
    return c.startswith(_DEFAULT_NUDGE_PREFIX[:20]) or c.startswith("上一段连续在")


def _user_context_for_title(messages, max_msgs=4, max_chars=200):
    """只取最早的非 nudge 用户消息（最多 max_msgs 条）。"""
    users = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        if _is_nudge(m):
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
    # 取最早的消息作为标题依据
    first = users[0]
    rest = users[1:]
    ctx = f"用户: {first}"
    for u in rest:
        ctx += f"\n用户: {u}"
    return ctx


def _sanitize_title(raw: str, max_chars: int) -> str:
    s = (raw or "").strip()
    s = re.sub(r'^[\"\'「」『』【】\[\]()（）]+|[\"\'「」『』【】\[\]()（）]+$', "", s)
    s = re.sub(r"\s+", " ", s).replace("\n", " ").strip()
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def refresh_title(session_id: str, agent_id: str = "default") -> str | None:
    """加载会话 → 过滤 nudge → LLM 生成标题 → 持久化。返回新标题或 None。"""
    # 1. 解析 LLM
    resolved = resolve_preset({})
    llm = llm_executor_from_resolved(resolved)

    # 2. 加载会话
    project_id = None
    chat_sess = load_or_create_chat_session(session_id, agent_id, project_id)
    if not chat_sess or not chat_sess.messages:
        logger.warning("会话为空或不存在")
        return None

    # 3. 过滤 nudge，构建标题上下文
    ctx = _user_context_for_title(chat_sess.messages)
    if not ctx.strip():
        logger.warning("无有效用户消息可用于标题生成")
        return None

    # 4. LLM 生成标题
    try:
        max_c = int(_ea.pick_default("36", *_ea.SESSION_TITLE_MAX_CHARS))
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
        tok = int(_ea.pick_default("96", *_ea.SESSION_TITLE_MAX_TOKENS))
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
        logger.error("LLM 标题生成失败: %s", e)
        return None

    if meta.get("tool_calls"):
        logger.warning("LLM 返回了 tool_calls，忽略")
        return None

    title = _sanitize_title(content, max_c)
    if not title:
        logger.warning("标题为空，跳过")
        return None

    # 5. 写入会话元数据
    chat_sess.metadata["display_title"] = title
    chat_sess.metadata["display_title_source"] = "llm"
    try:
        persist_chat_session(chat_sess)
        logger.info(f"✅ 标题已更新为: {title}")
        return title
    except Exception as e:
        logger.error(f"持久化失败: {e}")
        return None


def list_sessions(agent_id: str = "default"):
    """列出所有存盘会话及其当前标题。"""
    d = Path(llm_sessions_dir(agent_id))
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            meta = data.get("metadata", {})
            title = meta.get("display_title", "(无标题)")
            n_msgs = len(data.get("messages", []))
            # 找最早的非 nudge 用户消息
            first_msg = ""
            for m in data.get("messages", []):
                if m.get("role") == "user" and not _is_nudge(m):
                    first_msg = str(m.get("content", ""))[:60]
                    break
            print(f"{f.stem}")
            print(f"  标题: {title}")
            print(f"  首条: {first_msg}")
            print(f"  消息: {n_msgs} 条")
            print()
        except Exception as e:
            print(f"{f.stem}: 错误 {e}")
            print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 refresh_title.py list            # 列出所有会话")
        print("  python3 refresh_title.py <session_id>    # 刷新指定会话标题")
        sys.exit(1)

    if sys.argv[1] == "list":
        list_sessions()
        sys.exit(0)

    session_id = sys.argv[1]
    # 支持直接传文件路径
    if session_id.endswith(".json"):
        session_id = Path(session_id).stem

    title = refresh_title(session_id)
    if title:
        print(f"\n新标题: {title}")
    else:
        print("\n标题刷新失败")
        sys.exit(1)
