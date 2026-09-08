"""codeagent.core.attachments 纯逻辑函数单元测试。

覆盖 mime 白名单/kind 分类（安全关键：SVG/HTML 拒绝防 XSS）、
image_dir tag 解析、globs 匹配、message attachment 检测/收集。
"""
import pytest

from codeagent.core import attachments as att


# ---------- mime_allowed ----------
@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "video/mp4", "audio/mpeg", "application/pdf", "text/plain"])
def test_mime_allowed_common(mime):
    assert att.mime_allowed(mime) is True


@pytest.mark.parametrize("mime", ["image/svg+xml", "text/html", "application/x-msdownload", "text/html; charset=utf-8"])
def test_mime_rejected_svg_html_exec(mime):
    assert att.mime_allowed(mime) is False


def test_mime_allowed_strips_params_and_case():
    assert att.mime_allowed("IMAGE/PNG; charset=utf-8") is True


def test_mime_allowed_empty_with_filename_guess():
    assert att.mime_allowed("", "photo.png") is True
    assert att.mime_allowed("", "doc.pdf") is True


def test_mime_allowed_empty_no_filename():
    assert att.mime_allowed("", "") is False


# ---------- _kind_for_mime ----------
def test_kind_classification():
    assert att._kind_for_mime("image/png", "") == "image"
    assert att._kind_for_mime("video/mp4", "") == "video"
    assert att._kind_for_mime("audio/mpeg", "") == "audio"
    assert att._kind_for_mime("application/pdf", "") == "document"


def test_kind_pdf_by_filename_fallback():
    assert att._kind_for_mime("", "report.PDF") == "document"


def test_kind_unknown_is_document():
    assert att._kind_for_mime("application/octet-stream", "file.bin") == "document"


# ---------- parse_image_dir_tags ----------
def test_parse_image_dir_tag():
    tags = att.parse_image_dir_tags("看 [image_dir:photos max=5] 目录")
    assert tags == [("photos", 5)]


def test_parse_image_dir_tag_default_max():
    tags = att.parse_image_dir_tags("看 [image_dir:photos] 目录")
    # 无 max → 用默认 _dir_max_files()（32）
    assert tags == [("photos", 32)]


def test_parse_image_dir_no_tag():
    assert att.parse_image_dir_tags("没有 tag") == []


def test_parse_image_dir_multiple():
    tags = att.parse_image_dir_tags("[image_dir:a] [image_dir:b max=3]")
    assert ("a", 32) in tags and ("b", 3) in tags


def test_parse_image_dir_max_clamped():
    # max 超过上限被钳制到 _dir_max_files()
    assert att.parse_image_dir_tags("[image_dir:x max=999]") == [("x", 32)]


# ---------- _parse_globs / _matches_globs ----------
def test_matches_globs_exact():
    assert att._matches_globs("photo.png", ("*.png",)) is True
    assert att._matches_globs("photo.jpg", ("*.png",)) is False


def test_matches_globs_case_insensitive():
    assert att._matches_globs("PHOTO.PNG", ("*.png",)) is True


def test_matches_globs_multiple():
    assert att._matches_globs("a.gif", ("*.png", "*.gif", "*.jpg")) is True


# ---------- message attachment 检测 ----------
def test_message_has_image_attachments():
    assert att.message_has_image_attachments({"attachments": [{"kind": "image"}]}) is True
    assert att.message_has_image_attachments({"attachments": [{"kind": "audio"}]}) is False
    assert att.message_has_image_attachments({}) is False


def test_message_has_video_attachments():
    assert att.message_has_video_attachments({"attachments": [{"kind": "video"}]}) is True


def test_message_has_audio_attachments():
    assert att.message_has_audio_attachments({"attachments": [{"kind": "audio"}]}) is True


def test_collect_attachment_ids_from_message():
    msg = {"attachments": [{"id": "a1", "kind": "image"}, {"id": "a2", "kind": "video"}]}
    assert att.collect_attachment_ids_from_message(msg) == ["a1", "a2"]


def test_collect_attachment_ids_empty():
    assert att.collect_attachment_ids_from_message({}) == []
