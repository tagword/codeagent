"""
DeepSeek V3 tokenizer 封装 — 用于准确计算 token 用量。

安装依赖：pip install tokenizers
Tokenizer 文件来源：https://cdn.deepseek.com/api-docs/deepseek_v3_tokenizer.zip
"""

from __future__ import annotations

import os
from typing import Any

_TOKENIZER_DIR = os.path.join(os.path.dirname(__file__), "deepseek_tokenizer")
_TOKENIZER_PATH = os.path.join(_TOKENIZER_DIR, "tokenizer.json")

_tokenizer = None


def _load_tokenizer():
    """延迟加载 DeepSeek tokenizer"""
    global _tokenizer
    if _tokenizer is not None:
        return _tokenizer
    if not os.path.isfile(_TOKENIZER_PATH):
        # tokenizer 文件不存在，回退
        return None
    try:
        from tokenizers import Tokenizer
        _tokenizer = Tokenizer.from_file(_TOKENIZER_PATH)
        return _tokenizer
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """计算单段文本的 token 数"""
    tok = _load_tokenizer()
    if tok is None:
        # fallback: 使用 DeepSeek 文档的公式
        # 1 中文字符 ≈ 0.6 token, 1 英文字符 ≈ 0.3 token
        cn = 0
        en = 0
        for ch in text:
            cp = ord(ch)
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF:
                cn += 1
            else:
                en += 1
        return int(cn * 0.6 + en * 0.3 + 0.5)  # 四舍五入
    try:
        return len(tok.encode(text).ids)
    except Exception:
        return len(text.encode("utf-8")) // 4


def count_messages(messages: list[dict[str, Any]]) -> dict[str, int]:
    """计算一组消息的总 token 用量

    DeepSeek 计算方式：
    - 所有消息 content 的 token 之和
    - 每条消息额外开销（role 标记等）：约 4 tokens
    """
    content_tokens = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            # 多模态消息
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    content_tokens += count_tokens(part.get("text", ""))
        else:
            content_tokens += count_tokens(str(content))
        # role 标记开销
        content_tokens += 4

    return {
        "total_tokens": content_tokens,
        "content_tokens": content_tokens,
        "message_count": len(messages),
    }
