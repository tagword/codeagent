"""Tests for cross-platform port listener helpers."""

from __future__ import annotations

import os

import pytest

from codeagent.core.process_ports import pids_listening_on_port


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only test")
def test_pids_listening_on_port_localhost_service() -> None:
    """Port 1 (tcpmux) is unlikely to have a listener in CI; returns a set without error."""
    pids = pids_listening_on_port(1)
    assert isinstance(pids, set)


def test_pids_listening_on_port_invalid_high_port() -> None:
    pids = pids_listening_on_port(59999)
    assert isinstance(pids, set)
