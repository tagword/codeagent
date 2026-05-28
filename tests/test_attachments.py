"""Attachment subsystem tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from codeagent.core.attachments import (
    ATTACHMENT_TAG_RE,
    build_user_message,
    content_text_for_skills,
    extract_document_text,
    message_has_image_attachments,
    mime_allowed,
    save_attachment,
    scan_image_directory,
)


def test_build_user_message_attachment_refs_only() -> None:
    from codeagent.core.attachments import AttachmentMeta

    meta = AttachmentMeta(
        id="abc123",
        kind="image",
        mime="image/png",
        filename="ui.png",
        size_bytes=12,
        path="/tmp/ui.png",
    )
    msg = build_user_message("请看图", [meta])
    assert "[attachment:abc123 ui.png]" in msg["content"]
    assert "base64" not in msg["content"].lower()
    assert msg["attachments"][0]["id"] == "abc123"


def test_content_text_for_skills_strips_attachment_tags() -> None:
    text = "hello\n[attachment:a1 x.png]\n[image_dir:shots max=8]"
    assert content_text_for_skills(text) == "hello"


def test_save_attachment_writes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    meta = save_attachment(
        agent_id="default",
        session_id="test-sess",
        raw_bytes=raw,
        filename="dot.png",
        mime="image/png",
    )
    assert meta.id
    assert Path(meta.path).is_file()
    assert meta.kind == "image"


def test_mime_allowed_rejects_svg() -> None:
    assert mime_allowed("image/svg+xml", "x.svg") is False
    assert mime_allowed("image/png", "x.png") is True


def test_extract_document_text_plain() -> None:
    assert extract_document_text(b"hello world", "text/plain") == "hello world"


def test_scan_image_directory(tmp_path: Path) -> None:
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (shots / "b.txt").write_text("nope", encoding="utf-8")
    paths, truncated = scan_image_directory(tmp_path, "shots", max_files=10)
    assert len(paths) == 1
    assert paths[0].name == "a.png"
    assert truncated is False


def test_scan_image_directory_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="traversal"):
        scan_image_directory(tmp_path, "../etc", max_files=4)


def test_message_has_image_attachments() -> None:
    msg = {"content": "x", "attachments": [{"id": "a", "kind": "image"}]}
    assert message_has_image_attachments(msg) is True
    assert ATTACHMENT_TAG_RE.search("[attachment:id f.png]")
