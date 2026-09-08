"""codeagent.skills.select 纯逻辑单元测试。

覆盖 _skill_description_from_file / _read_skills_state / _skill_enabled。
"""
import json

from codeagent.skills import select as sel


# ---------- _skill_description_from_file ----------
def test_description_reads_first_lines(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("line1\nline2\nline3", encoding="utf-8")
    d = sel._skill_description_from_file(f)
    assert d.startswith("line1")
    assert "line2" in d


def test_description_respects_max_lines(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("\n".join(f"line{i}" for i in range(20)), encoding="utf-8")
    d = sel._skill_description_from_file(f, max_lines=5)
    assert d.count("line") == 5


def test_description_truncates_by_chars(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("x" * 1000, encoding="utf-8")
    d = sel._skill_description_from_file(f, max_chars=100)
    assert len(d) <= 100
    assert d.endswith("…")


def test_description_missing_file(tmp_path):
    d = sel._skill_description_from_file(tmp_path / "nope.md")
    assert d == ""


def test_description_empty_lines(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("", encoding="utf-8")
    assert sel._skill_description_from_file(f) == ""


# ---------- _read_skills_state ----------
def test_read_state_missing_file(tmp_path):
    assert sel._read_skills_state(tmp_path / "nope.json") == {}


def test_read_state_valid(tmp_path):
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"skill-a": True, "skill-b": False}), encoding="utf-8")
    s = sel._read_skills_state(f)
    assert s == {"skill-a": True, "skill-b": False}


def test_read_state_bad_json(tmp_path):
    f = tmp_path / "state.json"
    f.write_text("{bad", encoding="utf-8")
    assert sel._read_skills_state(f) == {}


def test_read_state_non_dict(tmp_path):
    f = tmp_path / "state.json"
    f.write_text('["list"]', encoding="utf-8")
    assert sel._read_skills_state(f) == {}


def test_read_state_coerces_values(tmp_path):
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"a": 1, "b": 0, "c": "x"}), encoding="utf-8")
    s = sel._read_skills_state(f)
    assert s == {"a": True, "b": False, "c": True}


# ---------- _skill_enabled ----------
def test_skill_enabled_default_true_when_not_in_state():
    assert sel._skill_enabled({}, "skill-a") is True


def test_skill_enabled_respects_state():
    assert sel._skill_enabled({"skill-a": False}, "skill-a") is False
    assert sel._skill_enabled({"skill-a": True}, "skill-a") is True
