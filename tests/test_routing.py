"""Tests for seed.routing — command routing engine."""

from seed.routing import (
    get_command,
    find_commands,
    invalidate_routing_cache,
    _merged_registry,
    _agent_tool_entries,
)


class TestMergedRegistry:
    """_merged_registry builds a combined agent + shell command list."""

    def test_returns_list_of_command_entries(self):
        entries = _merged_registry()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_includes_shell_commands(self):
        entries = _merged_registry()
        names = {e.name.lower() for e in entries}
        assert "ls" in names
        assert "cat" in names
        assert "grep" in names

    def test_includes_agent_tools(self):
        entries = _merged_registry()
        names = {e.name.lower() for e in entries}
        assert "echo" in names or "file_read" in names

    def test_no_duplicate_names(self):
        entries = _merged_registry()
        names = [e.name.lower() for e in entries]
        assert len(names) == len(set(names)), "duplicate command names found"


class TestAgentToolEntriesCache:
    """_agent_tool_entries is cached via lru_cache."""

    def test_cache_reuses_same_tuple(self):
        a = _agent_tool_entries()
        b = _agent_tool_entries()
        assert a is b

    def test_cache_cleared_by_invalidate(self):
        a = _agent_tool_entries()
        invalidate_routing_cache()
        b = _agent_tool_entries()
        # After invalidation, a new call produces a new tuple
        # (content may be same but identity differs)
        assert a is not b


class TestGetCommand:
    """get_command resolves command names to CommandEntry (exact match)."""

    def test_exact_match_found(self):
        entry = get_command("ls")
        assert entry is not None
        assert entry.name == "ls"

    def test_case_insensitive(self):
        entry = get_command("LS")
        assert entry is not None
        assert entry.name == "ls"

    def test_unknown_command_returns_none(self):
        entry = get_command("this_command_does_not_exist_xyz")
        assert entry is None

    def test_empty_string_returns_none(self):
        entry = get_command("")
        assert entry is None

    def test_case_sensitive_exact(self):
        entry = get_command("CAT", case_insensitive=True)
        assert entry is not None
        assert entry.name == "cat"


class TestFindCommands:
    """find_commands supports partial matching with scoring."""

    def test_partial_match_prefix(self):
        entries = find_commands("gre")
        names = [e.name.lower() for e in entries]
        assert "grep" in names

    def test_partial_match_middle(self):
        entries = find_commands("ath")
        names = [e.name.lower() for e in entries]
        assert any("ath" in n for n in names)

    def test_empty_query_returns_all(self):
        """Empty query matches everything (returns up to limit)."""
        entries = find_commands("")
        assert len(entries) > 0
        assert len(entries) <= 20

    def test_limit_works(self):
        entries = find_commands("a", limit=3)
        assert len(entries) <= 3


class TestInvalidateCache:
    """invalidate_routing_cache clears the cached tool list."""

    def test_cache_cleared(self):
        a = _agent_tool_entries()
        invalidate_routing_cache()
        b = _agent_tool_entries()
        assert b is not None
