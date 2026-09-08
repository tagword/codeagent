"""codeagent.core.attachments 恶意 filename 净化安全回归测试。

验证 save_attachment 对含路径穿越（../、绝对路径）的 filename 不会逃逸出
session 附件目录——防护在 seed.core.media_store.save_session_media 层。
"""
import pathlib

import pytest

from codeagent.core.attachments import save_attachment


@pytest.fixture
def isolated_sess(tmp_path, monkeypatch):
    sess_dir = tmp_path / "sess"
    monkeypatch.setenv("SEED_AGENT_SESSIONS_DIR", str(sess_dir))
    return sess_dir


def _save(raw_name):
    return save_attachment(
        agent_id="a1",
        session_id="s1",
        raw_bytes=b"X" * 10,
        filename=raw_name,
        mime="text/plain",
    )


def test_normal_filename_stored_under_session(isolated_sess):
    meta = _save("hello.txt")
    p = pathlib.Path(meta.path)
    # 路径在隔离 sessions 目录内
    assert str(p).startswith(str(isolated_sess))
    assert p.is_file()


def test_traversal_filename_sanitized(isolated_sess):
    # filename 含 ../ → seed 库净化写入路径，不逃逸出附件目录
    meta = _save("../evil.txt")
    p = pathlib.Path(meta.path)
    assert str(p).startswith(str(isolated_sess))
    assert p.is_file()
    # 写入位置在附件子目录，不带 .. 片段
    assert ".." not in pathlib.Path(meta.path).name


def test_absolute_filename_sanitized(isolated_sess):
    meta = _save("/tmp/abs_evil.txt")
    p = pathlib.Path(meta.path)
    assert str(p).startswith(str(isolated_sess))
    assert p.is_file()


def test_no_file_escapes_sessions_dir(isolated_sess):
    # 多种恶意 filename 都不应逃逸出 sessions 目录
    for name in ("../x.txt", "../../../../etc/passwd", "a/../b.txt"):
        meta = _save(name)
        p = pathlib.Path(meta.path).resolve()
        assert str(p).startswith(str(isolated_sess.resolve())), f"escaped: {name}"
