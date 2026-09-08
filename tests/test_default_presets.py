"""codeagent.core.default_presets 单元测试。

用 monkeypatch 隔离 IO（把 _config_dir 指向 tmp_path）。
覆盖：
1. get_default_preset_ids：无文件空 / 新 JSON map / 过滤非法 slot / 空值
2. set_default_preset_id_for_slot：设置/清除/未知 slot 报错
3. set_default_preset_ids：批量替换忽略未知 slot
4. legacy shim：get/set_default_preset_id 走 chat slot
"""
import json
import pathlib

import pytest

from codeagent.core import default_presets as dp


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    """把 _config_dir 指向临时目录 + 隔离 legacy seed 路径，干净测试新 JSON map 逻辑。"""
    monkeypatch.setattr(dp, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(dp, "_read_legacy_single_id", lambda: "")
    return tmp_path


def _read_file(cfg_dir, filename):
    p = cfg_dir / filename
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ---------- get_default_preset_ids ----------
def test_get_empty_when_no_file(cfg_dir):
    assert dp.get_default_preset_ids() == {}


def test_get_reads_new_json_map(cfg_dir):
    (cfg_dir / dp.DEFAULT_PRESET_IDS_FILENAME).write_text(
        json.dumps({"chat": "preset-a", "vision": "preset-b"}), encoding="utf-8"
    )
    assert dp.get_default_preset_ids() == {"chat": "preset-a", "vision": "preset-b"}


def test_get_filters_unknown_slots(cfg_dir):
    (cfg_dir / dp.DEFAULT_PRESET_IDS_FILENAME).write_text(
        json.dumps({"chat": "a", "evil_slot": "b", "other": "c"}), encoding="utf-8"
    )
    assert dp.get_default_preset_ids() == {"chat": "a"}


def test_get_ignores_empty_and_non_string(cfg_dir):
    (cfg_dir / dp.DEFAULT_PRESET_IDS_FILENAME).write_text(
        json.dumps({"chat": "", "vision": "  ", "audio": 123, "music": "ok"}), encoding="utf-8"
    )
    assert dp.get_default_preset_ids() == {"music": "ok"}


def test_get_bad_json_returns_empty(cfg_dir):
    (cfg_dir / dp.DEFAULT_PRESET_IDS_FILENAME).write_text("{bad json", encoding="utf-8")
    assert dp.get_default_preset_ids() == {}


def test_get_non_dict_returns_empty(cfg_dir):
    (cfg_dir / dp.DEFAULT_PRESET_IDS_FILENAME).write_text('["list"]', encoding="utf-8")
    assert dp.get_default_preset_ids() == {}


# ---------- set_default_preset_id_for_slot ----------
def test_set_slot_persists(cfg_dir):
    dp.set_default_preset_id_for_slot("chat", "preset-x")
    data = _read_file(cfg_dir, dp.DEFAULT_PRESET_IDS_FILENAME)
    assert data == {"chat": "preset-x"}


def test_set_slot_empty_clears(cfg_dir):
    dp.set_default_preset_id_for_slot("chat", "preset-x")
    dp.set_default_preset_id_for_slot("chat", "")
    assert dp.get_default_preset_ids() == {}


def test_set_unknown_slot_raises(cfg_dir):
    with pytest.raises(ValueError):
        dp.set_default_preset_id_for_slot("bad_slot", "x")


def test_set_trims_whitespace(cfg_dir):
    dp.set_default_preset_id_for_slot("chat", "  preset-y  ")
    assert dp.get_default_preset_ids() == {"chat": "preset-y"}


# ---------- set_default_preset_ids ----------
def test_set_bulk_ignores_unknown(cfg_dir):
    dp.set_default_preset_ids({"chat": "a", "vision": "b", "evil": "zzz", "bad": 123})
    assert dp.get_default_preset_ids() == {"chat": "a", "vision": "b"}


def test_set_bulk_empty_clears_all(cfg_dir):
    dp.set_default_preset_id_for_slot("chat", "a")
    dp.set_default_preset_ids({})
    assert dp.get_default_preset_ids() == {}


# ---------- legacy shim ----------
def test_legacy_get_default_preset_id_empty(cfg_dir):
    assert dp.get_default_preset_id() == ""


def test_legacy_set_then_get_chat(cfg_dir):
    dp.set_default_preset_id("legacy-preset")
    assert dp.get_default_preset_id() == "legacy-preset"
    # 内部映射到 chat slot
    assert dp.get_default_preset_ids() == {"chat": "legacy-preset"}
