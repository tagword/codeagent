"""Tests for folder picker helpers."""

from __future__ import annotations

import os
import sys

from codeagent.core.folder_picker import has_graphical_session, pick_directory_sync


def test_has_graphical_session_windows() -> None:
    if sys.platform == "win32":
        assert has_graphical_session() is True


def test_has_graphical_session_linux_no_display(monkeypatch) -> None:
    if not sys.platform.startswith("linux"):
        return
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert has_graphical_session() is False


def test_pick_linux_headless_returns_hint(monkeypatch) -> None:
    if not sys.platform.startswith("linux"):
        return
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    path, skipped, hint = pick_directory_sync()
    assert path == ""
    assert skipped is True
    assert "DISPLAY" in hint or "zenity" in hint
