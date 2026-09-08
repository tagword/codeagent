"""codeagent.server.self_healing heal() 动作单元测试。

覆盖 heal 在 stuck 时重置 heartbeat、非 stuck 时不动作。
"""
import time

import codeagent.server.self_healing as sh


def _patch_stuck(monkeypatch, tmp_path, status="stuck"):
    hb = tmp_path / "heartbeat"
    if status == "stuck":
        hb.write_text(str(time.time() - 500), encoding="utf-8")  # old → stuck
    else:
        hb.write_text(str(time.time() - 5), encoding="utf-8")  # fresh → alive
    monkeypatch.setattr(sh, "get_heartbeat_path", lambda: hb)
    monkeypatch.setattr(sh, "_heartbeat_timeout", lambda: 180)
    monkeypatch.setattr(sh, "is_enabled", lambda: True)


def test_heal_stuck_resets_heartbeat(tmp_path, monkeypatch):
    _patch_stuck(monkeypatch, tmp_path, "stuck")
    hb = tmp_path / "heartbeat"
    old_val = hb.read_text()
    result = sh.heal()
    assert result["healed"] is True
    assert result["status"] == "stuck"
    # heartbeat 被重置为新时间戳
    new_val = hb.read_text()
    assert new_val != old_val
    assert float(new_val) > float(old_val)
    assert any("heartbeat reset" in a for a in result["actions"])


def test_heal_alive_no_action(tmp_path, monkeypatch):
    _patch_stuck(monkeypatch, tmp_path, "alive")
    hb = tmp_path / "heartbeat"
    before = hb.read_text()
    result = sh.heal()
    assert result["healed"] is False
    assert result["status"] == "alive"
    # 不写 heartbeat
    assert hb.read_text() == before
    assert any("no action" in a for a in result["actions"])


def test_heal_unknown_no_action(tmp_path, monkeypatch):
    # 无 heartbeat 文件 → unknown → 不 heal
    hb = tmp_path / "heartbeat"
    monkeypatch.setattr(sh, "get_heartbeat_path", lambda: hb)
    monkeypatch.setattr(sh, "_heartbeat_timeout", lambda: 180)
    monkeypatch.setattr(sh, "is_enabled", lambda: True)
    result = sh.heal()
    assert result["healed"] is False
    assert result["status"] == "unknown"
