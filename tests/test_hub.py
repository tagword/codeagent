"""codeagent.server.hub 消息加载与 SSE 格式化单元测试。

覆盖 load_messages（since_id/agent 过滤/排序/limit）与 _format_sse。
monkeypatch _hub_msgs_path 指向临时文件。
"""
import json

import codeagent.server.hub as hub


def _mk_msgs_file(tmp_path, msgs):
    path = tmp_path / "hub_msgs.jsonl"
    with open(str(path), "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return path


def _patch(monkeypatch, tmp_path, msgs):
    path = _mk_msgs_file(tmp_path, msgs)
    monkeypatch.setattr(hub, "_hub_msgs_path", lambda: path)


def _msg(i, frm="a", to="all", content="hi"):
    return {"id": f"id{i}", "ts": i, "frm": frm, "to": to, "type": "text", "content": content}


# ---------- load_messages ----------
def test_load_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "_hub_msgs_path", lambda: tmp_path / "nope.jsonl")
    assert hub.load_messages() == []


def test_load_newest_first(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_msg(0), _msg(1), _msg(2)])
    msgs = hub.load_messages()
    assert [m["id"] for m in msgs] == ["id2", "id1", "id0"]  # 新在前


def test_load_limit(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_msg(i) for i in range(5)])
    msgs = hub.load_messages(limit=2)
    assert [m["id"] for m in msgs] == ["id4", "id3"]


def test_load_since_id(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_msg(i) for i in range(5)])
    # since id2 → 只返回 id3,id4（新在前）
    msgs = hub.load_messages(since_id="id2")
    assert [m["id"] for m in msgs] == ["id4", "id3"]


def test_load_since_id_not_found_returns_all(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [_msg(0), _msg(1)])
    msgs = hub.load_messages(since_id="nope")
    assert len(msgs) == 2


def test_load_filter_agent_frm_or_to(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [
        _msg(0, frm="a", to="b"),
        _msg(1, frm="c", to="b"),
        _msg(2, frm="b", to="d"),
    ])
    msgs = hub.load_messages(filter_agent="b")
    # 匹配 frm==b 或 to==b：id0(to=b), id1(to=b), id2(frm=b)
    assert len(msgs) == 3


def test_load_skips_corrupt_lines(tmp_path, monkeypatch):
    path = tmp_path / "hub_msgs.jsonl"
    path.write_text('{"id":"ok"}\nnot-json\n{"id":"ok2"}\n', encoding="utf-8")
    monkeypatch.setattr(hub, "_hub_msgs_path", lambda: path)
    msgs = hub.load_messages()
    assert [m["id"] for m in msgs] == ["ok2", "ok"]  # 损坏行被跳过


# ---------- _format_sse ----------
def test_format_sse_structure():
    raw = hub._format_sse({"id": "x1", "ts": 1, "frm": "a", "content": "你好"})
    text = raw.decode("utf-8")
    assert text.startswith("id: x1\n")
    assert "event: message" in text
    assert "data: " in text
    assert text.endswith("\n\n")
    # 中文内容保留（ensure_ascii=False）
    assert "你好" in text


def test_format_sse_missing_id():
    raw = hub._format_sse({"content": "x"})
    assert raw.decode("utf-8").startswith("id: \n")
