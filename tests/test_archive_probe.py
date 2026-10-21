"""codeagent.server.webui_api_app 归档 + LLM probe 校验单元测试。

覆盖 _archive_session_path（文件归档）与 _llm_probe_response 的输入校验分支。
"""
import asyncio
import json

from codeagent.server.webui_api_app import _archive_session_path


# ---------- _archive_session_path ----------
def test_archive_moves_file(tmp_path):
    src = tmp_path / "sess.json"
    src.write_text("{}", encoding="utf-8")
    assert _archive_session_path(src) is True
    # 原文件被移走，归档目录出现
    assert not src.exists()
    assert (tmp_path / "archived" / "sess.json").exists()


def test_archive_overwrites_existing_dest(tmp_path):
    src = tmp_path / "sess.json"
    src.write_text("new", encoding="utf-8")
    arch_dir = tmp_path / "archived"
    arch_dir.mkdir()
    (arch_dir / "sess.json").write_text("old", encoding="utf-8")
    assert _archive_session_path(src) is True
    assert (arch_dir / "sess.json").read_text() == "new"


def test_archive_oserror_returns_false(tmp_path, monkeypatch):
    src = tmp_path / "sess.json"
    src.write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("denied")

    monkeypatch.setattr("pathlib.Path.mkdir", boom)
    assert _archive_session_path(src) is False


# ---------- _llm_probe_response 校验分支 ----------
def _probe_with(body):
    from codeagent.server.webui_api_app import _llm_probe_response

    async def run():
        return await _llm_probe_response(body)

    return asyncio.run(run())


def test_probe_requires_base_url():
    resp = _probe_with({})
    assert resp.status_code == 400
    assert "base_url" in json.loads(resp.body).get("detail", "")


def test_probe_rejects_non_http_scheme():
    resp = _probe_with({"base_url": "ftp://x.com"})
    assert resp.status_code == 400
    assert "http(s)" in json.loads(resp.body).get("detail", "")


def test_probe_accepts_http_base_url():
    # 只测校验通过分支（不真发请求）：mock urllib 探测
    import codeagent.server.webui_api_app as mod

    async def fake_to_thread(fn):
        return True, "ok-model"

    async def run():
        return await mod._llm_probe_response(
            {"base_url": "http://localhost:9999", "model": "m1", "api_key": "", "auth_scheme": "Bearer"}
        )

    # 替换 asyncio.to_thread 为假实现
    import unittest.mock as mock
    with mock.patch.object(mod.asyncio, "to_thread", side_effect=fake_to_thread):
        resp = asyncio.run(run())
    assert resp.status_code == 200
    assert "连通性正常" in json.loads(resp.body).get("model_hint", "")


def test_probe_failed_probe_returns_502():
    import unittest.mock as mock

    import codeagent.server.webui_api_app as mod

    async def fake_to_thread(fn):
        return False, "connect refused"

    with mock.patch.object(mod.asyncio, "to_thread", side_effect=fake_to_thread):
        resp = asyncio.run(
            mod._llm_probe_response({"base_url": "http://localhost:9999"})
        )
    assert resp.status_code == 502
    assert "connect refused" in json.loads(resp.body).get("detail", "")
