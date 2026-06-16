from __future__ import annotations

import time

from codeagent.server import self_healing


def test_is_enabled_tracks_env(monkeypatch) -> None:
    monkeypatch.setenv("CODEAGENT_SELF_HEALING_ENABLED", "0")
    assert self_healing.is_enabled() is False
    monkeypatch.setenv("CODEAGENT_SELF_HEALING_ENABLED", "1")
    assert self_healing.is_enabled() is True


def test_check_health_tolerates_bad_timeout_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(self_healing, "codeagent_home", lambda: tmp_path)
    monkeypatch.setenv("CODEAGENT_HEARTBEAT_TIMEOUT", "not-an-int")
    hb = tmp_path / "heartbeat"
    hb.write_text(str(time.time() - 20), encoding="utf-8")

    health = self_healing.check_health()
    assert health["timeout"] == 180
    assert health["status"] == "alive"


def test_watchdog_interval_is_clamped(monkeypatch) -> None:
    monkeypatch.setenv("CODEAGENT_WATCHDOG_INTERVAL", "99999")
    assert self_healing.watchdog_interval() == 600
    monkeypatch.setenv("CODEAGENT_WATCHDOG_INTERVAL", "-5")
    assert self_healing.watchdog_interval() == 1
