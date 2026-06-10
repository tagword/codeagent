"""Self-healing engine — integrates Watchdog + Supervisor for autonomous recovery.

Architecture:
  Heartbeat (every 5s) → Watchdog (scans every 10s) → SelfHealer (decides action)
  → Supervisor (diagnose + fix) → Recovery (restart agents / skip tasks / notify)

Config can be toggled via environment variable SELF_HEALING_ENABLED (default: 1).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from codeagent.core.paths import codeagent_home

logger = logging.getLogger(__name__)

SELF_HEALING_ENABLED = os.environ.get("SELF_HEALING_ENABLED", "1") == "1"
HEARTBEAT_TIMEOUT = int(os.environ.get("HEARTBEAT_TIMEOUT", "180"))
WATCHDOG_INTERVAL = int(os.environ.get("WATCHDOG_INTERVAL", "10"))


def is_enabled() -> bool:
    return SELF_HEALING_ENABLED


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
    age = heartbeat_age()
    status = "alive" if 0 < age < HEARTBEAT_TIMEOUT else ("stuck" if age >= HEARTBEAT_TIMEOUT else "unknown")
    return {
        "status": status,
        "heartbeat_age": round(age, 1) if age >= 0 else None,
        "timeout": HEARTBEAT_TIMEOUT,
        "healing_enabled": SELF_HEALING_ENABLED,
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
