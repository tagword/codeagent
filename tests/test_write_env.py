"""codeagent.server.webui_api_app._write_env_file_merge 单元测试。

覆盖合并写 env 文件：新建/合并现有/保留未更新 key/排序。
"""
from codeagent.server.webui_api_app import _parse_env_file, _write_env_file_merge


def test_write_creates_new_file(tmp_path):
    p = tmp_path / "sub" / "env"
    _write_env_file_merge(p, {"A": "1", "B": "2"})
    assert p.is_file()
    assert _parse_env_file(p) == {"A": "1", "B": "2"}


def test_write_merges_existing_keeps_others(tmp_path):
    p = tmp_path / "env"
    p.write_text("A=old\nC=keep\n", encoding="utf-8")
    _write_env_file_merge(p, {"A": "new", "B": "added"})
    parsed = _parse_env_file(p)
    assert parsed["A"] == "new"  # 更新
    assert parsed["B"] == "added"  # 新增
    assert parsed["C"] == "keep"  # 保留未更新


def test_write_empty_updates_keeps_file(tmp_path):
    p = tmp_path / "env"
    p.write_text("A=1\n", encoding="utf-8")
    _write_env_file_merge(p, {})
    assert _parse_env_file(p) == {"A": "1"}


def test_write_sorted_keys(tmp_path):
    p = tmp_path / "env"
    _write_env_file_merge(p, {"B": "2", "A": "1", "C": "3"})
    content = p.read_text(encoding="utf-8")
    # 排序后 A 在 B 前
    assert content.index("A=") < content.index("B=") < content.index("C=")


def test_write_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "env"
    _write_env_file_merge(p, {"A": "1"})
    assert p.is_file()
    assert _parse_env_file(p) == {"A": "1"}
