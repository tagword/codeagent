"""Per-agent tools registry: innate + acquired.

This provides the mechanism requested:
- Every agent has an innate set of tools (stable, low-risk defaults).
- Every agent can have acquired tools (agent-specific allow/deny in agents/<id>/tools.json).

The returned registry is what gets exposed to the tool-loop (and what the executor can run).
Plugin toggles from ui_settings still apply on top
when rendering tools to the LLM, but we also allow hard removal per-agent here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass

from seed_tools import ToolExecutor, ToolRegistry, setup_builtin_tools

from codeagent.core.paths import agent_home


@dataclass
class ToolLayerRule:
    allow: set[str]
    deny: set[str]
    allow_prefixes: tuple[str, ...]
    deny_prefixes: tuple[str, ...]


def _as_set(xs: object) -> set[str]:
    if not isinstance(xs, list):
        return set()
    out: set[str] = set()
    for x in xs:
        if isinstance(x, str) and x.strip():
            out.add(x.strip())
    return out


def _as_prefixes(xs: object) -> tuple[str, ...]:
    if not isinstance(xs, list):
        return ()
    out = []
    for x in xs:
        if isinstance(x, str):
            s = x.strip()
            if s:
                out.append(s)
    return tuple(out)


def _load_tools_json(agent_id: str) -> dict[str, object]:
    p = agent_home(agent_id) / "tools.json"
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _layer_rule(raw: dict[str, object], key: str) -> ToolLayerRule:
    d = raw.get(key)
    if not isinstance(d, dict):
        d = {}
    return ToolLayerRule(
        allow=_as_set(d.get("allow")),
        deny=_as_set(d.get("deny")),
        allow_prefixes=_as_prefixes(d.get("allow_prefixes")),
        deny_prefixes=_as_prefixes(d.get("deny_prefixes")),
    )


def _match_prefix(name: str, prefixes: Iterable[str]) -> bool:
    return any(p and name.startswith(p) for p in prefixes)


# Default innate policy: keep things that are mostly read-only / low risk.
# Users can override via agents/<id>/tools.json if desired.
_INNATE_DENY_PREFIXES: tuple[str, ...] = ()
_INNATE_DENY_NAMES: set[str] = {
    # write/exec/high-risk by default
    "file_write",
    "file_edit",
    "bash_exec",
    "bash_tool",
    "notebook_edit_tool",
    "seed_cron_apply",
    "codeagent_cron_apply",  # legacy alias
}


def _default_innate_allowed(all_names: set[str]) -> set[str]:
    out: set[str] = set()
    for n in all_names:
        if n in _INNATE_DENY_NAMES:
            continue
        if _match_prefix(n, _INNATE_DENY_PREFIXES):
            continue
        out.add(n)
    return out


def _apply_rule(base: set[str], *, rule: ToolLayerRule, all_names: set[str]) -> set[str]:
    out = set(base)
    if rule.allow_prefixes:
        out |= {n for n in all_names if _match_prefix(n, rule.allow_prefixes)}
    if rule.allow:
        out |= {n for n in rule.allow if n in all_names}
    if rule.deny_prefixes:
        out -= {n for n in out if _match_prefix(n, rule.deny_prefixes)}
    if rule.deny:
        out -= {n for n in rule.deny}
    return out


_CACHE: dict[str, tuple[ToolRegistry, ToolExecutor]] = {}


def get_tools_for_agent(agent_id: str) -> tuple[ToolRegistry, ToolExecutor]:
    """
    Build or return cached (registry, executor) for an agent.

    Env:
      CODEAGENT_AGENT_TOOLS_NO_CACHE=1  -> disable cache (debug)
      CODEAGENT_AGENT_TOOLS_MODE=all    -> do not filter (everything allowed)
    """
    aid = (agent_id or "").strip() or "default"
    if os.environ.get("CODEAGENT_AGENT_TOOLS_NO_CACHE", "").lower() not in ("1", "true", "yes"):
        hit = _CACHE.get(aid)
        if hit is not None:
            return hit

    reg, ex = setup_builtin_tools()
    all_names = {t.name for t in reg.list_all()}
    mode = os.environ.get("CODEAGENT_AGENT_TOOLS_MODE", "").strip().lower()
    if mode == "all":
        out = (reg, ex)
        _CACHE[aid] = out
        return out

    raw = _load_tools_json(aid)
    innate_rule = _layer_rule(raw, "innate")
    acquired_rule = _layer_rule(raw, "acquired")

    innate = _apply_rule(_default_innate_allowed(all_names), rule=innate_rule, all_names=all_names)
    # Default acquired: everything not in innate.
    acquired = _apply_rule(set(all_names) - set(innate), rule=acquired_rule, all_names=all_names)
    allowed = set(innate) | set(acquired)

    for t in list(reg.list_all()):
        if t.name not in allowed:
            reg.unregister(t.name)

    out = (reg, ToolExecutor(reg))
    _CACHE[aid] = out
    return out


def reset_agent_tools_cache() -> None:
    _CACHE.clear()

