"""
Token 计数适配层 — 基于 seed_model_providers.token_counter，增加 attachment tag 剥离。

如需使用原始 DeepSeek tokenizer 计数，直接 from seed_model_providers.token_counter import count_tokens.
"""

from __future__ import annotations

from typing import Any

from seed_model_providers.token_counter import count_tokens  # noqa: F401 — re-export

from codeagent.core.attachments import ATTACHMENT_TAG_RE, IMAGE_DIR_TAG_RE


def count_messages(messages: list[dict[str, Any]]) -> dict[str, int]:
    """计算一组消息的总 token 用量（剥离 attachment/image_dir 标记后再计）。"""
    from seed_model_providers.token_counter import count_tokens as _cnt_tok

    content_tokens = 0
    for msg in messages:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role == "tool":
            content_tokens += _cnt_tok(str(content or ""))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    content_tokens += _cnt_tok(part.get("text", ""))
        else:
            text = str(content or "")
            text = ATTACHMENT_TAG_RE.sub("", text)
            text = IMAGE_DIR_TAG_RE.sub("", text)
            content_tokens += _cnt_tok(text)
        content_tokens += 4

    return {
        "total_tokens": content_tokens,
        "content_tokens": content_tokens,
        "message_count": len(messages),
    }
