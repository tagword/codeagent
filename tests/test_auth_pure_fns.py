"""codeagent.web.auth_impl 认证纯函数单元测试（安全相关）。

覆盖 cookie 名派生、scope method 解析、query 参数解析、token 常量时间比较。
"""

from codeagent.web import auth_impl as ai


# ---------- cookie_name_for ----------
def test_cookie_name_deterministic():
    assert ai.cookie_name_for("token-a") == ai.cookie_name_for("token-a")


def test_cookie_name_differs_by_token():
    assert ai.cookie_name_for("token-a") != ai.cookie_name_for("token-b")


def test_cookie_name_prefix():
    assert ai.cookie_name_for("anything").startswith("ca_webui_")
    assert len(ai.cookie_name_for("x")) == len("ca_webui_") + 8


# ---------- _http_method_from_scope ----------
def test_method_str_uppercased():
    assert ai._http_method_from_scope({"method": "post"}) == "POST"
    assert ai._http_method_from_scope({"method": "GET"}) == "GET"


def test_method_bytes_decoded():
    assert ai._http_method_from_scope({"method": b"get"}) == "GET"


def test_method_missing_defaults_get():
    assert ai._http_method_from_scope({}) == "GET"


def test_method_non_ascii_bytes_safe():
    # 非法字节不崩溃（errors=replace → U+FFFD），返回无害乱码而非真实 method
    out = ai._http_method_from_scope({"method": b"\xff\xfe"})
    assert isinstance(out, str)
    assert "\ufffd" in out or out == ""


# ---------- _parse_query_params / _first_query_value ----------
def test_parse_query_simple():
    q = ai._parse_query_params({"query_string": b"a=1&b=hello"})
    assert q == {"a": ["1"], "b": ["hello"]}


def test_parse_query_repeated_key():
    q = ai._parse_query_params({"query_string": b"a=1&a=2"})
    assert q["a"] == ["1", "2"]


def test_parse_query_empty():
    assert ai._parse_query_params({}) == {}
    assert ai._parse_query_params({"query_string": b""}) == {}


def test_first_query_value():
    scope = {"query_string": b"token=abc&other=1"}
    assert ai._first_query_value(scope, "token") == "abc"


def test_first_query_value_missing():
    assert ai._first_query_value({"query_string": b"a=1"}, "token") == ""


def test_first_query_value_strips():
    scope = {"query_string": b"token=%20abc%20"}
    assert ai._first_query_value(scope, "token") == "abc"


# ---------- _raw_token_matches ----------
def test_raw_token_matches_exact():
    assert ai._raw_token_matches("secret", "secret") is True


def test_raw_token_matches_mismatch():
    assert ai._raw_token_matches("secret", "secret2") is False


def test_raw_token_matches_empty():
    assert ai._raw_token_matches("", "secret") is False
    assert ai._raw_token_matches("secret", "") is False
    assert ai._raw_token_matches("", "") is False


def test_raw_token_matches_strips_whitespace():
    assert ai._raw_token_matches("  secret  ", "secret") is True


def test_raw_token_matches_diff_length_fast_false():
    # 长度不同直接 False（不进入 compare_digest）
    assert ai._raw_token_matches("a", "ab") is False
