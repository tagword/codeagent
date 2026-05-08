"""Daily diary for agents: keep 7 days, archive older.

Layout:
  agents/<agent_id>/memory/daily/YYYY-MM-DD.md
  agents/<agent_id>/memory/archive/YYYY-MM-DD.md
  agents/<agent_id>/memory/projects/<slug>/daily|archive/  (when project_id set)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from src.codeagent_paths_pkg import (
    agent_archive_dir,
    agent_daily_dir,
    agent_memory_dir,
    agent_project_daily_dir,
)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _fmt_day(d: date) -> str:
    return d.isoformat()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def daily_path(
    agent_id: str, *, day: Optional[date] = None, project_id: Optional[str] = None
) -> Path:
    day = day or _today_utc()
    if project_id and str(project_id).strip():
        return agent_project_daily_dir(agent_id, project_id) / f"{_fmt_day(day)}.md"
    return agent_daily_dir(agent_id) / f"{_fmt_day(day)}.md"


def ensure_today_diary(
    agent_id: str, *, day: Optional[date] = None, project_id: Optional[str] = None
) -> Path:
    day = day or _today_utc()
    p = daily_path(agent_id, day=day, project_id=project_id)
    _ensure_dir(p.parent)
    if p.is_file():
        return p
    header = (
        f"# 日记 {day.isoformat()}\n\n"
        "- 今日主题：\n"
        "- 今日进展：\n"
        "- 学到什么：\n"
        "- 待办：\n\n"
        "---\n\n"
    )
    p.write_text(header, encoding="utf-8")
    return p


def append_diary_entry(
    agent_id: str,
    *,
    text: str,
    day: Optional[date] = None,
    project_id: Optional[str] = None,
) -> Path:
    day = day or _today_utc()
    p = ensure_today_diary(agent_id, day=day, project_id=project_id)
    t = (text or "").strip()
    if not t:
        return p
    ts = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
    block = f"## {ts}\n\n{t}\n\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(block)
    return p


@dataclass
class ArchiveResult:
    moved: int = 0
    kept: int = 0


def _archive_daily_dir(
    ddir: Path, adir: Path, *, keep_days: int, now: date
) -> ArchiveResult:
    if not ddir.is_dir():
        return ArchiveResult(moved=0, kept=0)
    keep_days = max(1, min(int(keep_days), 60))
    cutoff = now - timedelta(days=keep_days - 1)
    _ensure_dir(adir)
    moved = 0
    kept = 0
    for p in sorted(ddir.glob("*.md")):
        stem = p.stem
        if not _DATE_RE.match(stem):
            continue
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if d < cutoff:
            dest = adir / p.name
            try:
                if dest.is_file():
                    dest.unlink()
                p.replace(dest)
                moved += 1
            except OSError:
                continue
        else:
            kept += 1
    return ArchiveResult(moved=moved, kept=kept)


def archive_old_diaries(agent_id: str, *, keep_days: int = 7, now: Optional[date] = None) -> ArchiveResult:
    keep_days = int(keep_days)
    now = now or _today_utc()
    acc = ArchiveResult(moved=0, kept=0)
    r0 = _archive_daily_dir(
        agent_daily_dir(agent_id), agent_archive_dir(agent_id), keep_days=keep_days, now=now
    )
    acc.moved += r0.moved
    acc.kept += r0.kept
    proj_root = agent_memory_dir(agent_id) / "projects"
    if proj_root.is_dir():
        for sub in sorted(proj_root.iterdir()):
            if not sub.is_dir():
                continue
            pdaily = sub / "daily"
            parch = sub / "archive"
            if pdaily.is_dir():
                r1 = _archive_daily_dir(pdaily, parch, keep_days=keep_days, now=now)
                acc.moved += r1.moved
                acc.kept += r1.kept
    return acc
