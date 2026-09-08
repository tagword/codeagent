"""codeagent.server.webui_api_app git provider / 路径解析单元测试。

覆盖 _git_provider_host / _ssh_provider_target / _git_cwd / _resolve_project_id。
"""
import pathlib

from codeagent.server.webui_api_app import (
    _git_cwd,
    _git_provider_host,
    _resolve_project_id,
    _ssh_provider_target,
)


# ---------- _resolve_project_id ----------
def test_resolve_project_id_normal():
    assert _resolve_project_id("proj-1") == "proj-1"


def test_resolve_project_id_unassigned_to_empty():
    from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID
    assert _resolve_project_id(_UNASSIGNED_PROJECT_ID) == ""


def test_resolve_project_id_empty_passthrough():
    assert _resolve_project_id("") == ""


# ---------- _git_provider_host ----------
def test_git_provider_host_known():
    assert _git_provider_host("github") == "github.com"
    assert _git_provider_host("GitLab") == "gitlab.com"  # 大小写不敏感
    assert _git_provider_host("gitee") == "gitee.com"


def test_git_provider_host_unknown_falls_back_github():
    assert _git_provider_host("self-hosted") == "github.com"


def test_git_provider_host_empty_without_root():
    assert _git_provider_host("") == "github.com"


def test_git_provider_host_empty_reads_defaults_file(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    (cfg / "codeagent.git.defaults.json").write_text(
        '{"provider": "gitlab"}', encoding="utf-8"
    )
    assert _git_provider_host("", root=tmp_path) == "gitlab.com"


def test_git_provider_host_corrupt_defaults_file(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    (cfg / "codeagent.git.defaults.json").write_text("not-json", encoding="utf-8")
    # 损坏文件 → suppress 异常 → fallback github
    assert _git_provider_host("", root=tmp_path) == "github.com"


# ---------- _ssh_provider_target ----------
def test_ssh_provider_target_known():
    pid, host = _ssh_provider_target("github")
    assert pid == "github"
    assert host == "git@github.com"


def test_ssh_provider_target_empty_defaults_github():
    pid, host = _ssh_provider_target("")
    assert pid == "github"
    assert host == "git@github.com"


def test_ssh_provider_target_unknown():
    pid, host = _ssh_provider_target("weird")
    assert pid == "weird"
    assert host == "git@github.com"  # host fallback github


# ---------- _git_cwd ----------
def test_git_cwd_no_pid_uses_project_root(tmp_path):
    assert _git_cwd({}, "agent", tmp_path) == tmp_path


def test_git_cwd_with_unknown_pid_uses_project_root(tmp_path):
    # pid 无对应 project → _project_fs_dir 返回 None → fallback project_root
    assert _git_cwd({"project_id": "nope"}, "agent", tmp_path) == tmp_path


def test_git_cwd_with_unassigned_pid_uses_project_root(tmp_path):
    from codeagent.server.webui_api_app import _UNASSIGNED_PROJECT_ID
    assert _git_cwd({"project_id": _UNASSIGNED_PROJECT_ID}, "agent", tmp_path) == tmp_path
