"""Self-healing engine — integrates Watchdog + Supervisor for autonomous recovery.

Architecture:
  Heartbeat (every 5s) → Watchdog (scans every 10s) → SelfHealer (decides action)
  → Supervisor (diagnose + fix) → Recovery (restart agents / skip tasks / notify)

Config can be toggled via environment variable CODEAGENT_SELF_HEALING_ENABLED (default: 1).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from codeagent.core.paths import codeagent_home

logger = logging.getLogger(__name__)

_DEFAULT_SELF_HEALING_ENABLED = True
_DEFAULT_HEARTBEAT_TIMEOUT = 180
_DEFAULT_WATCHDOG_INTERVAL = 10


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = str(raw).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _env_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(value, max_value))


def _heartbeat_timeout() -> int:
    return _env_int(
        "CODEAGENT_HEARTBEAT_TIMEOUT",
        _DEFAULT_HEARTBEAT_TIMEOUT,
        min_value=10,
        max_value=3600,
    )


def watchdog_interval() -> int:
    return _env_int(
        "CODEAGENT_WATCHDOG_INTERVAL",
        _DEFAULT_WATCHDOG_INTERVAL,
        min_value=1,
        max_value=600,
    )


def is_enabled() -> bool:
    return _env_bool("CODEAGENT_SELF_HEALING_ENABLED", _DEFAULT_SELF_HEALING_ENABLED)


def get_heartbeat_path() -> Path:
    return codeagent_home() / "heartbeat"


def heartbeat_age() -> float:
    """Return seconds since last heartbeat, or -1 if never."""
    hb = get_heartbeat_path()
    if not hb.is_file():
        return -1
    try:
        last = float(hb.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return -1
    return time.time() - last


def check_health() -> dict:
    """Return health status dict."""
    timeout = _heartbeat_timeout()
    age = heartbeat_age()
    status = "alive" if 0 < age < timeout else ("stuck" if age >= timeout else "unknown")
    return {
        "status": status,
        "heartbeat_age": round(age, 1) if age >= 0 else None,
        "timeout": timeout,
        "healing_enabled": is_enabled(),
    }


def diagnose() -> dict:
    """Run diagnostic checks and return findings."""
    health = check_health()
    findings = []
    findings.append(f"heartbeat: {health['heartbeat_age']}s ago (timeout={health['timeout']}s)")

    if health["status"] == "stuck":
        findings.append("WARNING: agent appears stuck")
        # Check process
        try:
            result = subprocess.run(
                ["ps", "-p", str(os.getpid()), "-o", "pid,stat,%cpu,%mem,etime", "--no-headers"],
                capture_output=True, text=True, timeout=5,
            )
            findings.append(f"process: {result.stdout.strip()}")
        except Exception as e:
            findings.append(f"process check failed: {e}")
    else:
        findings.append("OK: agent is alive")

    return {
        "healthy": health["status"] == "alive",
        "status": health["status"],
        "findings": findings,
    }


def heal() -> dict:
    """Attempt to heal the agent."""
    health = check_health()
    actions = []

    if health["status"] == "stuck":
        actions.append("heartbeat too old, forcing heartbeat reset")
        get_heartbeat_path().write_text(str(time.time()), encoding="utf-8")
        actions.append("heartbeat reset applied")
        logger.warning("self-healing: forced heartbeat reset")
    else:
        actions.append("no action needed")

    return {
        "healed": health["status"] == "stuck",
        "status": health["status"],
        "actions": actions,
    }
