"""codeagent.core.pricing 单元测试。

覆盖：
1. normalize_model：标准名、别名映射、未知模型
2. calculate_cost：缓存命中/未命中/输出费用、空 usage、未知模型、边界
3. format_cost：不同金额格式化

注意：DeepSeek 定价分 peak / off_peak 两档，费用随「计费时刻」浮动。
所有计费断言必须显式传 ``now`` 固定时段，否则测试结果会随运行时刻变化
（白天跑 peak、深夜跑 off_peak，同一断言时对时错）。
本文件统一使用 OFF_PEAK_NOW（周末凌晨，确定在空闲时段）。
"""
from datetime import datetime

from codeagent.core import pricing as pr

# 2026-10-18 是周日 03:00（北京时间），确定落在 off_peak
OFF_PEAK_NOW = datetime(2026, 10, 18, 3, 0)


# ---------- normalize_model ----------
def test_normalize_standard_model():
    # 定价表标准 key：deepseek-flash / deepseek-v4-pro
    assert pr.normalize_model("deepseek-flash") == "deepseek-flash"
    assert pr.normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"


def test_normalize_alias_mapping():
    # 旧名/带 v4 的写法统一归一到定价表 key
    assert pr.normalize_model("deepseek-chat") == "deepseek-flash"
    assert pr.normalize_model("deepseek-reasoner") == "deepseek-flash"
    assert pr.normalize_model("deepseek-v4-flash") == "deepseek-flash"


def test_normalize_case_insensitive_and_whitespace():
    assert pr.normalize_model("  DeepSeek-V4-Flash  ") == "deepseek-flash"


def test_normalize_unknown_model():
    assert pr.normalize_model("unknown-model") is None
    assert pr.normalize_model("") is None


# ---------- calculate_cost（off_peak 档）----------
def test_cost_flash_cache_miss_only():
    usage = {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 0}
    r = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    assert r["total_cost"] == 1.0  # 1M * 1.0/1M（off_peak）
    assert r["cache_miss_cost"] == 1.0
    assert r["cache_hit_cost"] == 0.0
    assert r["output_cost"] == 0.0
    assert r["currency"] == "CNY"
    assert r["model"] == "deepseek-flash"
    assert r["time_bucket"] == "off_peak"


def test_cost_flash_cache_hit_only():
    usage = {"prompt_cache_hit_tokens": 1_000_000, "completion_tokens": 0}
    r = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    assert r["cache_hit_cost"] == 0.02  # 1M * 0.02/1M
    assert r["total_cost"] == 0.02


def test_cost_flash_output_only():
    usage = {"completion_tokens": 1_000_000}
    r = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    assert r["output_cost"] == 4.0  # 1M * 4.0/1M（off_peak）
    assert r["total_cost"] == 4.0


def test_cost_mixed_all_components():
    usage = {
        "prompt_cache_hit_tokens": 500_000,
        "prompt_cache_miss_tokens": 500_000,
        "completion_tokens": 250_000,
    }
    r = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    # 0.5M*0.02 + 0.5M*1.0 + 0.25M*4.0 (per 1M, off_peak)
    assert r["cache_hit_cost"] == 0.01
    assert r["cache_miss_cost"] == 0.5
    assert r["output_cost"] == 1.0
    assert round(r["total_cost"], 6) == round(1.51, 6)


def test_cost_pro_pricing_differs_from_flash():
    usage = {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 1_000_000}
    r_flash = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    r_pro = pr.calculate_cost("deepseek-v4-pro", usage, now=OFF_PEAK_NOW)
    # pro(off_peak): 1M*4.5 + 1M*13.5 = 18.0; flash(off_peak): 1M*1.0 + 1M*4.0 = 5.0
    assert r_pro["total_cost"] == 18.0
    assert r_flash["total_cost"] == 5.0


def test_cost_alias_model_uses_flash_pricing():
    usage = {"prompt_cache_miss_tokens": 1_000_000}
    r = pr.calculate_cost("deepseek-chat", usage, now=OFF_PEAK_NOW)  # 别名 → flash
    assert r["model"] == "deepseek-flash"
    assert r["total_cost"] == 1.0


def test_cost_peak_is_double_off_peak():
    """同一用量在 peak 时段费用是 off_peak 的 2 倍（验证时段切换真实生效）。"""
    peak_now = datetime(2026, 10, 19, 10, 0)  # 周一 10:00 = peak
    usage = {"prompt_cache_miss_tokens": 1_000_000}
    r_peak = pr.calculate_cost("deepseek-v4-flash", usage, now=peak_now)
    r_off = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    assert r_peak["time_bucket"] == "peak"
    assert r_off["time_bucket"] == "off_peak"
    assert r_peak["total_cost"] == 2.0
    assert r_off["total_cost"] == 1.0


def test_cost_empty_usage_returns_zero():
    r = pr.calculate_cost("deepseek-v4-flash", {}, now=OFF_PEAK_NOW)
    assert r["total_cost"] == 0.0
    r2 = pr.calculate_cost("deepseek-v4-flash", None, now=OFF_PEAK_NOW)
    assert r2["total_cost"] == 0.0


def test_cost_unknown_model_returns_zero_with_original_name():
    r = pr.calculate_cost("no-such-model", {"completion_tokens": 100}, now=OFF_PEAK_NOW)
    assert r["total_cost"] == 0.0
    assert r["model"] == "no-such-model"


def test_cost_missing_keys_treated_as_zero():
    # 只有 total_tokens，没有 cache/output 明细 → 全部按 0 算
    r = pr.calculate_cost("deepseek-v4-flash", {"total_tokens": 1000}, now=OFF_PEAK_NOW)
    assert r["total_cost"] == 0.0


def test_cost_zero_tokens():
    r = pr.calculate_cost(
        "deepseek-v4-flash",
        {"completion_tokens": 0, "prompt_cache_miss_tokens": 0},
        now=OFF_PEAK_NOW,
    )
    assert r["total_cost"] == 0.0


def test_cost_non_numeric_usage_treated_as_zero():
    """API 返回异常字段（字符串/None）不得抛异常，按 0 处理。"""
    usage = {
        "prompt_cache_hit_tokens": "abc",
        "prompt_cache_miss_tokens": None,
        "completion_tokens": "500",
    }
    r = pr.calculate_cost("deepseek-v4-flash", usage, now=OFF_PEAK_NOW)
    # 只有 completion_tokens=500 有效：500 * 4.0 / 1M
    assert r["output_cost"] == 0.002
    assert r["total_cost"] == 0.002


# ---------- format_cost ----------
def test_format_zero():
    assert pr.format_cost(0) == "¥0"
    assert pr.format_cost(-1) == "¥0"


def test_format_small_amount():
    assert pr.format_cost(0.005) == "¥0.0050"
    assert pr.format_cost(0.001) == "¥0.0010"


def test_format_medium_amount():
    assert pr.format_cost(0.5) == "¥0.500"
    assert pr.format_cost(0.99) == "¥0.990"


def test_format_large_amount():
    assert pr.format_cost(3.0) == "¥3.00"
    assert pr.format_cost(123.456) == "¥123.46"
