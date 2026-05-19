import os

from codeagent.core.bootstrap import bootstrap_codeagent_runtime
def test_bootstrap_bridges_kernel_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "codeagent.env").write_text("CODEAGENT_LLM_BASEURL=https://bridge.test\n", encoding="utf-8")
    monkeypatch.delenv("SEED_LLM_BASEURL", raising=False)
    monkeypatch.delenv("CODEAGENT_LLM_BASEURL", raising=False)

    home = bootstrap_codeagent_runtime(tmp_path / "agent-home")

    assert home == (tmp_path / "agent-home").resolve()
    assert os.environ.get("CODEAGENT_LLM_BASEURL") == "https://bridge.test"
    assert os.environ.get("SEED_LLM_BASEURL") == "https://bridge.test"
