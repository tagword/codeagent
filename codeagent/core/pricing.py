"""Thin wrapper over :mod:`seed_model_providers.pricing` (DeepSeek only).

Canonical pricing lives in ``seed_model_providers.pricing``; this module
keeps the legacy 2-arg API (``calculate_cost(model, usage)``,
``normalize_model(model)``) so existing callers in ``codeagent`` continue
to work without changes.

Only DeepSeek pricing is currently exposed. When a non-DeepSeek provider
needs pricing here, extend the signature with ``provider``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from seed_model_providers.pricing import (
    PRICING_TABLE,
    format_cost,
    is_peak_time,
)
from seed_model_providers.pricing import (
    calculate_cost as _smp_calculate_cost,
)
from seed_model_providers.pricing import (
    normalize_model as _smp_normalize_model,
)
from seed_model_providers.pricing import (
    resolve_bucket as _smp_resolve_bucket,
)


def normalize_model(model: str) -> str | None:
    """DeepSeek-only: 把模型名标准化为定价表 key（与旧版语义一致）。

    若未来要支持多 provider，应改为 ``normalize_model(provider, model)`` 并
    更新所有调用方（参见 usage_billing.calculate_cost / normalize_model 的
    调用栈）。
    """
    return _smp_normalize_model("deepseek", model)


def calculate_cost(
    model: str,
    usage: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """DeepSeek-only: 计算费用（保留旧 2 参签名）。

    Returns: 参见 :func:`seed_model_providers.pricing.calculate_cost`。
    """
    return _smp_calculate_cost("deepseek", model, usage, now=now)


def resolve_bucket(now: datetime | None = None) -> str:
    """DeepSeek-only: 返回当前时段 bucket（"peak" / "off_peak"）。"""
    return _smp_resolve_bucket("deepseek", now)


__all__ = [
    "PRICING_TABLE",
    "normalize_model",
    "calculate_cost",
    "format_cost",
    "is_peak_time",
    "resolve_bucket",
]
