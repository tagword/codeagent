"""codeagent.core.pricing 单元测试。

覆盖：
1. normalize_model：标准名、别名映射、未知模型
2. calculate_cost：缓存命中/未命中/输出费用、空 usage、未知模型、边界
3. format_cost：不同金额格式化
"""
from codeagent.core import pricing as pr


# ---------- normalize_model ----------
def test_normalize_standard_model():
    assert pr.normalize_model("deepseek-v4-flash") == "deepseek-v4-flash"
    assert pr.normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"


def test_normalize_alias_mapping():
    # 旧名 deepseek-chat / deepseek-reasoner → flash
    assert pr.normalize_model("deepseek-chat") == "deepseek-v4-flash"
    assert pr.normalize_model("deepseek-reasoner") == "deepseek-v4-flash"


def test_normalize_case_insensitive_and_whitespace():
    assert pr.normalize_model("  DeepSeek-V4-Flash  ") == "deepseek-v4-flash"


def test_normalize_unknown_model():
    assert pr.normalize_model("unknown-model") is None
    assert pr.normalize_model("") is None


# ---------- calculate_cost ----------
def test_cost_flash_cache_miss_only():
    usage = {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 0}
    r = pr.calculate_cost("deepseek-v4-flash", usage)
    assert r["total_cost"] == 1.0  # 1M * 1.0/1M
    assert r["cache_miss_cost"] == 1.0
    assert r["cache_hit_cost"] == 0.0
    assert r["output_cost"] == 0.0
    assert r["currency"] == "CNY"
    assert r["model"] == "deepseek-v4-flash"


def test_cost_flash_cache_hit_only():
    usage = {"prompt_cache_hit_tokens": 1_000_000, "completion_tokens": 0}
    r = pr.calculate_cost("deepseek-v4-flash", usage)
    assert r["cache_hit_cost"] == 0.02  # 1M * 0.02/1M
    assert r["total_cost"] == 0.02


def test_cost_flash_output_only():
    usage = {"completion_tokens": 1_000_000}
    r = pr.calculate_cost("deepseek-v4-flash", usage)
    assert r["output_cost"] == 2.0  # 1M * 2.0/1M
    assert r["total_cost"] == 2.0


def test_cost_mixed_all_components():
    usage = {
        "prompt_cache_hit_tokens": 500_000,
        "prompt_cache_miss_tokens": 500_000,
        "completion_tokens": 250_000,
    }
    r = pr.calculate_cost("deepseek-v4-flash", usage)
    # 0.5M*0.02 + 0.5M*1.0 + 0.25M*2.0 (per 1M)
    assert r["cache_hit_cost"] == 0.01
    assert r["cache_miss_cost"] == 0.5
    assert r["output_cost"] == 0.5
    assert round(r["total_cost"], 6) == round(1.01, 6)


def test_cost_pro_pricing_differs_from_flash():
    usage = {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 1_000_000}
    r_flash = pr.calculate_cost("deepseek-v4-flash", usage)
    r_pro = pr.calculate_cost("deepseek-v4-pro", usage)
    # pro: 1M*3.0 + 1M*6.0 = 9.0; flash: 1M*1.0 + 1M*2.0 = 3.0
    assert r_pro["total_cost"] == 9.0
    assert r_flash["total_cost"] == 3.0


def test_cost_alias_model_uses_flash_pricing():
    usage = {"prompt_cache_miss_tokens": 1_000_000}
    r = pr.calculate_cost("deepseek-chat", usage)  # 别名 → flash
    assert r["model"] == "deepseek-v4-flash"
    assert r["total_cost"] == 1.0


def test_cost_empty_usage_returns_zero():
    r = pr.calculate_cost("deepseek-v4-flash", {})
    assert r["total_cost"] == 0.0
    r2 = pr.calculate_cost("deepseek-v4-flash", None)
    assert r2["total_cost"] == 0.0


def test_cost_unknown_model_returns_zero_with_original_name():
    r = pr.calculate_cost("no-such-model", {"completion_tokens": 100})
    assert r["total_cost"] == 0.0
    assert r["model"] == "no-such-model"


def test_cost_missing_keys_treated_as_zero():
    # 只有 total_tokens，没有 cache/output 明细 → 全部按 0 算
    r = pr.calculate_cost("deepseek-v4-flash", {"total_tokens": 1000})
    assert r["total_cost"] == 0.0


def test_cost_zero_tokens():
    r = pr.calculate_cost("deepseek-v4-flash", {"completion_tokens": 0, "prompt_cache_miss_tokens": 0})
    assert r["total_cost"] == 0.0


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
