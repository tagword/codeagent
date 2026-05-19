from codeagent.core.usage_billing import merge_accumulated_usage


def test_merge_two_models():
    acc, _, total = merge_accumulated_usage(
        None,
        "deepseek-v4-flash",
        {"prompt_cache_hit_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
    )
    acc2, _, total2 = merge_accumulated_usage(
        acc,
        "deepseek-v4-pro",
        {"prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
    )
    assert "deepseek-v4-flash" in acc2["per_model"]
    assert "deepseek-v4-pro" in acc2["per_model"]
    assert acc2["per_model"]["deepseek-v4-flash"]["cost"] > 0
    assert acc2["per_model"]["deepseek-v4-pro"]["cost"] > 0
    assert acc2["total_cost"] == round(
        acc2["per_model"]["deepseek-v4-flash"]["cost"]
        + acc2["per_model"]["deepseek-v4-pro"]["cost"],
        6,
    )
    assert total2["total_cost"] == acc2["total_cost"]
    assert acc2["last_request"]["model"] == "deepseek-v4-pro"
