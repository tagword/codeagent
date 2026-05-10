"""Tests for seed.session_title — LLM-driven session title generation."""

from seed.session_title import (
    _strip_assistant_noise_for_title,
    _user_context_for_title,
    _fallback_title_from_users,
)


class TestStripAssistantNoiseForTitle:
    """_strip_assistant_noise_for_title filters out thinking/chain-of-thought."""

    def test_normal_text_preserved(self):
        result = _strip_assistant_noise_for_title("Hello world")
        assert result == "Hello world"

    def test_empty_string(self):
        assert _strip_assistant_noise_for_title("") == ""

    def test_whitespace_only(self):
        assert _strip_assistant_noise_for_title("   \n  ") == ""

    def test_thinking_process_filtered(self):
        result = _strip_assistant_noise_for_title("Thinking Process:\nLet me analyze...")
        assert result == ""

    def test_think_tag_stripped(self):
        result = _strip_assistant_noise_for_title("Some text <think>internal</think> visible")
        assert "<think>" not in result
        assert "visible" in result

    def test_chinese_thinking_filtered(self):
        result = _strip_assistant_noise_for_title("思考过程：\n首先我要理解需求")
        assert result == ""

    def test_chain_of_thought_filtered(self):
        result = _strip_assistant_noise_for_title("Chain of thought: step 1...")
        assert result == ""

    def test_bullet_analyze_filtered(self):
        result = _strip_assistant_noise_for_title("1. ** Analyze the requirements")
        assert result == ""

    def test_only_think_tag(self):
        result = _strip_assistant_noise_for_title("<think>some reasoning</think>")
        assert result == ""

    def test_rstrip_carriage_return(self):
        result = _strip_assistant_noise_for_title("Hello\r\nWorld")
        assert "\\r" not in result
        assert "Hello" in result


class TestUserContextForTitle:
    """_user_context_for_title extracts user messages for title generation."""

    def test_single_user_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = _user_context_for_title(msgs)
        assert "用户: Hello" in result

    def test_ignores_assistant_messages(self):
        msgs = [
            {"role": "assistant", "content": "I'm a bot"},
            {"role": "user", "content": "Hello"},
        ]
        result = _user_context_for_title(msgs)
        assert "用户: Hello" in result
        assert "bot" not in result

    def test_empty_messages(self):
        assert _user_context_for_title([]) == ""

    def test_non_dict_messages_ignored(self):
        msgs = ["just a string", {"role": "user", "content": "Hi"}]
        result = _user_context_for_title(msgs)
        assert "用户: Hi" in result

    def test_max_messages_limit(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = _user_context_for_title(msgs, max_msgs=3)
        assert result.count("用户: msg") == 3

    def test_max_chars_truncation(self):
        long_msg = "a" * 300
        msgs = [{"role": "user", "content": long_msg}]
        result = _user_context_for_title(msgs, max_chars=100)
        assert len(result) < 200  # 100 chars + "用户: " prefix + ellipsis
        assert result.endswith("…")

    def test_chronological_order(self):
        """Returns messages in chronological order (oldest first)."""
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "last"},
        ]
        result = _user_context_for_title(msgs, max_msgs=2)
        # oldest appears first in the string
        assert result.index("first") < result.index("last")

    def test_empty_content_skipped(self):
        msgs = [
            {"role": "user", "content": ""},
            {"role": "user", "content": "actual"},
        ]
        result = _user_context_for_title(msgs)
        assert "用户: actual" in result
        assert "用户: " not in result.replace("用户: actual", "")


class TestFallbackTitleFromUsers:
    """_fallback_title_from_users extracts a short title from user messages."""

    def test_simple_message(self):
        msgs = [{"role": "user", "content": "How do I deploy this app?"}]
        title = _fallback_title_from_users(msgs)
        assert title is not None
        assert "deploy" in title

    def test_empty_messages(self):
        assert _fallback_title_from_users([]) is None

    def test_only_assistant_messages(self):
        msgs = [{"role": "assistant", "content": "Here is the answer..."}]
        assert _fallback_title_from_users(msgs) is None

    def test_truncation(self):
        long = "hello world " * 50
        msgs = [{"role": "user", "content": long}]
        title = _fallback_title_from_users(msgs, max_chars=20)
        assert title is not None
        assert len(title) <= 20

    def test_whitespace_normalized(self):
        msgs = [{"role": "user", "content": "hello    world\nfoo"}]
        title = _fallback_title_from_users(msgs)
        assert title is not None
        assert "   " not in title  # no multi-space
