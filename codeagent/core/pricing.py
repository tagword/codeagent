"""
DeepSeek 模型定价表 & 费用计算。

定价数据来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing
当前 deepseek-v4-pro 模型 2.5 折，优惠期至 2026-05-31 23:59 (UTC+8)。
"""

from __future__ import annotations

from typing import Any

# ── 定价表（元/百万 tokens） ─────────────────────────────────
# 模型名统一映射到标准化名称
# deepseek-v4-flash = 之前 deepseek-chat（非思考） / deepseek-reasoner（思考）
# deepseek-v4-pro   = 新旗舰模型

PRICING_TABLE: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.02,
        "input_cache_miss": 1.0,
        "output": 2.0,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.025,
        "input_cache_miss": 3.0,
        "output": 6.0,
    },
}

# 别名映射（旧模型名 → 标准化名）
_MODEL_ALIASES: dict[str, str] = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
}


def normalize_model(model: str) -> str | None:
    """将模型名标准化为定价表中的 key。未知模型返回 None。"""
    key = model.strip().lower()
    return _MODEL_ALIASES.get(key)


def calculate_cost(model: str, usage: dict[str, Any]) -> dict[str, Any]:
    """根据模型和 usage 计算费用（人民币元）。

    Args:
        model: 模型名（自动匹配别名）
        usage: DeepSeek API 返回的 usage 对象，包含：
            - prompt_cache_hit_tokens (int): 缓存命中的输入 tokens
            - prompt_cache_miss_tokens (int): 缓存未命中的输入 tokens
            - completion_tokens (int): 输出 tokens
            - total_tokens (int): 总计

    Returns:
        {
            "total_cost": float,       # 总费用（元）
            "cache_hit_cost": float,   # 缓存命中费用
            "cache_miss_cost": float,  # 缓存未命中费用
            "output_cost": float,      # 输出费用
            "currency": "CNY",
            "model": str,              # 标准化模型名
        }
        如果模型不在定价表中或 usage 为空，所有费用返回 0。
    """
    std_model = normalize_model(model)
    if not std_model or not usage:
        return {
            "total_cost": 0.0,
            "cache_hit_cost": 0.0,
            "cache_miss_cost": 0.0,
            "output_cost": 0.0,
            "currency": "CNY",
            "model": model,
        }

    prices = PRICING_TABLE[std_model]

    cache_hit = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
    cache_miss = int(usage.get("prompt_cache_miss_tokens", 0) or 0)
    output = int(usage.get("completion_tokens", 0) or 0)

    cache_hit_cost = cache_hit * prices["input_cache_hit"] / 1_000_000
    cache_miss_cost = cache_miss * prices["input_cache_miss"] / 1_000_000
    output_cost = output * prices["output"] / 1_000_000
    total = cache_hit_cost + cache_miss_cost + output_cost

    return {
        "total_cost": round(total, 6),
        "cache_hit_cost": round(cache_hit_cost, 6),
        "cache_miss_cost": round(cache_miss_cost, 6),
        "output_cost": round(output_cost, 6),
        "currency": "CNY",
        "model": std_model,
    }


def format_cost(cost: float, currency: str = "CNY") -> str:
    """将费用格式化为可读字符串。"""
    if cost <= 0:
        return "¥0"
    if cost < 0.01:
        return f"¥{cost:.4f}"
    if cost < 1:
        return f"¥{cost:.3f}"
    return f"¥{cost:.2f}"
