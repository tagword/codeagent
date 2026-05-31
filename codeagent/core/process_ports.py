"""Cross-platform helpers to find and stop processes listening on a TCP port."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from shutil import which
from typing import Callable, Optional, Set


def _win_no_window_kwargs() -> dict:
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    si.wShowWindow = 0
    return {"startupinfo": si, "creationflags": 0x08000000}


def pids_listening_on_port(port: int) -> Set[int]:
    """Return PIDs with a TCP listener on *port* (best effort)."""
    if os.name == "nt":
        return _pids_listening_on_port_windows(port)
    return _pids_listening_on_port_posix(port)


def kill_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        return _kill_pid_windows(pid)
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def force_kill_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == "nt":
        return _kill_pid_windows(pid)
    try:
        os.kill(pid, signal.SIGKILL)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def wait_port_released(port: int, timeout_sec: float) -> bool:
    deadline = time.time() + max(0.1, float(timeout_sec))
    while time.time() < deadline:
        if not pids_listening_on_port(port):
            return True
        time.sleep(0.15)
    return not pids_listening_on_port(port)


def stop_listeners_on_port(
    port: int,
    *,
    timeout_sec: float = 5.0,
    exclude_pid: Optional[int] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Set[int]:
    """
    SIGTERM listeners on *port*, wait for release, then SIGKILL stragglers.
    Returns PIDs that were targeted (excluding *exclude_pid*).
    """
    pids = pids_listening_on_port(port)
    if exclude_pid is not None:
        pids.discard(int(exclude_pid))
    if not pids:
        return set()

    def _say(msg: str) -> None:
        if log:
            log(msg)

    _say(f"Stopping listener(s) on port {port}: {sorted(pids)}")
    for pid in sorted(pids):
        kill_pid(pid)

    if wait_port_released(port, timeout_sec):
        return pids

    remaining = pids_listening_on_port(port)
    if exclude_pid is not None:
        remaining.discard(int(exclude_pid))
    for pid in sorted(remaining):
        _say(f"Force-stopping pid {pid} on port {port}")
        force_kill_pid(pid)
    wait_port_released(port, min(2.0, timeout_sec))
    return pids


def _pids_listening_on_port_windows(port: int) -> Set[int]:
    try:
        cp = subprocess.run(
            ["netstat", "-ano"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_win_no_window_kwargs(),
        )
    except Exception:
        return set()
    pids: Set[int] = set()
    needle = f":{int(port)}"
    for line in (cp.stdout or "").splitlines():
        line = line.strip()
        if not line or "LISTENING" not in line.upper() or needle not in line:
            continue
        parts = line.split()
        try:
            pid = int(parts[-1])
        except (ValueError, IndexError):
            continue
        if pid > 0:
            pids.add(pid)
    return pids


def _kill_pid_windows(pid: int) -> bool:
    try:
        cp = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_win_no_window_kwargs(),
        )
        return cp.returncode == 0
    except Exception:
        return False


def _pids_listening_on_port_posix(port: int) -> Set[int]:
    p = int(port)
    pids = _pids_via_lsof(p)
    if pids:
        return {x for x in pids if _pid_listens_on_port(x, p)}
    pids = _pids_via_ss(p)
    if pids:
        return pids
    return _pids_via_fuser(p)


def _pids_via_lsof(port: int) -> Set[int]:
    if not which("lsof"):
        return set()
    try:
        cp = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return set()
    out: Set[int] = set()
    for line in (cp.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.add(int(line))
        except ValueError:
            continue
    return out


_SS_PID_RE = re.compile(r"pid=(\d+)", re.I)


def _pids_via_ss(port: int) -> Set[int]:
    if not which("ss"):
        return set()
    try:
        cp = subprocess.run(
            ["ss", "-lptn", f"sport = :{port}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return set()
    pids: Set[int] = set()
    for line in (cp.stdout or "").splitlines():
        for m in _SS_PID_RE.finditer(line):
            try:
                pids.add(int(m.group(1)))
            except ValueError:
                continue
    return pids


def _pids_via_fuser(port: int) -> Set[int]:
    if not which("fuser"):
        return set()
    try:
        cp = subprocess.run(
            ["fuser", "-n", "tcp", str(port)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return set()
    pids: Set[int] = set()
    spec = f"{port}/tcp"
    for part in (cp.stdout or "").split():
        part = part.strip()
        if part.endswith(spec):
            part = part[: -len(spec)]
        part = part.rstrip(":").strip()
        if not part:
            continue
        try:
            pids.add(int(part))
        except ValueError:
            continue
    return pids


def _pid_listens_on_port(pid: int, port: int) -> bool:
    if not which("lsof"):
        return True
    try:
        cp = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-a", "-p", str(pid), "-t"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return True
    return bool((cp.stdout or "").strip())
