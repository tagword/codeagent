"""codeagent.server.webui_api_app 会话历史 JSON 安全单元测试。

覆盖 _json_default_history / _history_payload_json_safe：
确保含 bytes/set/object 的 payload 能安全 JSON 序列化（Starlette 不抛 TypeError）。
"""
from codeagent.server.webui_api_app import _history_payload_json_safe, _json_default_history


# ---------- _json_default_history ----------
def test_default_history_bytes_decoded():
    assert _json_default_history(b"hello") == "hello"


def test_default_history_invalid_bytes_replace():
    out = _json_default_history(b"\xff\xfe")
    assert isinstance(out, str)


def test_default_history_set_to_list():
    assert sorted(_json_default_history({1, 2})) == [1, 2]


def test_default_history_other_to_str():
    obj = object()
    assert _json_default_history(obj) == str(obj)


# ---------- _history_payload_json_safe ----------
def test_safe_normal_payload():
    assert _history_payload_json_safe({"msg": "hi", "n": 1}) == {"msg": "hi", "n": 1}


def test_safe_with_bytes():
    out = _history_payload_json_safe({"trace": [{"raw": b"abc"}]})
    assert out["trace"][0]["raw"] == "abc"


def test_safe_with_set():
    out = _history_payload_json_safe({"tags": {"a", "b"}})
    assert sorted(out["tags"]) == ["a", "b"]


def test_safe_with_invalid_bytes_no_crash():
    # 非法 utf-8 bytes → replace，不抛异常
    out = _history_payload_json_safe({"raw": b"\xff\xfe"})
    assert isinstance(out["raw"], str)


def test_safe_nested_mixed():
    payload = {
        "rows": [
            {"id": 1, "raw": b"x"},
            {"id": 2, "tags": {"p", "q"}},
        ]
    }
    out = _history_payload_json_safe(payload)
    assert out["rows"][0]["raw"] == "x"
    assert sorted(out["rows"][1]["tags"]) == ["p", "q"]


def test_safe_empty():
    assert _history_payload_json_safe({}) == {}
