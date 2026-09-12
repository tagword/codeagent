"""codeagent.server 长输入持久化 + 摘要截断单元测试。

覆盖 _persist_long_user_input（文件写入/异常容错）与
_summarize_user_input_with_fallback 的超长输入 head+tail 截断。
"""
import pathlib

from codeagent.server import _persist_long_user_input


def _home(tmp_path, monkeypatch):
    # agent_sessions_dir 优先读 SEED_AGENT_SESSIONS_DIR 显式覆盖
    sess_dir = tmp_path / "sessions"
    monkeypatch.setenv("SEED_AGENT_SESSIONS_DIR", str(sess_dir))
    return sess_dir


# ---------- _persist_long_user_input ----------
def test_persist_writes_file(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    p = _persist_long_user_input(agent_id="a1", session_id="s1", text="long input")
    assert p is not None
    fp = pathlib.Path(p)
    assert fp.is_file()
    assert fp.read_text(encoding="utf-8") == "long input"
    assert fp.name.startswith("s1_")
    assert fp.name.endswith(".txt")


def test_persist_returns_none_on_error(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise OSError("denied")

    monkeypatch.setattr("pathlib.Path.mkdir", boom)
    assert _persist_long_user_input(agent_id="a1", session_id="s1", text="x") is None


def test_persist_creates_dir(tmp_path, monkeypatch):
    sess_dir = _home(tmp_path, monkeypatch)
    _persist_long_user_input(agent_id="a1", session_id="s1", text="x")
    # _user_inputs 子目录被创建
    assert (sess_dir / "_user_inputs").is_dir()


# ---------- _summarize_user_input_with_fallback 截断 ----------
class _FakeLLM:
    def __init__(self, captured):
        self.captured = captured

    def generate(self, messages, tools=None, max_tokens=None):
        self.captured["blob"] = messages[1]["content"]
        self.captured["max_tokens"] = max_tokens
        return "摘要结果", {}


def _call_summarize(monkeypatch, raw, max_in=60000):
    captured = {}
    monkeypatch.setattr("seed.core.llm_exec.get_llm_executor", lambda **k: _FakeLLM(captured))
    monkeypatch.setenv("CODEAGENT_USER_INPUT_SUMMARY_BASEURL", "")
    monkeypatch.setenv("CODEAGENT_USER_INPUT_SUMMARY_MODEL", "")
    monkeypatch.setenv("CODEAGENT_USER_INPUT_SUMMARY_MAX_INPUT_CHARS", str(max_in))
    from codeagent.server import _summarize_user_input_with_fallback
    out = _summarize_user_input_with_fallback(
        raw_text=raw, baseurl="http://x", model="m", max_tokens=1000
    )
    return out, captured


def test_summarize_short_input_no_truncation(monkeypatch):
    out, cap = _call_summarize(monkeypatch, "short input")
    assert out == "摘要结果"
    assert cap["blob"] == "short input"
    assert cap["max_tokens"] == 1000


def test_summarize_long_input_truncated_head_tail(monkeypatch):
    raw = "A" * 100000
    out, cap = _call_summarize(monkeypatch, raw, max_in=60000)
    # blob 被截断为 head + 省略标记 + tail
    assert len(cap["blob"]) < len(raw)
    assert "内容过长" in cap["blob"]
    # head 与 tail 都保留
    assert cap["blob"].startswith("A" * 100)
    assert cap["blob"].endswith("A" * 100)


def test_summarize_empty_input(monkeypatch):
    out, cap = _call_summarize(monkeypatch, "   ")
    # 空输入 → blob 空，不截断
    assert cap["blob"] == ""
