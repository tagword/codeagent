"""P0 回归测试：agent 写入根与读取根必须一致（新建后可见）。

复现的真实缺陷（18898 RSI 副本）：
  WebUI 新建 agent 返回 201 Created，日志显示注册成功，但列表里看不到。

  根因是**两套根解析机制**：
    - 写入：``ensure_agent_scaffold`` → ``seed.core.config_plane.project_root()``
      （读 ``SEED_PROJECT_ROOT``）
    - 读取：``_list_agent_metas`` → ``_agents_dir()`` → ``codeagent_home()``
      （读 ``CODEAGENT_HOME``，默认 ``~/.codeagent``）

  当 ``SEED_PROJECT_ROOT`` 被外部设为非默认位置（如隔离副本的
  ``.rsi/workspace/ui-proj``）时，两者分叉：agent 建在
  ``$SEED_PROJECT_ROOT/agents``，列表却读 ``~/.codeagent/agents`` → 看不见。

修复：``_agents_dir`` / ``_teams_dir`` / ``_list_agent_metas`` 等接受注入的
``project_root``（由 ``build_*_routes(project_root)`` 传入），与写入端同根。

本测试在修复前失败（列表读不到新建 agent），修复后通过。
"""

from __future__ import annotations

from pathlib import Path

from codeagent.server import webui_handlers_agentmeta as meta


def _make_agent(root: Path, agent_id: str) -> Path:
    """在 root/agents/<id>/persona 下建一个合格 agent。"""
    persona = root / "agents" / agent_id / "persona"
    persona.mkdir(parents=True)
    (persona / "identity.md").write_text("I am a test agent", encoding="utf-8")
    return root / "agents" / agent_id


# ---------- 核心回归：写入根 == 读取根 ----------
def test_agents_dir_follows_injected_project_root(tmp_path):
    """_agents_dir(project_root) 必须用注入根，而非 codeagent_home()。"""
    root = tmp_path / "isolated-root"
    root.mkdir()
    assert meta._agents_dir(root) == root / "agents"


def test_agents_dir_defaults_to_codeagent_home_when_unspecified():
    """不传参时保持向后兼容（回退 ~/.codeagent/agents）。"""
    from codeagent.core.paths import codeagent_home

    assert meta._agents_dir() == codeagent_home() / "agents"


def test_created_agent_visible_under_same_root(tmp_path):
    """核心场景：在 root 下建的 agent，用同一 root 列表必须能看见。

    这是 18898「新建后不显示」的直接复现。
    """
    root = tmp_path / "ui-proj"
    root.mkdir()
    _make_agent(root, "agent1")

    metas = meta._list_agent_metas(root)
    ids = [m["id"] for m in metas]
    assert "agent1" in ids, "新建的 agent 必须出现在列表中（写入/读取同根）"


def test_created_agent_invisible_when_root_diverges(tmp_path):
    """反例：若读取用了错误的根（旧行为），agent 就看不见。

    证明修复的必要性——不是测试写错，而是分叉确实导致不可见。
    """
    write_root = tmp_path / "ui-proj"
    read_root = tmp_path / "other-home"
    write_root.mkdir()
    read_root.mkdir()
    _make_agent(write_root, "agent1")

    # 用「错误的」读取根 → 看不见（复现旧 bug）
    ids_wrong = [m["id"] for m in meta._list_agent_metas(read_root)]
    assert "agent1" not in ids_wrong

    # 用「正确的」写入根 → 看得见（修复后行为）
    ids_right = [m["id"] for m in meta._list_agent_metas(write_root)]
    assert "agent1" in ids_right


# ---------- 读写文件同样跟随注入根 ----------
def test_read_write_agent_file_follows_project_root(tmp_path):
    root = tmp_path / "ui-proj"
    root.mkdir()
    _make_agent(root, "agent1")

    assert meta._write_agent_file(
        "agent1", "sys prompt", "persona", "system.md", project_root=root
    ) is True
    got = meta._read_agent_file(
        "agent1", "persona", "system.md", project_root=root
    )
    assert got == "sys prompt"

    # 确认落盘位置就在注入根下
    assert (root / "agents" / "agent1" / "persona" / "system.md").is_file()


def test_teams_dir_follows_project_root(tmp_path):
    root = tmp_path / "ui-proj"
    root.mkdir()
    assert meta._teams_dir(root) == root / "teams"


# ---------- 路径穿越防护未被破坏 ----------
def test_traversal_guard_still_active(tmp_path):
    root = tmp_path / "ui-proj"
    root.mkdir()
    assert meta._write_agent_file(
        "../../escape", "x", "y.txt", project_root=root
    ) is False
    assert not (root.parent / "y.txt").exists()
