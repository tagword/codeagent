"""chat --project-id：CLI 派发任务的 Web UI 项目归属。

背景（真实需求）：
  RSI 通过 CLI 派发任务给副本 agent，希望任务在 Web UI 里归入对应项目
  （而非全部堆在"未分类"），以便按项目跟进进度。

缺陷：
  ``chat`` 子命令此前没有 ``--project-id``，且 ``_cmd_chat_llm`` 里
  ``finalize_episodic_for_llm(project_id=None)`` 硬编码为 None，
  导致 CLI 派发的会话永远注册到 ``__unassigned__``。

修复：
  - ``chat`` 新增 ``--project-id``
  - 传给 ``load_or_create_chat_session(project_id=...)`` 与
    ``finalize_episodic_for_llm(project_id=...)``
"""

from __future__ import annotations

import subprocess
import sys


def _chat_help() -> str:
    out = subprocess.run(
        [sys.executable, "-m", "codeagent", "chat", "--help"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    return (out.stdout or "") + (out.stderr or "")


def test_chat_help_mentions_project_id():
    """chat 子命令必须暴露 --project-id（否则 CLI 无法指定项目归属）。"""
    assert "--project-id" in _chat_help()


def test_chat_help_documents_project_grouping():
    """帮助文本应说明用途（归入 Web UI 项目视图），而非只有参数名。"""
    text = _chat_help()
    assert "project" in text.lower()


def test_load_or_create_chat_session_persists_project_id(tmp_path, monkeypatch):
    """核心契约：传入 project_id 时，会话 metadata 必须带上它。

    这是 Web UI 按项目分组的前提。
    """
    from seed.core import llm_sess

    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SEED_AGENT_ID", "default")

    sess = llm_sess.load_or_create_chat_session("proj-sess", "default", project_id="proj123")
    assert isinstance(sess.metadata, dict)
    assert sess.metadata.get("project_id") == "proj123"


def test_load_or_create_chat_session_without_project_id(tmp_path, monkeypatch):
    """不传 project_id 时不应凭空写入（保持未分类语义）。"""
    from seed.core import llm_sess

    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SEED_AGENT_ID", "default")

    sess = llm_sess.load_or_create_chat_session("no-proj-sess", "default")
    md = sess.metadata if isinstance(sess.metadata, dict) else {}
    assert not md.get("project_id")


def test_existing_session_project_id_is_updated(tmp_path, monkeypatch):
    """已存在的会话被指定新 project_id 时应更新（支持重新归属）。"""
    from seed.core import llm_sess

    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SEED_AGENT_ID", "default")

    first = llm_sess.load_or_create_chat_session("reassign-sess", "default", project_id="p1")
    assert first.metadata.get("project_id") == "p1"

    again = llm_sess.load_or_create_chat_session("reassign-sess", "default", project_id="p2")
    assert again.metadata.get("project_id") == "p2"
