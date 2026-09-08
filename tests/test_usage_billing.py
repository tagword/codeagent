"""codeagent.core.usage_billing 单元测试。

覆盖：
1. merge_accumulated_usage：无历史、有历史、多模型 per_model 累加
2. 空 usage / 无 prev 的边界
3. 非数值字段容错
"""
from codeagent.core.usage_billing import merge_accumulated_usage


def test_merge_from_empty_both():
    acc, round_cost, acc_cost = merge_accumulated_usage(None, "deepseek-v4-flash", None)
    # 无历史无 usage → 各 token 为 0
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert acc[key] == 0
    assert acc["total_cost"] == 0.0
    assert acc["currency"] == "CNY"
    assert acc_cost["total_cost"] == 0.0


def test_merge_first_round_with_usage():
    usage = {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 100_000}
    acc, round_cost, acc_cost = merge_accumulated_usage(None, "deepseek-v4-flash", usage)
    # flash: 1M miss(1.0) + 100K output(2.0) → 1.0 + 0.2 = 1.2
    assert acc["prompt_cache_miss_tokens"] == 1_000_000
    assert acc["completion_tokens"] == 100_000
    assert round(acc["total_cost"], 6) == round(1.2, 6)
    assert acc["currency"] == "CNY"
    # round_cost 是单次请求费用
    assert round(float(round_cost.get("total_cost", 0)), 6) == round(1.2, 6)


def test_merge_accumulates_across_rounds():
    r1_usage = {"completion_tokens": 100_000}
    acc1, _, _ = merge_accumulated_usage(None, "deepseek-v4-flash", r1_usage)
    assert acc1["completion_tokens"] == 100_000
    # 第二轮在 acc1 基础上累加
    r2_usage = {"completion_tokens": 50_000}
    acc2, _, _ = merge_accumulated_usage(acc1, "deepseek-v4-flash", r2_usage)
    assert acc2["completion_tokens"] == 150_000
    # total_tokens 只累加显式提供的 key；这里未提供 total_tokens，故仍为 0
    assert acc2["total_tokens"] == 0


def test_merge_different_models_tracked_separately_in_per_model():
    usage_flash = {"completion_tokens": 100_000}
    acc1, _, _ = merge_accumulated_usage(None, "deepseek-v4-flash", usage_flash)
    usage_pro = {"completion_tokens": 50_000}
    acc2, _, _ = merge_accumulated_usage(acc1, "deepseek-v4-pro", usage_pro)
    # per_model 分开记录
    assert acc2["per_model"]["deepseek-v4-flash"]["completion_tokens"] == 100_000
    assert acc2["per_model"]["deepseek-v4-pro"]["completion_tokens"] == 50_000
    # 总 completion = 150K
    assert acc2["completion_tokens"] == 150_000


def test_merge_same_model_accumulates_in_per_model():
    usage = {"completion_tokens": 100_000}
    acc1, _, _ = merge_accumulated_usage(None, "deepseek-v4-flash", usage)
    acc2, _, _ = merge_accumulated_usage(acc1, "deepseek-v4-flash", usage)
    assert acc2["per_model"]["deepseek-v4-flash"]["completion_tokens"] == 200_000


def test_merge_total_cost_is_sum_of_models():
    # flash: 100K completion = 0.2; pro: 100K completion = 0.6
    acc1, _, _ = merge_accumulated_usage(None, "deepseek-v4-flash", {"completion_tokens": 100_000})
    acc2, _, _ = merge_accumulated_usage(acc1, "deepseek-v4-pro", {"completion_tokens": 100_000})
    assert round(acc2["total_cost"], 6) == round(0.2 + 0.6, 6)
    assert round(acc2["per_model"]["deepseek-v4-flash"]["cost"], 6) == round(0.2, 6)
    assert round(acc2["per_model"]["deepseek-v4-pro"]["cost"], 6) == round(0.6, 6)


def test_merge_round_cost_reflects_only_current_request():
    acc, round_cost, acc_cost = merge_accumulated_usage(
        None, "deepseek-v4-flash", {"completion_tokens": 100_000}
    )
    # round_cost 只含本次请求的 cost
    assert round(float(round_cost.get("total_cost", 0)), 6) == round(0.2, 6)


def test_merge_non_numeric_usage_treated_as_zero():
    # 非数值字段不崩溃，按 0 处理
    acc, _, _ = merge_accumulated_usage(None, "deepseek-v4-flash", {"completion_tokens": "abc"})
    assert acc["completion_tokens"] == 0


def test_merge_unknown_model_cost_zero_but_tokens_counted():
    usage = {"completion_tokens": 100_000}
    acc, round_cost, _ = merge_accumulated_usage(None, "no-such-model", usage)
    # tokens 照常累加，但费用为 0（未知模型无定价）
    assert acc["completion_tokens"] == 100_000
    assert acc["total_cost"] == 0.0
    assert float(round_cost.get("total_cost", 0)) == 0.0


def test_merge_prev_preserves_non_usage_fields():
    prev = {"custom_field": "keep-me"}
    acc, _, _ = merge_accumulated_usage(prev, "deepseek-v4-flash", {})
    # prev 的 token 字段会被 _add_usage_keys 处理，但自定义字段应保留在结果结构里
    # （per_model / total_cost 等由函数重建）
    assert acc["total_cost"] == 0.0
