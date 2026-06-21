"""Tests for bundled default persona initialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from codeagent.core.paths import (
    _PERSONA_INIT_FILENAMES,
    _bundled_persona_defaults_dir,
    _ensure_default_persona_files,
    _read_bundled_persona_file,
)


def test_bundled_persona_defaults_present() -> None:
    bundled = _bundled_persona_defaults_dir()
    assert bundled is not None
    for fname in _PERSONA_INIT_FILENAMES:
        text = _read_bundled_persona_file(fname)
        assert text and text.strip(), f"missing or empty bundled persona: {fname}"


def test_ensure_default_persona_files_copies_bundle(tmp_path: Path) -> None:
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    _ensure_default_persona_files(persona_dir)
    for fname in _PERSONA_INIT_FILENAMES:
        p = persona_dir / fname
        assert p.is_file(), fname
        assert p.read_text(encoding="utf-8") == _read_bundled_persona_file(fname)


def test_ensure_default_persona_files_does_not_overwrite(tmp_path: Path) -> None:
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    custom = "# Custom agent\n"
    (persona_dir / "agent.md").write_text(custom, encoding="utf-8")
    _ensure_default_persona_files(persona_dir)
    assert (persona_dir / "agent.md").read_text(encoding="utf-8") == custom
    assert (persona_dir / "memory.md").is_file()
