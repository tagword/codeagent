"""WebUI 层对 OpenAI Responses 协议 provider 的适配。

前端 provider 下拉完全由后端 catalog 驱动（``/api/ui/llm/providers`` →
``list_provider_catalog()``），因此这里验证：
1. catalog 里出现 openai_responses，且元数据正确；
2. preset 表单物化（前端「简单表单」提交的后端处理）能正确填 base_url/模型；
3. 协议解析在 codeagent 这一层同样生效。
"""

from __future__ import annotations

from seed_model_providers import (
    list_provider_catalog,
    materialize_preset_from_form,
    resolve_chat_protocol,
    resolve_provider_for_preset,
)


def _provider(pid: str) -> dict:
    for p in list_provider_catalog():
        if p.get("id") == pid:
            return p
    raise AssertionError(f"provider not in catalog: {pid}")


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------

def test_responses_provider_listed_for_webui() -> None:
    """WebUI 的 provider 下拉从 catalog 生成，新协议必须出现在列表里。"""
    p = _provider("openai_responses")
    assert p["label"]
    assert p["default_base_url"] == "https://api.openai.com/v1"
    assert "chat" in p["capabilities"]
    assert p["models"]["chat"], "必须提供 chat 模型列表，否则前端下拉为空"


def test_responses_provider_has_vision_models() -> None:
    p = _provider("openai_responses")
    assert p["models"]["vision"]


def test_openai_provider_keeps_chat_completions() -> None:
    """老 provider 的协议不能被改动，否则既有 preset 全部回归。"""
    p = _provider("openai")
    assert p["chat_protocol"] == "openai"


# ---------------------------------------------------------------------------
# preset materialization（前端表单 → 后端 preset）
# ---------------------------------------------------------------------------

def test_preset_form_materializes_responses_provider() -> None:
    out = materialize_preset_from_form(
        {"provider": "openai_responses", "model": "gpt-5.1"}
    )
    assert out["provider"] == "openai_responses"
    assert out["base_url"] == "https://api.openai.com/v1"
    assert out["model"] == "gpt-5.1"
    assert out["use_type"] == "chat"


def test_preset_form_falls_back_to_default_model() -> None:
    out = materialize_preset_from_form({"provider": "openai_responses"})
    assert out["model"] == "gpt-5.1"


def test_preset_form_rejects_unknown_model() -> None:
    """选了目录外的模型 → 回退默认，避免发出服务端必然 400 的请求。"""
    out = materialize_preset_from_form(
        {"provider": "openai_responses", "model": "not-a-real-model"}
    )
    assert out["model"] == "gpt-5.1"


def test_preset_advanced_keeps_custom_base_url() -> None:
    """高级模式允许指向兼容 Responses 的第三方端点。"""
    out = materialize_preset_from_form(
        {
            "provider": "openai_responses",
            "model": "gpt-5.1",
            "base_url": "https://gw.example.com/v1",
            "advanced": True,
        }
    )
    assert out["base_url"] == "https://gw.example.com/v1"


# ---------------------------------------------------------------------------
# protocol resolution
# ---------------------------------------------------------------------------

def test_preset_resolves_to_responses_protocol() -> None:
    preset = {
        "provider": "openai_responses",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.1",
    }
    provider = resolve_provider_for_preset(preset)
    assert provider == "openai_responses"
    assert (
        resolve_chat_protocol(provider=provider, base_url=preset["base_url"])
        == "openai_responses"
    )
