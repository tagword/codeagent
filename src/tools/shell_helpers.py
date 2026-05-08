"""Shell execution helpers"""
import os
import re
import shutil
import subprocess
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_ANOMALY_LINE_RE = re.compile(
    r"\[0x[0-9A-Fa-f]+\]\s+ANOMALY:[^\r\n]*(?:\r?\n)?",
)

def _filter_shell_noise(text: str) -> str:
    if not text:
        return text
    cleaned = _ANOMALY_LINE_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


# On Windows `cmd.exe`, `cd C:\path` does NOT cross drives unless `/D` is given,
# which silently leaves the working directory on the previous drive.  Agents
# routinely write `cd <abs_path> && <cmd>`, so we auto-rewrite into `cd /D ...`.
_CMD_CD_RE = re.compile(
    r'(?<![A-Za-z_])cd\s+(?!/[Dd]\b)'          # bare `cd ` not already followed by /D
    r'(?P<path>"[^"\r\n]+"|[A-Za-z]:[^\s&|<>\r\n]*)',
    re.IGNORECASE,
)


def _autofix_cd_for_cmd(command: str) -> str:
    def _rep(m: "re.Match[str]") -> str:
        path = m.group("path")
        return f"cd /D {path}"
    return _CMD_CD_RE.sub(_rep, command)


def _pwsh_path() -> Optional[str]:
    """PowerShell 7+ (pwsh.exe) if installed; it supports && and cross-drive cd."""
    if os.name != "nt":
        return None
    cached = getattr(_pwsh_path, "_cache", "__unset__")
    if cached != "__unset__":
        return cached  # type: ignore[return-value]
    found = shutil.which("pwsh") or shutil.which("pwsh.exe")
    _pwsh_path._cache = found  # type: ignore[attr-defined]
    return found


def _prepare_shell_invocation(command: str) -> Tuple[Any, bool]:
    """
    Produce (popen_arg, shell_flag) that runs *command* correctly per OS.

    Windows:
      * Prefer `pwsh` (PowerShell 7+): native `&&`, cross-drive `cd`.
      * Fallback to `cmd.exe` but rewrite `cd <abs>` → `cd /D <abs>` so bare
        drive-letter jumps actually take effect.
    POSIX: straight `shell=True` with /bin/sh.
    """
    if os.name == "nt":
        pwsh = _pwsh_path()
        if pwsh:
            return ([pwsh, "-NoLogo", "-NoProfile", "-Command", command], False)
        return (_autofix_cd_for_cmd(command), True)
    return (command, True)


def _windows_no_window_kwargs() -> Dict[str, Any]:
    """Popen kwargs that suppress the black console window on Windows.

    Needed because:
      * ``CodeAgentTray.exe`` is a windowed (no-console) host, so any console
        child (``cmd.exe``, ``pwsh.exe``, ``node.exe``, ``python.exe`` ...) will
        **allocate its own new console window** unless we say otherwise.
      * ``DETACHED_PROCESS`` alone does *not* prevent this: it only severs the
        parent console link, the child is still free to pop its own.

    The standard "truly silent background" recipe is:
      - ``CREATE_NO_WINDOW`` (0x08000000): the child is a console app but we
        tell Windows not to allocate/show a console for it.
      - ``STARTUPINFO(SW_HIDE)``: belt-and-braces hide flag that also
        propagates if the child internally calls ``CreateProcess`` again
        (e.g. ``cmd /C npx serve`` spawning ``node``).
    """
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    si.wShowWindow = 0  # SW_HIDE
    return {
        "startupinfo": si,
        "creationflags": 0x08000000,  # CREATE_NO_WINDOW
    }


def _detach_popen_kwargs() -> Dict[str, Any]:
    """Platform-specific kwargs to truly detach a background subprocess.

    Combines the no-window flags above with flags that make the child outlive
    the parent tool call:
      * Windows: ``CREATE_NEW_PROCESS_GROUP`` lets the child have its own
        Ctrl-C group (parent Ctrl-C won't kill it); combined with
        ``CREATE_NO_WINDOW`` this produces a silent true-background process.
      * POSIX: ``start_new_session=True`` detaches the child from the parent's
        session/terminal.
    """
    kwargs: Dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        nw = _windows_no_window_kwargs()
        kwargs["startupinfo"] = nw["startupinfo"]
        # CREATE_NO_WINDOW (0x08000000) | CREATE_NEW_PROCESS_GROUP (0x00000200).
        # We deliberately do *not* set DETACHED_PROCESS: it is mutually
        # exclusive with CREATE_NEW_CONSOLE paths some interpreters take and
        # can cause `AllocConsole` warnings for child-of-child spawns.
        kwargs["creationflags"] = 0x08000000 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _active_agent_and_session() -> Tuple[str, str]:
    """
    Return (agent_id, session_id) best-effort from the current worker thread context.
    server.py sets active_llm_session to "<agent_id>::<session_id>".
    """
    try:
        from src.agent_context import get_active_llm_session

        raw = (get_active_llm_session() or "").strip()
        if "::" in raw:
            a, s = raw.split("::", 1)
            a = (a or "").strip() or "default"
            s = (s or "").strip() or "session"
            return a, s
        return "default", raw or "session"
    except Exception:
        return "default", "session"



