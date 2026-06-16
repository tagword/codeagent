"""Tests for external persona loading (W2: CODEAGENT_PERSONA_PATH)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# ─── Helpers ────────────────────────────────────────────────


def _mkdir_p(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(path: Path, text: str = "") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _setup_fake_repo(tmp_path: Path, persona_version: str = "1.0") -> Path:
    """Create a minimal external persona repo at ``tmp_path/repo``."""
    repo = _mkdir_p(tmp_path / "repo")
    _write(repo / "VERSION", persona_version)
    compat = {
        "persona_version": persona_version,
        "compat": [
            {"codeagent": ">=1.0,<2.0", "persona": "1.x", "note": "test compat"},
        ],
        "schema_version": "1.0",
    }
    _write(repo / "codeagent-compat.json", json.dumps(compat))
    persona_dir = _mkdir_p(repo / "persona")
    for fname in ("agent.md", "identity.md", "soul.md", "tools.md", "skills.md", "user.md"):
        _write(persona_dir / fname, f"# {fname} - from external repo\n")
    return repo


def _setup_dest(persona_dir: Path) -> None:
    """Ensure persona destination dir exists (mimics ``ensure_agent_dirs``)."""
    _mkdir_p(persona_dir)


def _import_paths() -> tuple:
    """Import ``paths`` module fresh (clears cached state)."""
    import importlib

    from codeagent.core import paths

    importlib.reload(paths)
    return paths


# ─── Tests: _ver_in_range, _ver_matches_pattern ──────────────


class TestVersionUtils:
    """Unit tests for version helper functions."""

    def test_ver_in_range_basic(self):
        paths = _import_paths()
        assert paths._ver_in_range("1.0.0", ">=1.0,<2.0") is True
        assert paths._ver_in_range("1.5.0", ">=1.0,<2.0") is True
        assert paths._ver_in_range("2.0.0", ">=1.0,<2.0") is False
        assert paths._ver_in_range("0.9.0", ">=1.0,<2.0") is False

    def test_ver_in_range_eq(self):
        paths = _import_paths()
        assert paths._ver_in_range("1.1.0", "==1.1.0") is True
        assert paths._ver_in_range("1.1.1", "==1.1.0") is False

    def test_ver_in_range_permissive(self):
        """Non-parseable versions should be permissive (return True)."""
        paths = _import_paths()
        assert paths._ver_in_range("dev", ">=1.0") is True
        assert paths._ver_in_range("", "") is True

    def test_ver_matches_pattern_x(self):
        paths = _import_paths()
        assert paths._ver_matches_pattern("1.0", "1.x") is True
        assert paths._ver_matches_pattern("1.9", "1.x") is True
        assert paths._ver_matches_pattern("2.0", "1.x") is False
        assert paths._ver_matches_pattern("1.0.0", "1.x") is True

    def test_ver_matches_pattern_star(self):
        paths = _import_paths()
        assert paths._ver_matches_pattern("anything", "*") is True

    def test_ver_matches_pattern_exact(self):
        paths = _import_paths()
        assert paths._ver_matches_pattern("1.0", "1.0") is True
        assert paths._ver_matches_pattern("1.1", "1.0") is False


# ─── Integration: _load_persona_from_external ───────────────


class TestExternalPersonaLoading:
    """Integration tests for external persona loading."""

    def test_no_env_var_falls_back(self):
        """No CODEAGENT_PERSONA_PATH → returns False (fallback to inline)."""
        os.environ.pop("CODEAGENT_PERSONA_PATH", None)
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "persona"
            _setup_dest(dest)
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)
            assert result is False

    def test_invalid_path_falls_back(self):
        """CODEAGENT_PERSONA_PATH pointing to non-existent dir → returns False."""
        os.environ["CODEAGENT_PERSONA_PATH"] = "/nonexistent/path"
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "persona"
            _setup_dest(dest)
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)
            assert result is False

    def test_valid_repo_loads(self):
        """Valid repo + compatible version → copies files and returns True."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = _setup_fake_repo(tmp)
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)

            assert result is True
            # Check all 6 files were copied
            for fname in ("agent.md", "identity.md", "soul.md", "tools.md", "skills.md", "user.md"):
                f = dest / fname
                assert f.is_file(), f"{fname} should exist"
                content = f.read_text(encoding="utf-8")
                assert "from external repo" in content

    def test_existing_files_not_overwritten(self):
        """Destination files that already exist should not be overwritten."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = _setup_fake_repo(tmp)
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            # Pre-create agent.md with custom content
            _write(dest / "agent.md", "# Custom user content\n")

            paths = _import_paths()
            result = paths._load_persona_from_external(dest)

            # Should report True (some files were copied)
            assert result is True
            # agent.md should NOT have been overwritten
            assert dest.joinpath("agent.md").read_text(encoding="utf-8") == "# Custom user content\n"

    def test_incompatible_version_falls_back(self):
        """Repo with incompatible version → returns False."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Setup repo with version 3.0 (not in compat matrix)
            repo = _setup_fake_repo(tmp, persona_version="3.0")
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)

            assert result is False

    def test_missing_persona_dir_falls_back(self):
        """Valid repo but missing ``persona/`` subdir → returns False."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = _mkdir_p(tmp / "repo")
            _write(repo / "VERSION", "1.0")
            _write(repo / "codeagent-compat.json", json.dumps({
                "persona_version": "1.0",
                "compat": [{"codeagent": ">=1.0,<2.0", "persona": "1.x", "note": ""}],
            }))
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)

            assert result is False

    def test_missing_compat_file_falls_back(self):
        """Valid repo but missing codeagent-compat.json → returns False."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = _mkdir_p(tmp / "repo")
            _write(repo / "VERSION", "1.0")
            _mkdir_p(repo / "persona")
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            paths = _import_paths()
            result = paths._load_persona_from_external(dest)

            assert result is False


# ─── Integration: _ensure_default_persona_files ─────────────


class TestEnsurePersonaFiles:
    """Integration tests for ``_ensure_default_persona_files`` priority."""

    def test_inline_fallback_when_no_env(self):
        """No env var → inline defaults are written."""
        os.environ.pop("CODEAGENT_PERSONA_PATH", None)
        with tempfile.TemporaryDirectory() as td:
            dest = _mkdir_p(Path(td) / "persona")
            paths = _import_paths()
            paths._ensure_default_persona_files(dest)

            for fname in ("agent.md", "identity.md", "soul.md", "tools.md", "skills.md", "user.md"):
                f = dest / fname
                assert f.is_file(), f"{fname} should exist"
                content = f.read_text(encoding="utf-8")
                assert len(content) > 50, f"{fname} too short: {len(content)}"

    def test_persona_repo_priority(self):
        """External repo takes priority over inline defaults."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = _setup_fake_repo(tmp)
            os.environ["CODEAGENT_PERSONA_PATH"] = str(repo)

            dest = _mkdir_p(tmp / "dest" / "persona")
            paths = _import_paths()
            paths._ensure_default_persona_files(dest)

            for fname in ("agent.md", "identity.md", "soul.md", "tools.md", "skills.md", "user.md"):
                f = dest / fname
                assert f.is_file()
                content = f.read_text(encoding="utf-8")
                assert "from external repo" in content, (
                    f"{fname} should come from external repo, got: {content[:80]}"
                )
