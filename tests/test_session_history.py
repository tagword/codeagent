"""codeagent.server.webui_api_app 会话历史分页单元测试。

覆盖 _session_history_json_for_session 的 user-block 分页逻辑：
before_block_index / has_more / truncated_start / 消息截断。
"""


class FakeSession:
    """最小 session 对象：含 messages 列表和 metadata。"""

    def __init__(self, messages, metadata=None):
        self.messages = messages
        self.metadata = metadata or {}


def _mk_sess(n_blocks, msgs_per_block=2):
    """构造 n_blocks 个 user block，每块含 1 user + msgs_per_block-1 assistant。"""
    messages = []
    for i in range(n_blocks):
        messages.append({"role": "user", "content": f"u{i}"})
        for j in range(1, msgs_per_block):
            messages.append({"role": "assistant", "content": f"a{i}-{j}"})
    return FakeSession(messages)


def _rows_for(sess):
    """用真实 rows 函数得到 rows（与实现一致）。"""
    from codeagent.server import _webui_history_rows_from_session
    return _webui_history_rows_from_session(sess, 12000)


def _blocks(sess):
    from codeagent.server import _webui_history_partition_user_blocks
    return _webui_history_partition_user_blocks(_rows_for(sess))


# ---------- 空会话 ----------
def test_empty_session():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    out = _session_history_json_for_session(FakeSession([]), None)
    assert out["messages"] == []
    assert out["has_more_older"] is False
    assert out["first_block_index"] is None


# ---------- 基本分页（before_block_index=None → 取最后 max_blocks） ----------
def test_few_blocks_no_truncation():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(3)  # 3 个 block，少于默认 max_blocks(10)
    out = _session_history_json_for_session(sess, None)
    assert out["has_more_older"] is False
    assert out["truncated_start"] is False
    assert out["first_block_index"] == 0
    # 3 个 block 全返回
    assert sum(1 for m in out["messages"] if m["role"] == "user") == 3


def test_many_blocks_truncates_to_tail():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(15)  # 15 个 block，超过默认 max_blocks(10)
    out = _session_history_json_for_session(sess, None)
    # 只取最后 10 个 block
    assert out["has_more_older"] is True
    assert out["truncated_start"] is True
    assert out["first_block_index"] == 5
    assert sum(1 for m in out["messages"] if m["role"] == "user") == 10


# ---------- before_block_index 分页 ----------
def test_before_block_index_pagination():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(15)
    # 请求 before block 12 → 取 block 2..12（最多 10 个）
    out = _session_history_json_for_session(sess, before_block_index=12)
    assert out["has_more_older"] is True
    assert out["first_block_index"] == 2
    users = [m for m in out["messages"] if m["role"] == "user"]
    assert len(users) == 10
    assert users[0]["content"] == "u2"  # 从 block 2 开始


def test_before_block_index_early_no_more():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(5)
    # 请求 before block 3 → 取 block 0..3，无更早
    out = _session_history_json_for_session(sess, before_block_index=3)
    assert out["has_more_older"] is False
    assert out["first_block_index"] == 0


def test_before_block_index_zero():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(3)
    out = _session_history_json_for_session(sess, before_block_index=0)
    assert out["messages"] == []
    assert out["has_more_older"] is False


# ---------- 消息顺序保持 ----------
def test_messages_preserve_order():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = _mk_sess(2)
    out = _session_history_json_for_session(sess, None)
    contents = [m["content"] for m in out["messages"]]
    assert contents[0] == "u0"
    assert contents[-1] == "a1-1"


# ---------- metadata 传递 ----------
def test_metadata_passed_through():
    from codeagent.server.webui_api_app import _session_history_json_for_session
    sess = FakeSession([{"role": "user", "content": "hi"}], metadata={"accumulated_usage": {"total_cost": 1.5}})
    out = _session_history_json_for_session(sess, None)
    assert out["accumulated_usage"] == {"total_cost": 1.5}
