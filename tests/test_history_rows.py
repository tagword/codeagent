"""codeagent.server._webui_history_rows_from_session 单元测试。

覆盖会话历史扁平化：role 过滤、非 dict 跳过、内容截断、attachments/tool_trace/ts 提取。
"""


class FakeSession:
    def __init__(self, messages):
        self.messages = messages


def _rows(sess, max_chars=100):
    from codeagent.server import _webui_history_rows_from_session
    return _webui_history_rows_from_session(sess, max_chars)


def test_basic_user_assistant():
    s = FakeSession([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
    ])
    rows = _rows(s)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "hi"
    assert rows[0]["text"] == "hi"
    assert rows[0]["idx"] == 0
    assert rows[1]["idx"] == 1


def test_filters_non_user_assistant_roles():
    s = FakeSession([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "tool-out"},
    ])
    rows = _rows(s)
    assert [r["role"] for r in rows] == ["user"]


def test_skips_non_dict_messages():
    s = FakeSession(["just-string", {"role": "user", "content": "hi"}, 42])
    rows = _rows(s)
    assert len(rows) == 1
    assert rows[0]["role"] == "user"


def test_truncates_long_content():
    s = FakeSession([{"role": "user", "content": "x" * 500}])
    rows = _rows(s, max_chars=100)
    assert len(rows[0]["content"]) <= 100
    assert "内容已截断" in rows[0]["content"]


def test_keeps_short_content_intact():
    s = FakeSession([{"role": "user", "content": "short"}])
    rows = _rows(s, max_chars=100)
    assert rows[0]["content"] == "short"


def test_extracts_attachments():
    s = FakeSession([{"role": "user", "content": "x", "attachments": [{"id": "a1"}]}])
    rows = _rows(s)
    assert rows[0]["attachments"] == [{"id": "a1"}]


def test_empty_attachments_not_included():
    s = FakeSession([{"role": "user", "content": "x"}])
    rows = _rows(s)
    assert "attachments" not in rows[0]


def test_extracts_tool_trace():
    s = FakeSession([{"role": "assistant", "content": "x", "tool_trace": [{"tool": "bash"}]}])
    rows = _rows(s)
    assert rows[0]["tool_trace"] == [{"tool": "bash"}]


def test_extracts_ts():
    s = FakeSession([{"role": "user", "content": "x", "ts": "1699999999"}])
    rows = _rows(s)
    assert rows[0]["ts"] == "1699999999"


def test_empty_ts_not_included():
    s = FakeSession([{"role": "user", "content": "x", "ts": ""}])
    rows = _rows(s)
    assert "ts" not in rows[0]


def test_empty_messages():
    assert _rows(FakeSession([])) == []
