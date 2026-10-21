"""并发压力测试：验证 run 文件原子写 + 线程同步在真实并发下的正确性。

背景：修复前 run 文件用非原子 write_text，并发 reader 会读到半截 JSON →
JSONDecodeError → run 看似消失。本测试用高并发读写复现压力场景，验证
修复后「零读失败 + 零丢更新」。

不调真实 LLM（用 simulate 模式），纯验证持久化层并发安全。
"""

from __future__ import annotations

import concurrent.futures
import json
import threading

import pytest

import codeagent.server.team_engine as eng


@pytest.fixture(autouse=True)
def _clean_threads():
    yield
    with eng._RUN_THREADS_LOCK:
        threads = list(eng._RUN_THREADS.values())
    for t in threads:
        t.join(timeout=10.0)
    eng.reset_run_threads()


def _isolate(monkeypatch, tmp_path):
    def _td():
        p = tmp_path / "teams"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _rd():
        p = tmp_path / "runs"
        p.mkdir(parents=True, exist_ok=True)
        return p
    monkeypatch.setattr(eng, "_teams_dir", _td)
    monkeypatch.setattr(eng, "_runs_dir", _rd)


def test_concurrent_read_write_no_corruption(monkeypatch, tmp_path):
    """一个 run 被 8 线程并发 update + 8 线程并发 get，全程不得读失败。"""
    _isolate(monkeypatch, tmp_path)
    run = eng.create_run("t1", "input")
    rid = run["id"]

    read_failures = []
    write_errors = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            data = eng.get_run(rid)
            if data is None:
                read_failures.append(1)

    def writer(i):
        try:
            for n in range(30):
                eng.update_run(rid, {f"field_{i}_{n}": n})
        except Exception as e:  # noqa: BLE001
            write_errors.append(str(e))

    readers = [threading.Thread(target=reader) for _ in range(8)]
    for r in readers:
        r.start()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(writer, range(8)))
    stop.set()
    for r in readers:
        r.join(timeout=5)

    assert not read_failures, f"并发下出现 {len(read_failures)} 次读失败（run 看似消失）"
    assert not write_errors, f"并发写异常: {write_errors[:3]}"
    # 最终所有写入都在（无丢更新）
    final = eng.get_run(rid)
    assert final is not None
    for i in range(8):
        assert f"field_{i}_29" in final, f"字段 field_{i}_29 丢失（丢更新）"


def test_many_runs_concurrent_creation(monkeypatch, tmp_path):
    """20 个 run 并发创建 + 并发读，全部可读且内容完整。"""
    _isolate(monkeypatch, tmp_path)

    def make(i):
        r = eng.create_run(f"team{i}", f"input{i}")
        return r["id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        ids = list(pool.map(make, range(20)))

    assert len(set(ids)) == 20, "run id 冲突"
    for rid in ids:
        data = eng.get_run(rid)
        assert data is not None, f"run {rid} 创建后读不到"
        assert data["team_id"].startswith("team")


def test_no_partial_json_ever_observed(monkeypatch, tmp_path):
    """直接验证原子写：高频写时 reader 永远读到合法 JSON。"""
    _isolate(monkeypatch, tmp_path)
    run = eng.create_run("t1", "x")
    rid = run["id"]
    f = eng._runs_dir() / f"{rid}.json"

    bad = []
    stop = threading.Event()

    def raw_reader():
        while not stop.is_set():
            try:
                raw = f.read_text(encoding="utf-8")
                json.loads(raw)  # 必须始终合法
            except FileNotFoundError:
                pass  # 原子替换的瞬时窗口（os.replace 前旧文件仍在，理论不发生）
            except json.JSONDecodeError:
                bad.append(1)

    readers = [threading.Thread(target=raw_reader) for _ in range(6)]
    for r in readers:
        r.start()
    for n in range(200):
        eng.update_run(rid, {"seq": n})
    stop.set()
    for r in readers:
        r.join(timeout=5)

    assert not bad, f"观察到 {len(bad)} 次半截 JSON（非原子写回归）"


def test_wait_for_run_joins_thread(monkeypatch, tmp_path):
    """wait_for_run 必须真正 join 后台线程（返回后 run 已终态）。"""
    _isolate(monkeypatch, tmp_path)
    td = eng._teams_dir()
    (td / "t1.json").write_text(
        json.dumps({"name": "t1", "members": ["a1", "a2"], "mode": "sequential"}),
        encoding="utf-8",
    )
    run = eng.run_team("t1", "input", simulate=True)
    rid = run["id"]
    ok = eng.wait_for_run(rid, timeout=30)
    assert ok, "wait_for_run 超时"
    final = eng.get_run(rid)
    assert final["status"] == "done", f"join 后仍非终态: {final['status']}"
    assert len(final["steps"]) == 2
