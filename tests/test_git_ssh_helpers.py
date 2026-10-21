"""Test ssh/git subprocess-parsing helpers in webui_handlers_git.

Covers _ssh_g_options / _ssh_resolve_identities / _ssh_build_status /
_ssh_read_public_keys. Subprocess boundaries are mocked via
asyncio.create_subprocess_exec or by patching helper fns directly.
"""
import asyncio
from pathlib import Path

from codeagent.server import webui_handlers_git as g


# ---------------------------------------------------------------------------
# _ssh_g_options
# ---------------------------------------------------------------------------
class _FakeProc:
    def __init__(self, rc, out=b"", err=b""):
        self.returncode = rc
        self._out = out
        self._err = err

    async def communicate(self):
        return self._out, self._err


def test_ssh_g_options_parses_kv(monkeypatch):
    created = []

    async def fake_exec(*args, **kwargs):
        created.append(args)
        return _FakeProc(0, b"identityfile /home/u/.ssh/id_ed25519\nuser git\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    out = asyncio.run(g._ssh_g_options("git@github.com"))
    assert out["identityfile"] == ["/home/u/.ssh/id_ed25519"]
    assert out["user"] == ["git"]


def test_ssh_g_options_ignores_comments_and_blank(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(0, b"# comment\n\nidentityfile /x.pub\n  \n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    out = asyncio.run(g._ssh_g_options("git@github.com"))
    assert out["identityfile"] == ["/x.pub"]


def test_ssh_g_options_nonzero_returns_empty(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(1, b"", b"bad option")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(g._ssh_g_options("git@github.com")) == {}


def test_ssh_g_options_accumulates_multi_value(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(0, b"identityfile /a\nidentityfile /b\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    out = asyncio.run(g._ssh_g_options("git@github.com"))
    assert out["identityfile"] == ["/a", "/b"]


# ---------------------------------------------------------------------------
# _ssh_resolve_identities
# ---------------------------------------------------------------------------
def test_ssh_resolve_identities_dedup_and_pub(monkeypatch, tmp_path):
    priv = tmp_path / "id_ed25519"
    priv.write_text("priv")
    pub = tmp_path / "id_ed25519.pub"
    pub.write_text("pub")

    async def fake_g_options(ssh_host):
        return {"identityfile": [str(priv), str(priv), "~/.ssh/id_rsa", "/nonexistent/key"]}

    monkeypatch.setattr(g, "_ssh_g_options", fake_g_options)
    rows = asyncio.run(g._ssh_resolve_identities("git@github.com"))
    # dedup removes the second same path
    assert len(rows) == 3
    by_name = {Path(r["private"]).name: r for r in rows}
    assert by_name["id_ed25519"]["private_exists"] is True
    assert by_name["id_ed25519"]["public_exists"] is True
    assert by_name["id_rsa"]["private_exists"] is False
    assert by_name["key"]["private_exists"] is False
    # public path derived as <priv>.pub
    assert rows[0]["public"] == str(priv) + ".pub"


def test_ssh_resolve_identities_expands_tilde(monkeypatch, tmp_path):
    async def fake_g_options(ssh_host):
        return {"identityfile": ["~/t"]}

    monkeypatch.setattr(g, "_ssh_g_options", fake_g_options)
    monkeypatch.setenv("HOME", str(tmp_path))
    rows = asyncio.run(g._ssh_resolve_identities("git@github.com"))
    assert rows[0]["private"] == str(tmp_path / "t")
    assert rows[0]["public"] == str(tmp_path / "t.pub")


def test_ssh_resolve_identities_empty_opts(monkeypatch):
    async def fake_g_options(ssh_host):
        return {}

    monkeypatch.setattr(g, "_ssh_g_options", fake_g_options)
    assert asyncio.run(g._ssh_resolve_identities("git@github.com")) == []


# ---------------------------------------------------------------------------
# _ssh_build_status
# ---------------------------------------------------------------------------
def _fake_resolve(rows):
    async def _f(ssh_host):
        return rows
    return _f


def _fake_agent_fingerprints(keys):
    async def _f():
        return keys
    return _f


def _ssh_dir(tmp_path) -> Path:
    d = tmp_path / ".ssh"
    d.mkdir(exist_ok=True)
    return d


def test_ssh_build_status_connected(monkeypatch, tmp_path):
    async def fake_probe(ssh_host):
        return True, "Hi git! You've successfully authenticated"

    monkeypatch.setattr(g, "_ssh_probe", fake_probe)
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st = asyncio.run(g._ssh_build_status("github"))
    assert st["connected"] is True
    assert st["recommendation"] == "ok_no_action"
    assert "已可用" in st["result"]


def test_ssh_build_status_has_keys_but_not_connected(monkeypatch, tmp_path):
    async def fake_probe(ssh_host):
        return False, "Permission denied"

    rows = [{"private": "/x/id_ed25519", "public": "/x/id_ed25519.pub",
             "private_exists": True, "public_exists": True}]
    monkeypatch.setattr(g, "_ssh_probe", fake_probe)
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve(rows))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st = asyncio.run(g._ssh_build_status("github"))
    assert st["connected"] is False
    assert st["recommendation"] == "needs_platform_or_config"


def test_ssh_build_status_no_keys_suggests_generate(monkeypatch, tmp_path):
    async def fake_probe(ssh_host):
        return False, "Connection refused"

    monkeypatch.setattr(g, "_ssh_probe", fake_probe)
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st = asyncio.run(g._ssh_build_status("github"))
    assert st["recommendation"] == "generate_suggested"
    assert "生成" in st["recommendation_text"]


def test_ssh_build_status_custom_host(monkeypatch, tmp_path):
    async def fake_probe(ssh_host):
        return True, "ok"

    monkeypatch.setattr(g, "_ssh_probe", fake_probe)
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st = asyncio.run(g._ssh_build_status("", ssh_host="custom.example.com"))
    assert st["provider"] == "custom"
    assert st["ssh_host"] == "custom.example.com"


# ---------------------------------------------------------------------------
# _ssh_read_public_keys
# ---------------------------------------------------------------------------
def _mk_key(tmp_path, name="id_ed25519.pub"):
    p = _ssh_dir(tmp_path) / name
    p.write_text(f"ssh-ed25519 AAAA {name}\n")
    return p


def test_ssh_read_public_keys_uses_identities_first(monkeypatch, tmp_path):
    pub = tmp_path / "id_ed25519.pub"
    pub.write_text("ssh-ed25519 AAAA id_ed25519.pub\n")
    rows = [{"private": str(tmp_path / "id_ed25519"),
             "public": str(pub), "private_exists": True, "public_exists": True}]
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve(rows))
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert err == ""
    assert "id_ed25519.pub" in text
    assert "ssh-ed25519" in text


def test_ssh_read_public_keys_missing_pub_falls_back(monkeypatch, tmp_path):
    # identity resolved but private pub missing, no agent, no default key
    # -> falls through to "no public key found" error
    rows = [{"private": str(tmp_path / "id_ed25519"),
             "public": str(tmp_path / "id_ed25519.pub"),
             "private_exists": True, "public_exists": False}]
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve(rows))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert text == ""
    assert "未找到公钥" in err


def test_ssh_read_public_keys_single_default_key(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _mk_key(tmp_path, "id_ed25519.pub")
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert err == ""
    assert "ssh-ed25519" in text


def test_ssh_read_public_keys_multiple_pubs_ambiguous(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _mk_key(tmp_path, "a.pub")
    _mk_key(tmp_path, "b.pub")
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert text == ""
    assert "未确定" in err


def test_ssh_read_public_keys_no_keys_at_all(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints", _fake_agent_fingerprints([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert text == ""
    assert "未找到公钥" in err


def test_ssh_read_public_keys_agent_only(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "_ssh_resolve_identities", _fake_resolve([]))
    monkeypatch.setattr(g, "_ssh_agent_fingerprints",
                        _fake_agent_fingerprints(["256 SHA256:abc (ED25519)"]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    text, err = asyncio.run(g._ssh_read_public_keys("github"))
    assert text == ""
    assert "ssh-agent" in err
