"""packaging/prepare_bundle_tools.py 的本地二进制复用逻辑。

背景：Windows CI 曾因从 GitHub Releases 下载 15MB ast-grep zip（实测 ~100KB/s）
把 Stage 步骤拖到 20 分钟以上。改为 ``pip install ast-grep-cli`` 预装 +
prefer_local=True 复用本地二进制。这里锁住该行为，避免以后被改回"先下载"。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "packaging" / "prepare_bundle_tools.py"


@pytest.fixture(scope="module")
def pbt():
    spec = importlib.util.spec_from_file_location("prepare_bundle_tools", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fake_binary(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"#!/bin/sh\necho 0.40.3\n")
    path.chmod(0o755)
    return path


def test_prefer_local_disabled_never_touches_network(pbt, tmp_path, monkeypatch):
    """macOS 分支：prefer_local=False 必须直接返回 False（不复制本地 brew 二进制）。"""
    src = _fake_binary(tmp_path / "ast-grep")
    monkeypatch.setattr(pbt, "_venv_bin", lambda name: src)
    dest = tmp_path / "out" / "ast-grep"

    assert pbt._prefer_local_ast_grep(dest, prefer_local=False) is False
    assert not dest.exists()


def test_prefer_local_copies_venv_binary(pbt, tmp_path, monkeypatch):
    """Windows 分支：venv 里装了 ast-grep-cli，直接复制，不下载。"""
    src = _fake_binary(tmp_path / "Scripts" / "ast-grep")
    monkeypatch.setattr(pbt, "_venv_bin", lambda name: src)
    monkeypatch.setattr(pbt.shutil, "which", lambda name: None)
    dest = tmp_path / "out" / "bin" / "ast-grep.exe"
    dest.parent.mkdir(parents=True)

    assert pbt._prefer_local_ast_grep(dest, prefer_local=True) is True
    assert dest.is_file()
    assert dest.read_bytes() == src.read_bytes()


def test_prefer_local_missing_binary_returns_false(pbt, tmp_path, monkeypatch):
    """本地没有 ast-grep 时必须回退到下载分支（返回 False，不抛异常）。"""
    monkeypatch.setattr(pbt, "_venv_bin", lambda name: None)
    monkeypatch.setattr(pbt.shutil, "which", lambda name: None)
    dest = tmp_path / "out" / "ast-grep"

    assert pbt._prefer_local_ast_grep(dest, prefer_local=True) is False
    assert not dest.exists()


def test_prefer_local_creates_sg_alias_on_windows(pbt, tmp_path, monkeypatch):
    """Windows 无 symlink 特权：复制出 sg.exe 别名。"""
    if sys.platform != "win32":
        pytest.skip("只在 Windows 上验证 sg.exe 别名")
    src = _fake_binary(tmp_path / "ast-grep.exe")
    monkeypatch.setattr(pbt, "_venv_bin", lambda name: src)
    dest = tmp_path / "out" / "bin" / "ast-grep.exe"
    dest.parent.mkdir(parents=True)

    assert pbt._prefer_local_ast_grep(dest, prefer_local=True) is True
    assert (dest.parent / "sg.exe").is_file()
