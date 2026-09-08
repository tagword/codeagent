"""codeagent.server.webui_api_app env chat 配置单元测试。

覆盖 _env_chat_specs（key→默认值清单完整性）与 _env_chat_view（文件值合并）。

注意：_resolve_env_value 优先读 os.environ，测试必须 monkeypatch.delenv 隔离。
"""
from codeagent.core import env as ca_env
from codeagent.server.webui_api_app import _env_chat_specs

# specs 中出现的所有 key（用于统一清理环境变量）
_SPEC_KEYS = {k for keys, _ in _env_chat_specs() for k in keys}


def _clear_env(monkeypatch):
    for k in _SPEC_KEYS:
        monkeypatch.delenv(k, raising=False)


# ---------- _env_chat_specs ----------
def test_specs_non_empty():
    assert len(_env_chat_specs()) >= 10


def test_specs_cover_chat_defaults():
    specs = list(_env_chat_specs())
    by_key = {k: d for keys, d in specs for k in keys}
    assert by_key[ca_env.CHAT_MAX_TOOL_ROUNDS_DEFAULT] == "16"
    assert by_key[ca_env.CHAT_MAX_TOKENS] == "8192"
    assert by_key[ca_env.CONTEXT_COMPACT_MID_LOOP] == "1"


def test_specs_defaults_are_strings():
    for keys, default in _env_chat_specs():
        assert isinstance(default, str)
        assert keys  # 非空 key 元组


def test_specs_no_duplicate_keys():
    seen = set()
    for keys, _ in _env_chat_specs():
        for k in keys:
            assert k not in seen, f"duplicate key {k}"
            seen.add(k)


def test_specs_keys_are_env_keys():
    for keys, _ in _env_chat_specs():
        for k in keys:
            assert k.startswith("CODEAGENT_")


# ---------- _env_chat_view ----------
def test_env_chat_view_merges_file_values(tmp_path, monkeypatch):
    from codeagent.server.webui_api_app import _env_chat_view
    _clear_env(monkeypatch)

    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    # ENV_FILENAME = 'env'
    (cfg / "env").write_text("CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT=24\n", encoding="utf-8")

    view = _env_chat_view(tmp_path)
    assert view[ca_env.CHAT_MAX_TOOL_ROUNDS_DEFAULT] == "24"
    assert view[ca_env.CHAT_MAX_TOKENS] == "8192"


def test_env_chat_view_no_files_uses_defaults(tmp_path, monkeypatch):
    from codeagent.server.webui_api_app import _env_chat_view
    _clear_env(monkeypatch)

    view = _env_chat_view(tmp_path)
    assert view[ca_env.CHAT_MAX_TOOL_ROUNDS_DEFAULT] == "16"


def test_env_chat_view_legacy_env_merged(tmp_path, monkeypatch):
    from codeagent.server.webui_api_app import _env_chat_view
    _clear_env(monkeypatch)

    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    # LEGACY_ENV_FILENAME = 'codeagent.env'
    (cfg / "codeagent.env").write_text("CODEAGENT_CHAT_MAX_TOKENS=4096\n", encoding="utf-8")

    view = _env_chat_view(tmp_path)
    assert view[ca_env.CHAT_MAX_TOKENS] == "4096"


def test_env_chat_view_env_overrides_legacy(tmp_path, monkeypatch):
    from codeagent.server.webui_api_app import _env_chat_view
    _clear_env(monkeypatch)

    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    (cfg / "codeagent.env").write_text("CODEAGENT_CHAT_MAX_TOKENS=4096\n", encoding="utf-8")
    (cfg / "env").write_text("CODEAGENT_CHAT_MAX_TOKENS=8192\n", encoding="utf-8")

    view = _env_chat_view(tmp_path)
    # env 文件（seed）优先于 legacy
    assert view[ca_env.CHAT_MAX_TOKENS] == "8192"
