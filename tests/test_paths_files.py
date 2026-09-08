"""codeagent.core.paths 状态/规则/gitignore 文件函数单元测试。

覆盖 read_state_file/write_state_file/read_global_rules/read_agent_rules/
_append_gitignore_entry。用 root 参数隔离到临时目录。
"""
import codeagent.core.paths as p


# ---------- state file ----------
def test_write_then_read_state(tmp_path):
    p.write_state_file("content", "a1", root=tmp_path)
    assert p.read_state_file("a1", root=tmp_path) == "content"


def test_read_state_missing_returns_empty(tmp_path):
    assert p.read_state_file("nope", root=tmp_path) == ""


def test_state_strips_whitespace(tmp_path):
    p.write_state_file("  hi  ", "a1", root=tmp_path)
    assert p.read_state_file("a1", root=tmp_path) == "hi"


def test_state_unsafe_agent_id_defaults(tmp_path, monkeypatch):
    # 非法 agent_id（穿越）→ 回退默认 agent 目录
    monkeypatch.setattr("seed.core.paths.agent_id_default", lambda: "defagent")
    p.write_state_file("x", "../evil", root=tmp_path)
    # 写到 defagent 而非穿越路径
    assert (tmp_path / ".codeagent" / "defagent" / "state.md").is_file()
    assert not (tmp_path.parent / "evil").exists()


# ---------- rules ----------
def test_read_global_rules_missing(tmp_path):
    assert p.read_global_rules(root=tmp_path) == ""


def test_read_global_rules_present(tmp_path):
    d = tmp_path / ".codeagent"
    d.mkdir(parents=True)
    (d / "rules.md").write_text("rule1", encoding="utf-8")
    assert p.read_global_rules(root=tmp_path) == "rule1"


def test_read_agent_rules(tmp_path):
    d = tmp_path / ".codeagent" / "a1"
    d.mkdir(parents=True)
    (d / "rules.md").write_text("agent rule", encoding="utf-8")
    assert p.read_agent_rules("a1", root=tmp_path) == "agent rule"


def test_read_agent_rules_missing(tmp_path):
    assert p.read_agent_rules("ghost", root=tmp_path) == ""


# ---------- _append_gitignore_entry ----------
def test_gitignore_created_if_missing(tmp_path):
    p._append_gitignore_entry(tmp_path)
    gi = tmp_path / ".gitignore"
    assert gi.is_file()
    assert ".codeagent/" in gi.read_text(encoding="utf-8")


def test_gitignore_no_duplicate(tmp_path):
    p._append_gitignore_entry(tmp_path)
    p._append_gitignore_entry(tmp_path)  # 第二次不应重复追加
    content = tmp_path / ".gitignore"
    assert content.read_text(encoding="utf-8").count(".codeagent/") == 1


def test_gitignore_appends_to_existing(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    p._append_gitignore_entry(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".codeagent/" in content


def test_gitignore_existing_entry_not_duplicated(tmp_path):
    (tmp_path / ".gitignore").write_text(".codeagent/\n", encoding="utf-8")
    p._append_gitignore_entry(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content.count(".codeagent/") == 1
