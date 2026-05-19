from codeagent.core.pricing import calculate_cost, format_cost, normalize_model


def test_normalize_model_aliases():
    assert normalize_model("deepseek-chat") == "deepseek-v4-flash"
    assert normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert normalize_model("unknown-model") is None


def test_calculate_cost_flash():
    usage = {
        "prompt_cache_hit_tokens": 1_000_000,
        "prompt_cache_miss_tokens": 0,
        "completion_tokens": 0,
    }
    out = calculate_cost("deepseek-chat", usage)
    assert out["model"] == "deepseek-v4-flash"
    assert out["total_cost"] == 0.02
    assert out["currency"] == "CNY"


def test_format_cost_small():
    assert format_cost(0) == "¥0"
    assert format_cost(0.005).startswith("¥")
