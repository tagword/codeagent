"""P1 回归测试：persona 初始化绝不留下空壳目录。

复现的真实缺陷：
  隔离环境（bundled 模板解析不到）下，`_ensure_default_persona_files`
  只 warning 就 return，目录建了但**一个文件都不写** → 产生空壳 agent
  （如 ag_09e0fc0a7e6f42cc）。

覆盖边界：normal（bundled 可用）/ fallback（bundled 缺失但有 default）/
         none（两源都缺 → 明确 error 而非静默）。
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from codeagent.core import paths


@pytest.fixture()
def persona_dir(tmp_path):
    d = tmp_path / "agent" / "persona"
    d.mkdir(parents=True)
    return d


def test_bundled_source_writes_files(persona_dir):
    """正常路径：bundled 模板可用 → 写出 persona 文件。"""
    with patch.object(
        paths, "_read_bundled_persona_file", return_value="# Identity\n"
    ):
        paths._ensure_default_persona_files(persona_dir)
    written = list(persona_dir.glob("*.md"))
    assert written, "bundled 可用时必须写出 persona 文件"


def test_fallback_to_default_agent_when_bundled_missing(persona_dir, tmp_path):
    """边界：bundled 缺失 → 回退复制 default agent 的 persona（核心反例）。"""
    default_persona = tmp_path / "agents" / "default" / "persona"
    default_persona.mkdir(parents=True)
    (default_persona / "identity.md").write_text("# Default Identity\n", encoding="utf-8")

    with (
        patch.object(paths, "_bundled_persona_defaults_dir", return_value=None),
        patch.object(paths, "_read_bundled_persona_file", return_value=None),
        patch.object(paths, "_fallback_persona_source_dir", return_value=default_persona),
    ):
        paths._ensure_default_persona_files(persona_dir)

    out = persona_dir / "identity.md"
    assert out.is_file(), "bundled 缺失时必须回退到 default persona，而非留空壳"
    assert "Default Identity" in out.read_text(encoding="utf-8")


def test_no_source_logs_error_not_silent(persona_dir, caplog):
    """边界：两源都缺 → 明确 error，绝不静默。"""
    with (
        patch.object(paths, "_bundled_persona_defaults_dir", return_value=None),
        patch.object(paths, "_fallback_persona_source_dir", return_value=None),
        caplog.at_level(logging.ERROR),
    ):
        paths._ensure_default_persona_files(persona_dir)

    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "两源都缺时必须记 error（旧实现只 warning，导致问题被忽略）"
    )
    assert not list(persona_dir.glob("*.md"))


def test_existing_files_not_overwritten(persona_dir):
    """幂等：已存在的 persona 文件不被覆盖。"""
    existing = persona_dir / "identity.md"
    existing.write_text("# Mine\n", encoding="utf-8")
    with patch.object(
        paths, "_read_bundled_persona_file", return_value="# Bundled\n"
    ):
        paths._ensure_default_persona_files(persona_dir)
    assert existing.read_text(encoding="utf-8") == "# Mine\n"
