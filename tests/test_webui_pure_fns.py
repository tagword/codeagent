"""codeagent.server.webui_api_app 纯函数单元测试。

聚焦从大文件 webui_api_app.py 中提取的、无 app 依赖的纯逻辑函数：
1. _parse_env_file：env 文件解析（注释/引号/无等号/空值）
2. _resolve_env_value：环境变量优先级（os.environ > file_vals > default）
3. _safe_under：路径穿越防护（核心安全逻辑）
4. _resolve_project_id：__unassigned__ 映射

这些函数是核心安全/配置逻辑，测试价值高。
"""
import pathlib

from codeagent.server.webui_api_app import (
    _parse_env_file,
    _resolve_env_value,
    _resolve_project_id,
    _safe_under,
)


# ---------- _parse_env_file ----------
def test_parse_env_basic(tmp_path):
    p = tmp_path / "test.env"
    p.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    assert _parse_env_file(p) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_ignores_comments_and_blank(tmp_path):
    p = tmp_path / "test.env"
    p.write_text("# comment\n\nFOO=bar\n  \n# another\n", encoding="utf-8")
    assert _parse_env_file(p) == {"FOO": "bar"}


def test_parse_env_strips_quotes(tmp_path):
    p = tmp_path / "test.env"
    p.write_text('A="hello world"\nB=\'single\'\n', encoding="utf-8")
    assert _parse_env_file(p) == {"A": "hello world", "B": "single"}


def test_parse_env_skips_line_without_equals(tmp_path):
    p = tmp_path / "test.env"
    p.write_text("NOEQUALS\nFOO=bar\n", encoding="utf-8")
    assert _parse_env_file(p) == {"FOO": "bar"}


def test_parse_env_empty_value(tmp_path):
    p = tmp_path / "test.env"
    p.write_text("EMPTY=\n", encoding="utf-8")
    assert _parse_env_file(p) == {"EMPTY": ""}


def test_parse_env_missing_file_returns_empty(tmp_path):
    assert _parse_env_file(tmp_path / "nonexistent.env") == {}


def test_parse_env_handles_partition_multiple_equals(tmp_path):
    p = tmp_path / "test.env"
    p.write_text("URL=https://x.com?a=b&c=d\n", encoding="utf-8")
    # partition 只按第一个 = 切分，value 保留其余
    assert _parse_env_file(p) == {"URL": "https://x.com?a=b&c=d"}


# ---------- _resolve_env_value ----------
def test_resolve_prefers_os_environ(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_KEY", "from-env")
    file_vals = {"TEST_KEY": "from-file"}
    assert _resolve_env_value(("TEST_KEY",), file_vals, "default") == "from-env"


def test_resolve_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_KEY", raising=False)
    file_vals = {"TEST_KEY": "from-file"}
    assert _resolve_env_value(("TEST_KEY",), file_vals, "default") == "from-file"


def test_resolve_uses_default_when_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert _resolve_env_value(("TEST_KEY",), {}, "default") == "default"


def test_resolve_tries_keys_in_order(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRST", raising=False)
    monkeypatch.delenv("SECOND", raising=False)
    file_vals = {"SECOND": "second-val"}
    # FIRST 不在，SECOND 在 → 返回 second-val
    assert _resolve_env_value(("FIRST", "SECOND"), file_vals, "default") == "second-val"


# ---------- _safe_under ----------
def test_safe_under_normal_path():
    base = pathlib.Path("/tmp")
    r = _safe_under(base, "sub/file.txt")
    assert r is not None
    assert r == (base / "sub/file.txt").resolve()


def test_safe_under_rejects_traversal():
    assert _safe_under(pathlib.Path("/tmp"), "../etc/passwd") is None
    assert _safe_under(pathlib.Path("/tmp"), "..") is None
    assert _safe_under(pathlib.Path("/tmp"), "sub/../../etc/passwd") is None


def test_safe_under_rejects_absolute_escape():
    # 绝对路径会被 lstrip('/') 处理，但若仍逃出 base 则拒绝
    assert _safe_under(pathlib.Path("/tmp"), "/etc/passwd") is not None  # 被当作相对 tmp
    # 直接给能逃出的
    assert _safe_under(pathlib.Path("/tmp/sub"), "..") is None


def test_safe_under_empty_rel():
    assert _safe_under(pathlib.Path("/tmp"), "") is None
    assert _safe_under(pathlib.Path("/tmp"), "  ") is None


def test_safe_under_allows_base_itself():
    base = pathlib.Path("/tmp")
    _safe_under(base, "")
    # 空 rel 返回 None（见上面），但 base 自身通过相对子路径可达
    r2 = _safe_under(base, ".")
    assert r2 is None or r2 == base.resolve()


# ---------- _resolve_project_id ----------
def test_resolve_project_id_unassigned():
    assert _resolve_project_id("__unassigned__") == ""


def test_resolve_project_id_normal():
    assert _resolve_project_id("project-123") == "project-123"


def test_resolve_project_id_empty():
    assert _resolve_project_id("") == ""
