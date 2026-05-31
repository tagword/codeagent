"""Native folder picker (macOS / Windows / Linux desktop)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


def has_graphical_session() -> bool:
    if sys.platform == "win32":
        return True
    if sys.platform == "darwin":
        return True
    return bool(
        os.environ.get("DISPLAY", "").strip()
        or os.environ.get("WAYLAND_DISPLAY", "").strip()
    )


def pick_directory_sync() -> Tuple[str, bool, str]:
    """
    Blocking folder picker.

    Returns ``(path, skipped, hint)``:
    - *path*: chosen directory or ``""``
    - *skipped*: env/disabled/no GUI tool
    - *hint*: user-facing reason when *path* is empty
    """
    if sys.platform == "darwin":
        return _pick_darwin()
    if sys.platform == "win32":
        return _pick_windows()
    return _pick_linux()


def _pick_darwin() -> Tuple[str, bool, str]:
    script = (
        'POSIX path of (choose folder with prompt '
        '"选择目录" default location (path to desktop folder))'
    )
    try:
        cp = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except FileNotFoundError:
        return "", True, "osascript not found"
    except subprocess.TimeoutExpired:
        return "", False, "folder picker timed out"
    cand = (cp.stdout or "").strip()
    if cand and Path(cand).is_dir():
        return cand, False, ""
    if cp.returncode != 0:
        return "", False, "folder picker cancelled"
    return "", False, ""


def _pick_windows() -> Tuple[str, bool, str]:
    ps = r"""
Add-Type -AssemblyName System.Windows.Forms
$top = New-Object System.Windows.Forms.Form
$top.TopMost = $true
$top.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
$top.ShowInTaskbar = $false
$top.Size = New-Object System.Drawing.Size(0, 0)
$top.StartPosition = "Manual"
$top.Location = New-Object System.Drawing.Point(-32000, -32000)
$null = $top.Show()
[System.Windows.Forms.Application]::DoEvents()
try {
  $d = New-Object System.Windows.Forms.FolderBrowserDialog
  $d.Description = "选择项目目录"
  $d.ShowNewFolderButton = $true
  if ($d.ShowDialog($top) -eq "OK") { Write-Output $d.SelectedPath }
} finally { $top.Close(); $top.Dispose() }
"""
    for exe in ("powershell", "pwsh"):
        if not _which(exe):
            continue
        try:
            cp = subprocess.run(
                [exe, "-NoProfile", "-Command", ps],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "", False, "folder picker timed out"
        cand = (cp.stdout or "").strip()
        if cand and Path(cand).is_dir():
            return cand, False, ""
    return "", True, "PowerShell not found for folder picker"


def _pick_linux() -> Tuple[str, bool, str]:
    if not has_graphical_session():
        return (
            "",
            True,
            "no DISPLAY/WAYLAND_DISPLAY; set project path manually or install zenity on a desktop session",
        )

    tools = (
        (["zenity", "--file-selection", "--directory"], "zenity"),
        (["kdialog", "--getexistingdirectory"], "kdialog"),
        (["yad", "--file", "--directory"], "yad"),
    )
    missing: list[str] = []
    for cmd, name in tools:
        if not _which(cmd[0]):
            missing.append(name)
            continue
        try:
            cp = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "", False, "folder picker timed out"
        cand = (cp.stdout or "").strip()
        if cand and Path(cand).is_dir():
            return cand, False, ""
        if cp.returncode != 0 and cp.returncode != 1:
            continue
    hint = (
        "install zenity, kdialog, or yad for GUI folder selection "
        f"(missing: {', '.join(missing) or 'unknown'})"
    )
    return "", True, hint


def _which(name: str) -> Optional[str]:
    from shutil import which as _w

    return _w(name)
