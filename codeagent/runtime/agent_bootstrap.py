"""Register on-disk agents into seed's ``AgentRegistry`` at server boot.

Without this, the chat team tools (``call_agent`` / ``dispatch`` / ``parallel``)
always fail with ``"Agent '<id>' not found in registry"`` because nothing ever
populates the registry.

Design notes
------------
* **Idempotent**: safe to call repeatedly (e.g. after creating a new agent).
* **Cheap**: registering only stores lightweight ``LLMWorkerHandle`` objects;
  no LLM call, no session load happens until a handle is actually invoked.
* **Best-effort**: a broken agent dir is skipped with a warning, never fatal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Agents that exist on disk but should not be callable via chat team tools.
_SKIP_IDS = frozenset({"testagent"})


def _has_persona_files(agent_dir: Path) -> bool:
    """True when ``persona/`` holds at least one **non-empty** ``*.md`` file.

    Neither a bare ``persona/`` directory nor a 0-byte placeholder counts: an
    agent whose persona was never materialised behaves like a blank default and
    must not be advertised to the LLM via ``list_agents`` (it would be "visible
    but not callable").
    """
    pdir = agent_dir / "persona"
    if not pdir.is_dir():
        return False
    try:
        for p in pdir.glob("*.md"):
            if p.is_file() and p.stat().st_size > 0:
                return True
    except OSError:
        return False
    return False


def _discover_agent_ids() -> list[str]:
    """Return agent ids that are genuinely usable on disk.

    Qualification requires a ``persona/`` directory **containing at least one
    ``*.md`` file** — hollow agents (empty persona dir) are excluded so that
    ``list_agents`` never advertises an agent the LLM cannot meaningfully call.
    """
    from codeagent.server.webui_handlers_agentmeta import _agents_dir

    ad = _agents_dir()
    if not ad.is_dir():
        return []
    ids: list[str] = []
    for entry in sorted(ad.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_IDS:
            continue
        if not _has_persona_files(entry):
            continue
        ids.append(entry.name)
    return ids


def register_disk_agents(
    *,
    agent_ids: list[str] | None = None,
    project_id: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Populate ``AgentRegistry`` with handles for on-disk agents.

    Args:
        agent_ids: Explicit ids to register. When ``None``, all discoverable
            on-disk agents are used.
        project_id: Optional project scope forwarded to each worker.
        overwrite: When ``False`` (default) existing registrations are kept,
            making repeated calls idempotent.

    Returns:
        ``{"registered": [...], "skipped": [...], "total": int}``
    """
    from codeagent.runtime.agent_handle import LLMWorkerHandle
    from seed.core.agent_registry import AgentHandle, AgentRegistry

    ids = agent_ids if agent_ids is not None else _discover_agent_ids()
    registered: list[str] = []
    skipped: list[str] = []

    for aid in ids:
        if not aid:
            continue
        if not overwrite and AgentRegistry.get(aid) is not None:
            skipped.append(aid)
            continue
        try:
            handle = AgentHandle(
                agent=LLMWorkerHandle(agent_id=aid, project_id=project_id),
                metadata={"source": "disk-bootstrap", "agent_id": aid},
            )
            AgentRegistry.register(aid, handle)
            registered.append(aid)
        except Exception:  # noqa: BLE001 — one bad agent must not break boot
            logger.warning("Failed to register agent '%s'", aid, exc_info=True)
            skipped.append(aid)

    if registered:
        logger.info("Registered %d agent(s) into AgentRegistry: %s", len(registered), registered)
    return {"registered": registered, "skipped": skipped, "total": len(registered)}
