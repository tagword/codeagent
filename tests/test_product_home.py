import os

from codeagent.core.bootstrap import bootstrap_codeagent_runtime
from codeagent.core.env import product_home


def test_default_product_home_is_codeagent(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEAGENT_HOME", raising=False)
    monkeypatch.delenv("CODEAGENT_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SEED_PROJECT_ROOT", raising=False)

    home = product_home()

    assert home == (tmp_path / ".codeagent").resolve()


def test_bootstrap_sets_seed_project_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SEED_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("CODEAGENT_HOME", raising=False)
    monkeypatch.delenv("CODEAGENT_PROJECT_ROOT", raising=False)

    got = bootstrap_codeagent_runtime()

    assert got == (tmp_path / ".codeagent").resolve()
    assert os.environ["SEED_PROJECT_ROOT"] == str(got)
    assert os.environ["CODEAGENT_HOME"] == str(got)
