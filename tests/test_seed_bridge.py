import os

from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed


def test_bridge_copies_when_seed_missing(monkeypatch):
    monkeypatch.delenv("SEED_LLM_BASEURL", raising=False)
    monkeypatch.setenv("CODEAGENT_LLM_BASEURL", "https://example/v1")
    bridge_codeagent_env_to_seed()
    assert os.environ.get("SEED_LLM_BASEURL") == "https://example/v1"


def test_bridge_does_not_override_seed(monkeypatch):
    monkeypatch.setenv("SEED_LLM_MODEL", "seed-model")
    monkeypatch.setenv("CODEAGENT_LLM_MODEL", "legacy-model")
    bridge_codeagent_env_to_seed()
    assert os.environ.get("SEED_LLM_MODEL") == "seed-model"
