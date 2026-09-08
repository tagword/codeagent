"""codeagent.runtime.compact_state 单元测试。

覆盖 inject_state_into_system：state.md 注入 system prompt 的格式与旧 block 替换。
read_state_file 用 monkeypatch 隔离文件 IO。
"""
import codeagent.runtime.compact_state as cs


def _patch_state(monkeypatch, text=""):
    # inject_state_into_system 函数内 import codeagent.core.paths.read_state_file
    monkeypatch.setattr(
        "codeagent.core.paths.read_state_file", lambda agent_id: text
    )


def test_empty_messages_noop(monkeypatch):
    _patch_state(monkeypatch, "some state")
    msgs = []
    cs.inject_state_into_system(msgs, "copy1")
    assert msgs == []


def test_no_state_noop(monkeypatch):
    _patch_state(monkeypatch, "")
    msgs = [{"role": "system", "content": "原始提示"}]
    cs.inject_state_into_system(msgs, "copy1")
    assert msgs[0]["content"] == "原始提示"  # 未改动


def test_inject_appends_state_block(monkeypatch):
    _patch_state(monkeypatch, "当前进度：第 5 步")
    msgs = [{"role": "system", "content": "原始提示"}]
    cs.inject_state_into_system(msgs, "copy1")
    content = msgs[0]["content"]
    assert content.startswith("原始提示")
    assert "<<<STATE>>>" in content
    assert "<<<END_STATE>>>" in content
    assert "当前进度：第 5 步" in content


def test_inject_replaces_old_state_block(monkeypatch):
    # 已有旧 STATE block → 应被替换，不叠加
    old = "原始提示\n\n<<<STATE>>>\n旧状态\n<<<END_STATE>>>"
    _patch_state(monkeypatch, "新状态")
    msgs = [{"role": "system", "content": old}]
    cs.inject_state_into_system(msgs, "copy1")
    content = msgs[0]["content"]
    # 旧状态被清除
    assert "旧状态" not in content
    # 新状态注入
    assert "新状态" in content
    # 只有一个 STATE block
    assert content.count("<<<STATE>>>") == 1
    assert content.count("<<<END_STATE>>>") == 1


def test_inject_first_msg_is_system(monkeypatch):
    _patch_state(monkeypatch, "state-x")
    msgs = [{"role": "system", "content": "提示"}, {"role": "user", "content": "hi"}]
    cs.inject_state_into_system(msgs, "copy1")
    # 只改第一条
    assert "<<<STATE>>>" in msgs[0]["content"]
    assert "<<<STATE>>>" not in str(msgs[1].get("content") or "")


def test_inject_state_with_special_chars(monkeypatch):
    _patch_state(monkeypatch, "含 <<<STATE>>> 字面量也不该破坏")
    msgs = [{"role": "system", "content": "p"}]
    cs.inject_state_into_system(msgs, "copy1")
    # 注入后应仍只有一个完整 block
    assert "<<<STATE>>>" in msgs[0]["content"]
