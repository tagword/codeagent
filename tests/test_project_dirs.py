"""codeagent.core.paths ensure_project_dirs 单元测试。

覆盖项目工作目录结构创建、agent_id 净化、gitignore 追加。
"""
import codeagent.core.paths as p

_PROJECT_SUBDIRS = ("docs", "plans", "scripts", "sessions", "skills", "cache", "tmp")


def _mk(tmp_path, agent_id="a1"):
    return p.ensure_project_dirs(agent_id=agent_id, root=tmp_path)


def test_creates_codeagent_root(tmp_path):
    ca = _mk(tmp_path)
    assert ca == (tmp_path / ".codeagent")
    assert ca.is_dir()


def test_creates_global_rules(tmp_path):
    _mk(tmp_path)
    assert (tmp_path / ".codeagent" / "rules.md").is_file()


def test_creates_agent_subdirs(tmp_path):
    _mk(tmp_path, "a1")
    agent_dir = tmp_path / ".codeagent" / "a1"
    for sub in _PROJECT_SUBDIRS:
        assert (agent_dir / sub).is_dir(), f"missing {sub}"
    assert (agent_dir / "rules.md").is_file()
    assert (agent_dir / "state.md").is_file()


def test_unsafe_agent_id_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr("seed.core.paths.agent_id_default", lambda: "defagent")
    ca = _mk(tmp_path, "../evil")
    # 净化失败 → 回退默认 agent，不创建穿越目录
    assert (tmp_path / ".codeagent" / "defagent").is_dir()
    assert not (tmp_path.parent / "evil").exists()


def test_gitignore_created(tmp_path):
    _mk(tmp_path)
    gi = tmp_path / ".gitignore"
    assert gi.is_file()
    assert ".codeagent/" in gi.read_text(encoding="utf-8")


def test_idempotent_recreate(tmp_path):
    ca1 = _mk(tmp_path, "a1")
    ca2 = _mk(tmp_path, "a1")
    assert ca1 == ca2
    # 重复创建不报错，文件不重复
    assert (ca1 / "a1" / "docs").is_dir()
