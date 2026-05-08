"""Tests for seed.persistence — session persistence and token tracking."""

import os
import tempfile
from datetime import datetime

from seed.persistence import (
    SessionTokens,
    SessionData,
    ensure_session_dir,
    CODEAGENT_DIR,
    SESSIONS_DIR,
)


class TestSessionTokens:
    """SessionTokens tracks input/output token usage."""

    def test_default_zero(self):
        st = SessionTokens()
        assert st.input_tokens == 0
        assert st.output_tokens == 0

    def test_custom_values(self):
        st = SessionTokens(input_tokens=100, output_tokens=50)
        assert st.input_tokens == 100
        assert st.output_tokens == 50

    def test_from_dict(self):
        st = SessionTokens.from_dict({"input_tokens": 200, "output_tokens": 75})
        assert st.input_tokens == 200
        assert st.output_tokens == 75

    def test_from_dict_empty(self):
        st = SessionTokens.from_dict({})
        assert st.input_tokens == 0
        assert st.output_tokens == 0

    def test_from_dict_partial(self):
        st = SessionTokens.from_dict({"input_tokens": 99})
        assert st.input_tokens == 99
        assert st.output_tokens == 0


class TestSessionData:
    """SessionData.from_session creates persistence-ready data."""

    def test_from_session_basic(self):
        """Verify with a minimal mock session."""
        class MockSession:
            session_id = "test-session-1"
            messages = ["msg1", "msg2"]
            created_at = datetime(2025, 6, 1, 10, 0, 0)
            turn_count = 3

        sd = SessionData.from_session(MockSession(), tokens_in=500, tokens_out=200)
        assert sd.session_id == "test-session-1"
        assert len(sd.messages) == 2
        assert sd.turn_count == 3
        assert sd.tokens["input_tokens"] == 500
        assert sd.tokens["output_tokens"] == 200

    def test_from_session_timestamps(self):
        class MockSession:
            session_id = "s2"
            messages = []
            created_at = datetime(2025, 1, 1, 0, 0, 0)
            turn_count = 0

        sd = SessionData.from_session(MockSession(), tokens_in=0, tokens_out=0)
        assert sd.created_at == "2025-01-01T00:00:00"
        assert "T" in sd.updated_at  # ISO format


class TestEnsureSessionDir:
    """ensure_session_dir creates the session directory."""

    def test_creates_directory(self):
        # Use a temp dir to avoid clobbering real session data
        with tempfile.TemporaryDirectory() as tmp:
            original_dir = SESSIONS_DIR
            try:
                import seed.persistence as pm
                test_dir = os.path.join(tmp, "sessions")
                pm.SESSIONS_DIR = test_dir
                pm.CODEAGENT_DIR = tmp

                ensure_session_dir()
                assert os.path.isdir(test_dir)
            finally:
                pm.SESSIONS_DIR = original_dir
                pm.CODEAGENT_DIR = CODEAGENT_DIR

    def test_idempotent(self):
        """Calling twice should not raise."""
        with tempfile.TemporaryDirectory() as tmp:
            import seed.persistence as pm
            original_dir = SESSIONS_DIR
            try:
                test_dir = os.path.join(tmp, "sessions")
                pm.SESSIONS_DIR = test_dir
                pm.CODEAGENT_DIR = tmp

                ensure_session_dir()
                ensure_session_dir()  # second call
                assert os.path.isdir(test_dir)
            finally:
                pm.SESSIONS_DIR = original_dir
                pm.CODEAGENT_DIR = CODEAGENT_DIR
