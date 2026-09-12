"""codeagent.server 纯逻辑单元测试。

覆盖 attachment_api._parse_body_json、hub._format_sse 的协议格式化逻辑。
"""
import json

from codeagent.server.attachment_api import _parse_body_json
from codeagent.server.hub import _format_sse


# ---------- _parse_body_json ----------
def test_parse_body_json_valid():
    assert _parse_body_json(b'{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_body_json_empty():
    assert _parse_body_json(b"") == {}
    assert _parse_body_json(b"{}") == {}


def test_parse_body_json_invalid():
    assert _parse_body_json(b"{bad json") == {}
    assert _parse_body_json(b"not json at all") == {}


def test_parse_body_json_non_dict():
    assert _parse_body_json(b'["list"]') == {}
    assert _parse_body_json(b'"string"') == {}


def test_parse_body_json_unicode():
    assert _parse_body_json('{"msg": "你好"}'.encode()) == {"msg": "你好"}


# ---------- _format_sse ----------
def test_format_sse_structure():
    out = _format_sse({"id": "m1", "type": "text", "content": "hi"})
    assert isinstance(out, bytes)
    text = out.decode("utf-8")
    assert "id: m1" in text
    assert "event: message" in text
    assert "data: " in text
    assert text.endswith("\n\n")


def test_format_sse_data_is_json():
    out = _format_sse({"id": "m1", "content": "hi"}).decode("utf-8")
    # 提取 data 行并解析
    for line in out.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            assert payload == {"id": "m1", "content": "hi"}
            return
    assert False, "no data line"


def test_format_sse_unicode_content():
    out = _format_sse({"id": "m1", "content": "你好"}).decode("utf-8")
    assert "你好" in out


def test_format_sse_missing_id():
    out = _format_sse({"content": "x"}).decode("utf-8")
    assert "id: " in out  # id 为空但不报错
