"""codeagent.core.paths 路径安全单元测试。

聚焦 _sanitize_agent_id / _agent_work_dir 的路径穿越防护：
agent_id 用户可控（WebUI query / chat 参数），非法值必须被拒绝，避免路径穿越。
"""
import tempfile
from pathlib import Path

from codeagent.core import paths as p


def _tmp_root():
    return Path(tempfile.mkdtemp())


# ---------- _sanitize_agent_id ----------
def test_sanitize_allows_normal_ids():
    assert p._sanitize_agent_id("copy1") == "copy1"
    assert p._sanitize_agent_id("agent-2") == "agent-2"
    assert p._sanitize_agent_id("a_b.c") == "a_b.c"
    assert p._sanitize_agent_id("  spaced  ") == "spaced"


def test_sanitize_rejects_path_separators():
    assert p._sanitize_agent_id("../../etc") == ""
    assert p._sanitize_agent_id("a/b") == ""
    assert p._sanitize_agent_id("a\\b") == ""


def test_sanitize_rejects_empty():
    assert p._sanitize_agent_id("") == ""
    assert p._sanitize_agent_id("   ") == ""
    assert p._sanitize_agent_id(None) == ""


# ---------- _agent_work_dir 路径穿越防护 ----------
def test_work_dir_normal_agent():
    root = _tmp_root()
    d = p._agent_work_dir("copy1", root)
    assert ".codeagent" in str(d)
    assert d.name == "copy1"
    # 必须仍在 .codeagent 之下
    assert str(d).startswith(str(root))


def test_work_dir_rejects_traversal():
    root = _tmp_root()
    d = p._agent_work_dir("../../etc", root)
    # 非法 agent_id → 回退默认，绝不穿越到 .codeagent 之外
    assert ".codeagent" in str(d)
    assert str(d).startswith(str(root))
    # 不再引用 ../
    assert ".." not in str(d.relative_to(root))


def test_work_dir_rejects_separator():
    root = _tmp_root()
    d = p._agent_work_dir("a/b", root)
    assert ".codeagent" in str(d)
    assert str(d).startswith(str(root))


def test_work_dir_with_explicit_root_stays_under_root():
    root = _tmp_root()
    d = p._agent_work_dir("copy1", root)
    # resolve 后仍应位于 root 之下
    resolved = d.resolve()
    assert resolved.is_relative_to(root.resolve())


def test_state_file_write_read_normal():
    root = _tmp_root()
    p.write_state_file("hello state", "copy1", root)
    assert p.read_state_file("copy1", root) == "hello state"


def test_state_file_traversal_agent_goes_to_default():
    root = _tmp_root()
    # 用非法 agent_id 写 → 应落到 .codeagent/default/state.md，不穿越
    p.write_state_file("data", "../../escape", root)
    default_state = root / ".codeagent" / "default" / "state.md"
    assert default_state.is_file()
    assert p.read_state_file("../../escape", root) == "data"


def test_read_missing_state_returns_empty():
    root = _tmp_root()
    assert p.read_state_file("nonexistent-agent", root) == ""
