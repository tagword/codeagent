"""codeagent.server.self_healing 健康判定单元测试。

覆盖 heartbeat_age / check_health 的 alive/stuck/unknown 状态逻辑。
用 monkeypatch 控制 heartbeat 文件与 timeout。
"""
import time

import codeagent.server.self_healing as sh


def _set_hb(tmp_path, age_or_none):
    """写 heartbeat 文件：age_or_none=None → 无文件；否则写入 (now - age) 秒前。"""
    hb = tmp_path / "heartbeat"
    if age_or_none is None:
        return hb  # 不创建
    hb.write_text(str(time.time() - age_or_none), encoding="utf-8")
    return hb


def _patch(monkeypatch, tmp_path, hb_age, timeout=180, enabled=True):
    hb = _set_hb(tmp_path, hb_age)
    monkeypatch.setattr(sh, "get_heartbeat_path", lambda: hb)
    monkeypatch.setattr(sh, "_heartbeat_timeout", lambda: timeout)
    monkeypatch.setattr(sh, "is_enabled", lambda: enabled)


# ---------- heartbeat_age ----------
def test_heartbeat_age_never(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, None)
    assert sh.heartbeat_age() == -1


def test_heartbeat_age_recent(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 10)
    age = sh.heartbeat_age()
    assert 9 <= age <= 11


def test_heartbeat_age_corrupt_file(tmp_path, monkeypatch):
    hb = tmp_path / "heartbeat"
    hb.write_text("not-a-number", encoding="utf-8")
    monkeypatch.setattr(sh, "get_heartbeat_path", lambda: hb)
    assert sh.heartbeat_age() == -1


# ---------- check_health ----------
def test_check_health_alive(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 10)  # age 10 < timeout 180
    h = sh.check_health()
    assert h["status"] == "alive"
    assert h["heartbeat_age"] is not None
    assert h["timeout"] == 180
    assert h["healing_enabled"] is True


def test_check_health_stuck(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 500)  # age 500 >= timeout 180
    h = sh.check_health()
    assert h["status"] == "stuck"


def test_check_health_stuck_boundary(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 180)  # age == timeout → stuck
    h = sh.check_health()
    assert h["status"] == "stuck"


def test_check_health_alive_just_under_boundary(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 179.9)  # age < timeout → alive
    h = sh.check_health()
    assert h["status"] == "alive"


def test_check_health_unknown_no_file(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, None)  # 无 heartbeat → age=-1 → unknown
    h = sh.check_health()
    assert h["status"] == "unknown"
    assert h["heartbeat_age"] is None


def test_check_health_custom_timeout(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 50, timeout=30)  # age 50 >= timeout 30 → stuck
    h = sh.check_health()
    assert h["status"] == "stuck"
    assert h["timeout"] == 30


# ---------- diagnose ----------
def test_diagnose_alive(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 10)
    d = sh.diagnose()
    assert d["healthy"] is True
    assert d["status"] == "alive"
    assert any("alive" in f for f in d["findings"])


def test_diagnose_stuck(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, 500)
    d = sh.diagnose()
    assert d["healthy"] is False
    assert d["status"] == "stuck"
    assert any("WARNING" in f for f in d["findings"])
