"""Inject searchable episodic snippets into the system prompt; strip/regenerate each turn."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_EPISODIC_START = "\n## CodeAgent episodic memory (recent)\n"
_EPISODIC_END = "\n## End CodeAgent episodic memory\n"

_EPISODIC_BLOCK = re.compile(
    r"\n## CodeAgent episodic memory \(recent\)\n.*?\n## End CodeAgent episodic memory\n",
    re.DOTALL,
)


# Match a ``## TTL`` section that gives a lifetime in seconds.
#   ## TTL
#   600
# Or on one line:
#   ## TTL: 600
_TTL_SECTION_RE = re.compile(
    r"^\s*##\s*TTL\s*[:：]?\s*(?P<inline>\d+)?\s*$(?:\r?\n\s*(?P<below>\d+)\s*$)?",
    re.IGNORECASE | re.MULTILINE,
)

# Match a ``## Expires`` section giving an absolute ISO-8601 timestamp.
#   ## Expires
#   2026-04-20T15:00:00Z
_EXPIRES_SECTION_RE = re.compile(
    r"^\s*##\s*Expires\s*[:：]?\s*(?P<inline>[0-9T:\-+Z \.]+)?\s*$"
    r"(?:\r?\n\s*(?P<below>[0-9T:\-+Z \.]+)\s*$)?",
    re.IGNORECASE | re.MULTILINE,
)


def strip_episodic_block(system_text: str) -> str:
    return _EPISODIC_BLOCK.sub("\n", system_text or "").strip()


def _parse_ttl_seconds(text: str) -> Optional[int]:
    m = _TTL_SECTION_RE.search(text or "")
    if not m:
        return None
    raw = (m.group("inline") or m.group("below") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
    except ValueError:
        return None
    return v if v > 0 else None


def _parse_expires_dt(text: str) -> Optional[datetime]:
    m = _EXPIRES_SECTION_RE.search(text or "")
    if not m:
        return None
    raw = (m.group("inline") or m.group("below") or "").strip()
    if not raw:
        return None
    # Accept trailing Z (Zulu) as UTC.
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_expired(path: Path, text: str, *, now: Optional[datetime] = None) -> bool:
    """
from __future__ import annotations

    True if this experience file carries a TTL / Expires marker and is past it.

    Supports two conventions (either may appear anywhere in the body):

        ## TTL
        600              # seconds after the file's mtime

        ## Expires
        2026-04-20T15:00:00Z
    """
    cur = now or datetime.now(timezone.utc)
    exp = _parse_expires_dt(text)
    if exp is not None:
        return cur >= exp
    ttl = _parse_ttl_seconds(text)
    if ttl is not None:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return False
        return cur >= mtime + timedelta(seconds=ttl)
    return False


def experience_file_expired(path: Path, text: str, *, now: Optional[datetime] = None) -> bool:
    """True if ``## TTL`` / ``## Expires`` in this experience markdown is past (same rules as episodic inject)."""
    return _is_expired(path, text, now=now)





import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.mem_sys_pkg import MemorySystem



def _td_seconds(seconds: int):
    # Imported lazily to avoid top-level import noise.
    from datetime import timedelta
    return timedelta(seconds=seconds)


def parsed_experience_project_id(text: str) -> Optional[str]:
    """Return canonical project id from ``## Project`` section, or None if absent."""
    m = re.search(r"(?im)^##\s*Project\s*\n\s*(\S+)", text or "")
    if not m:
        return None
    return (m.group(1) or "").strip() or None


def build_episodic_snippets(
    project_root: Path,
    *,
    session_id: str | None,
    max_chars: int,
    session_only: bool,
    project_id: str | None = None,
    project_scope: bool = False,
) -> str:
    """
    Recent experience files (newest first), optional filter by logged ## Session field.

    Files carrying an explicit ``## TTL`` (seconds from mtime) or ``## Expires``
    (absolute ISO-8601 timestamp) are **skipped once expired** so stale
    runtime facts (PID/port/"running" snapshots) stop being re-injected.
    """
    try:
        # If caller passes agents/<id>/memory, MemorySystem will use it directly.
        ms = MemorySystem(base_path=project_root.resolve())
    except Exception:
        return ""
    exp_dir = ms.memory_path / "experiences"
    if not exp_dir.is_dir():
        return ""

    files = sorted(exp_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    parts: List[str] = []
    total = 0
    now = datetime.now(timezone.utc)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_expired(f, text, now=now):
            continue
        if session_only and session_id:
            if "## session" in text.lower():
                if session_id not in text:
                    continue
        if project_scope:
            exp_proj = parsed_experience_project_id(text)
            want = (project_id or "").strip()
            if want:
                if exp_proj != want:
                    continue
            else:
                if exp_proj is not None:
                    continue
        snippet = text.strip()
        if len(snippet) > 900:
            snippet = snippet[:450] + "\n…\n" + snippet[-400:]
        chunk = f"### {f.name}\n{snippet}\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts).strip()


def apply_episodic_to_messages(
    messages: List[Dict[str, Any]],
    project_root: Path,
    session_id: str | None,
    *,
    project_id: Optional[str] = None,
    project_scope: bool = False,
) -> None:
    """Mutates messages[0] system content: refresh episodic block."""
    import os

    if not messages or messages[0].get("role") != "system":
        return
    if os.environ.get("CODEAGENT_MEMORY_INJECT", "1").lower() in ("0", "false", "no"):
        content = strip_episodic_block(str(messages[0].get("content") or ""))
        messages[0]["content"] = content
        return

    max_c = int(os.environ.get("CODEAGENT_MEMORY_INJECT_MAX_CHARS", "5000"))
    session_only = os.environ.get("CODEAGENT_MEMORY_INJECT_SESSION_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    block = build_episodic_snippets(
        project_root,
        session_id=session_id,
        max_chars=max_c,
        session_only=session_only,
        project_id=project_id,
        project_scope=project_scope,
    )
    base = strip_episodic_block(str(messages[0].get("content") or ""))
    if block:
        messages[0]["content"] = base + _EPISODIC_START + block + _EPISODIC_END
    else:
        messages[0]["content"] = base
