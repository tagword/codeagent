"""codeagent.core.audio_models / vision_models 纯函数单元测试。

聚焦无外部依赖的纯函数：
1. preset_supports_audio（audio_models）
2. preset_supports_vision（vision_models）

覆盖：True/False/缺字段/None/非 dict/类型错误。
"""
from codeagent.core.audio_models import preset_supports_audio
from codeagent.core.vision_models import preset_supports_vision


# ---------- preset_supports_audio ----------
def test_audio_supports_true():
    assert preset_supports_audio({"supports_audio": True}) is True


def test_audio_supports_false():
    assert preset_supports_audio({"supports_audio": False}) is False


def test_audio_missing_field_false():
    assert preset_supports_audio({"id": "x"}) is False


def test_audio_empty_dict_false():
    assert preset_supports_audio({}) is False


def test_audio_none_false():
    assert preset_supports_audio(None) is False


def test_audio_non_dict_false():
    assert preset_supports_audio("not-a-dict") is False
    assert preset_supports_audio(123) is False
    assert preset_supports_audio(["list"]) is False


def test_audio_truthy_non_bool_treated_false():
    # 只有严格 is True 才支持；truthy 但非 bool 不算
    assert preset_supports_audio({"supports_audio": 1}) is False
    assert preset_supports_audio({"supports_audio": "yes"}) is False


# ---------- preset_supports_vision ----------
def test_vision_supports_true():
    assert preset_supports_vision({"supports_vision": True}) is True


def test_vision_supports_false():
    assert preset_supports_vision({"supports_vision": False}) is False


def test_vision_missing_field_false():
    assert preset_supports_vision({"id": "x"}) is False


def test_vision_empty_dict_false():
    assert preset_supports_vision({}) is False


def test_vision_none_false():
    assert preset_supports_vision(None) is False


def test_vision_non_dict_false():
    assert preset_supports_vision("not-a-dict") is False
    assert preset_supports_vision(123) is False
    assert preset_supports_vision(["list"]) is False


def test_vision_truthy_non_bool_treated_false():
    assert preset_supports_vision({"supports_vision": 1}) is False
    assert preset_supports_vision({"supports_vision": "yes"}) is False
