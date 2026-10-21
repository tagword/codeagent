"""codeagent.runtime.prompt_enrichment._compute_persona_hash 单元测试。

覆盖 persona 哈希的确定性、内容变化触发 hash 变化（缓存失效依据）。
monkeypatch persona 目录与 rules 读取到临时路径隔离。
"""
import codeagent.runtime.prompt_enrichment as pe


def _patch_persona(monkeypatch, tmp_path, persona_files=None, memory=None):
    """构造临时 persona 目录并 monkeypatch seed 路径函数指向它。"""
    import seed.core.paths as sp

    persona_dir = tmp_path / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in (persona_files or {}).items():
        (persona_dir / fname).write_text(content, encoding="utf-8")
    if memory is not None:
        (persona_dir / "memory.md").write_text(memory, encoding="utf-8")

    monkeypatch.setattr(sp, "agent_persona_dir", lambda aid=None: persona_dir)
    monkeypatch.setattr(sp, "agent_persona_memory_path", lambda aid=None: persona_dir / "memory.md")
    return persona_dir


def test_hash_deterministic(tmp_path, monkeypatch):
    _patch_persona(monkeypatch, tmp_path, {"agent.md": "A", "soul.md": "S"}, memory="M")
    h1 = pe._compute_persona_hash("testagent")
    h2 = pe._compute_persona_hash("testagent")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_hash_changes_when_persona_edits(tmp_path, monkeypatch):
    _patch_persona(monkeypatch, tmp_path, {"agent.md": "A"}, memory="M")
    h1 = pe._compute_persona_hash("testagent")
    # 编辑 agent.md → hash 变（缓存失效）
    (tmp_path / "persona" / "agent.md").write_text("A-edited", encoding="utf-8")
    h2 = pe._compute_persona_hash("testagent")
    assert h1 != h2


def test_hash_changes_when_memory_edits(tmp_path, monkeypatch):
    _patch_persona(monkeypatch, tmp_path, {"agent.md": "A"}, memory="M1")
    h1 = pe._compute_persona_hash("testagent")
    (tmp_path / "persona" / "memory.md").write_text("M2", encoding="utf-8")
    h2 = pe._compute_persona_hash("testagent")
    assert h1 != h2


def test_hash_empty_persona_still_returns_hash(tmp_path, monkeypatch):
    _patch_persona(monkeypatch, tmp_path)  # 无文件
    h = pe._compute_persona_hash("testagent")
    assert len(h) == 64


def test_hash_includes_rules(tmp_path, monkeypatch):
    import codeagent.core.paths as cp
    # monkeypatch rules 读取返回不同内容 → hash 不同
    _patch_persona(monkeypatch, tmp_path, {"agent.md": "A"})
    monkeypatch.setattr(cp, "read_global_rules", lambda root=None: "rule-x")
    monkeypatch.setattr(cp, "read_agent_rules", lambda aid, root=None: "agent-rule")
    h1 = pe._compute_persona_hash("testagent")
    monkeypatch.setattr(cp, "read_global_rules", lambda root=None: "rule-y")
    h2 = pe._compute_persona_hash("testagent")
    assert h1 != h2
