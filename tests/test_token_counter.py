"""codeagent.core.token_counter 单元测试。

验证 count_messages 的 token 计数逻辑，重点验证 attachment/image_dir tag 剥离是否生效。
"""
from codeagent.core.token_counter import count_messages


def _tok(text):
    """用 seed 的 count_tokens 作为期望值基准（与实现一致）。"""
    from seed_model_providers.token_counter import count_tokens
    return count_tokens(text)


def test_empty_messages():
    r = count_messages([])
    assert r["message_count"] == 0
    assert r["total_tokens"] == 0
    assert r["content_tokens"] == 0


def test_single_text_message():
    msgs = [{"role": "user", "content": "hello"}]
    r = count_messages(msgs)
    # content tokens + 4 (per-message overhead)
    assert r["message_count"] == 1
    assert r["total_tokens"] == _tok("hello") + 4


def test_multiple_messages_accumulate():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    r = count_messages(msgs)
    assert r["message_count"] == 2
    assert r["total_tokens"] == _tok("hello") + _tok("world") + 2 * 4


def test_content_none_or_empty():
    r = count_messages([{"role": "user", "content": None}])
    # None → str(None)= "None"? 实际 str(content or "") = ""
    assert r["message_count"] == 1
    r2 = count_messages([{"role": "user"}])
    assert r2["message_count"] == 1


def test_attachment_tag_stripped_from_text():
    # attachment tag 应被剥离，不计入 token
    text = "看看这个文件 [attachment:abc123.png] 的内容"
    msgs = [{"role": "user", "content": text}]
    r = count_messages(msgs)
    # 剥离 tag 后计数
    from codeagent.core.attachments import ATTACHMENT_TAG_RE
    stripped = ATTACHMENT_TAG_RE.sub("", text)
    assert r["total_tokens"] == _tok(stripped) + 4


def test_image_dir_tag_stripped_from_text():
    text = "分析这目录 [image_dir:photos max=5]"
    msgs = [{"role": "user", "content": text}]
    r = count_messages(msgs)
    from codeagent.core.attachments import IMAGE_DIR_TAG_RE
    stripped = IMAGE_DIR_TAG_RE.sub("", text)
    assert r["total_tokens"] == _tok(stripped) + 4


def test_list_content_counts_text_parts():
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": {"url": "http://x/y.png"}},
        ],
    }]
    r = count_messages(msgs)
    # 只计 text 部分；image part 不计
    assert r["total_tokens"] == _tok("hello") + 4


def test_list_content_ignores_non_text():
    msgs = [{
        "role": "user",
        "content": [{"type": "image_url", "url": "http://x/y.png"}],
    }]
    r = count_messages(msgs)
    assert r["total_tokens"] == 4  # 只有 overhead
