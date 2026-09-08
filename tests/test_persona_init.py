"""codeagent.core.paths persona 默认文件初始化单元测试。

覆盖 _ensure_default_persona_files：已存在文件不覆盖、缺失文件从模板创建、
bundled 缺失时跳过。monkeypatch _read_bundled_persona_file 隔离真实 bundled。
"""
import codeagent.core.paths as p


def _mk_persona_dir(tmp_path):
    persona = tmp_path / "persona"
    persona.mkdir(parents=True)
    return persona


def _fake_bundled(fname):
    return f"# {fname} template body"


def _fake_bundled_partial(fname):
    # 只提供 agent.md，其他返回 None
    return "# agent.md template body" if fname == "agent.md" else None


def test_creates_missing_persona_files(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "_bundled_persona_defaults_dir", lambda: tmp_path / "tmpl")
    monkeypatch.setattr(p, "_read_bundled_persona_file", _fake_bundled)
    persona = _mk_persona_dir(tmp_path)
    p._ensure_default_persona_files(persona)
    assert (persona / "agent.md").is_file()
    assert (persona / "identity.md").is_file()
    assert (persona / "memory.md").is_file()
    assert "# agent.md template body" in (persona / "agent.md").read_text()


def test_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "_bundled_persona_defaults_dir", lambda: tmp_path / "tmpl")
    monkeypatch.setattr(p, "_read_bundled_persona_file", _fake_bundled)
    persona = _mk_persona_dir(tmp_path)
    (persona / "agent.md").write_text("CUSTOM", encoding="utf-8")
    p._ensure_default_persona_files(persona)
    # 已存在的 agent.md 不被覆盖
    assert (persona / "agent.md").read_text() == "CUSTOM"
    # 缺失的 identity.md 仍被创建
    assert (persona / "identity.md").is_file()


def test_no_bundled_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "_bundled_persona_defaults_dir", lambda: None)
    persona = _mk_persona_dir(tmp_path)
    p._ensure_default_persona_files(persona)
    # bundled 缺失 → 不创建任何文件
    assert not list(persona.iterdir())


def test_missing_bundled_file_skipped(tmp_path, monkeypatch):
    # 模板只提供 agent.md → 其他文件跳过不创建，不崩
    monkeypatch.setattr(p, "_bundled_persona_defaults_dir", lambda: tmp_path / "tmpl")
    monkeypatch.setattr(p, "_read_bundled_persona_file", _fake_bundled_partial)
    persona = _mk_persona_dir(tmp_path)
    p._ensure_default_persona_files(persona)
    assert (persona / "agent.md").is_file()
    assert not (persona / "tools.md").exists()
