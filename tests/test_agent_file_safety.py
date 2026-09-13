"""codeagent.server.webui_api_app agent 文件读写路径穿越防护测试。

_read_agent_file / _write_agent_file 的 agent_id 用户可控（WebUI path param），
必须拒绝含路径分隔符/穿越的 agent_id，避免写到 agents 目录之外。
"""

import pytest

from codeagent.server import webui_handlers_agentmeta as w


@pytest.fixture
def agents_dir(tmp_path, monkeypatch):
    """把 _agents_dir 指向临时目录，隔离文件 IO。

    mock 接受可选 project_root 参数：生产代码会把注入的 project_root 透传进来，
    测试里统一忽略并固定到 tmp_path。
    """
    monkeypatch.setattr(w, "_agents_dir", lambda *a, **kw: tmp_path)
    return tmp_path


# ---------- _write_agent_file ----------
def test_write_normal_agent(agents_dir):
    assert w._write_agent_file("copy1", "hello", "persona", "system.md") is True
    p = agents_dir / "copy1" / "persona" / "system.md"
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == "hello"


def test_write_traversal_rejected(agents_dir):
    # 穿越 agent_id → 拒绝，不写穿
    assert w._write_agent_file("../../escape", "data", "x.txt") is False
    assert not (agents_dir.parent / "x.txt").exists()


def test_write_separator_rejected(agents_dir):
    assert w._write_agent_file("a/b", "data", "x.txt") is False


def test_write_empty_agent_id_rejected(agents_dir):
    assert w._write_agent_file("", "data", "x.txt") is False
    assert w._write_agent_file(None, "data", "x.txt") is False


# ---------- _read_agent_file ----------
def test_read_normal_agent(agents_dir):
    (agents_dir / "copy1" / "persona").mkdir(parents=True)
    (agents_dir / "copy1" / "persona" / "system.md").write_text("sys", encoding="utf-8")
    assert w._read_agent_file("copy1", "persona", "system.md") == "sys"


def test_read_missing_returns_none(agents_dir):
    assert w._read_agent_file("nonexistent", "persona", "system.md") is None


def test_read_traversal_rejected(agents_dir):
    assert w._read_agent_file("../../etc", "passwd") is None


def test_read_separator_rejected(agents_dir):
    assert w._read_agent_file("a/b", "x.txt") is None


def test_read_empty_agent_id_rejected(agents_dir):
    assert w._read_agent_file("", "x.txt") is None


# ---------- 回归：正常 agent 读写往返 ----------
def test_read_write_roundtrip(agents_dir):
    w._write_agent_file("agent-x", "内容", "persona", "system.md")
    assert w._read_agent_file("agent-x", "persona", "system.md") == "内容"
