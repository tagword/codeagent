"""Session-level token usage accumulation with per-model cost (billing v2)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from codeagent.core.pricing import calculate_cost

USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)


def _add_usage_keys(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in USAGE_KEYS:
        value = source.get(key, 0)
        if not isinstance(value, (int, float)):
            value = 0
        target[key] = int(target.get(key, 0) or 0) + int(value)


def merge_accumulated_usage(
    prev: Dict[str, Any] | None,
    model_name: str,
    api_usage: Dict[str, Any] | None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Merge one LLM round into session ``accumulated_usage``.

    Returns:
        ``(accumulated_usage, round_cost, accumulated_cost_summary)``
    """
    prev = prev or {}
    api_usage = dict(api_usage or {})

    acc: Dict[str, Any] = {}
    _add_usage_keys(acc, prev)
    _add_usage_keys(acc, api_usage)

    per_model: Dict[str, Dict[str, Any]] = {
        name: dict(data) for name, data in (prev.get("per_model") or {}).items()
    }
    model_usage = dict(per_model.get(model_name) or {})
    _add_usage_keys(model_usage, api_usage)
    per_model[model_name] = model_usage

    total_cost_val = 0.0
    for mname, mdata in per_model.items():
        mcost = calculate_cost(mname, mdata)
        cost_val = float(mcost.get("total_cost", 0) or 0)
        mdata["cost"] = round(cost_val, 6)
        total_cost_val += cost_val

    acc["per_model"] = per_model
    acc["total_cost"] = round(total_cost_val, 6)
    acc["currency"] = "CNY"

    round_cost = calculate_cost(model_name, api_usage)
    acc["last_request"] = {
        "model": model_name,
        "usage": api_usage,
        "cost": round_cost,
    }

    accumulated_cost = {
        "total_cost": acc["total_cost"],
        "currency": "CNY",
    }
    return acc, round_cost, accumulated_cost
