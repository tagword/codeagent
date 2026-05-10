"""Tests for seed.execution — tool execution framework."""

from datetime import datetime
from seed.execution import ToolExecution, ExecutionContext, ToolRegistry


class TestToolExecution:
    """ToolExecution dataclass and helpers."""

    def test_default_construction(self):
        r = ToolExecution(
            success=True, handled=True,
            tool_name="test_tool", result="ok",
            timestamp=datetime.now(),
        )
        assert r.success is True
        assert r.handled is True
        assert r.tool_name == "test_tool"
        assert r.result == "ok"
        assert r.error is None
        assert r.payload_size == 0
        assert r.execution_duration == 0.0

    def test_to_dict_includes_all_fields(self):
        ts = datetime(2025, 1, 1, 12, 0, 0)
        r = ToolExecution(
            success=False, handled=True,
            tool_name="fail_tool", result="error",
            timestamp=ts,
            error="Something broke",
            payload_size=512,
            execution_duration=1.5,
        )
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "Something broke"
        assert d["payload_size"] == 512
        assert d["execution_duration"] == 1.5
        assert d["timestamp"] == "2025-01-01T12:00:00"

    def test_to_dict_no_error(self):
        ts = datetime.now()
        r = ToolExecution(success=True, handled=True, tool_name="t", result="ok", timestamp=ts)
        d = r.to_dict()
        assert d["error"] is None

    def test_error_is_optional(self):
        ts = datetime.now()
        r = ToolExecution(success=True, handled=True, tool_name="t", result="ok", timestamp=ts)
        assert r.error is None


class TestExecutionContext:
    """ExecutionContext dataclass and builder methods."""

    def test_default_construction(self):
        ctx = ExecutionContext(tool_name="echo", arguments={"msg": "hello"})
        assert ctx.tool_name == "echo"
        assert ctx.arguments == {"msg": "hello"}
        assert ctx.env_vars == {}
        assert ctx.timeout == 60.0
        assert ctx.working_dir is None

    def test_with_env_creates_new_context(self):
        ctx = ExecutionContext(tool_name="bash", arguments={})
        ctx2 = ctx.with_env("PATH", "/usr/bin")
        assert ctx2.env_vars == {"PATH": "/usr/bin"}
        # original unchanged
        assert ctx.env_vars == {}

    def test_with_env_chains_multiple(self):
        ctx = ExecutionContext(tool_name="t", arguments={})
        ctx2 = ctx.with_env("A", "1").with_env("B", "2")
        assert ctx2.env_vars == {"A": "1", "B": "2"}

    def test_with_argument_creates_new_context(self):
        ctx = ExecutionContext(tool_name="t", arguments={"x": 1})
        ctx2 = ctx.with_argument("y", 2)
        assert ctx2.arguments == {"x": 1, "y": 2}
        assert ctx.arguments == {"x": 1}  # unchanged

    def test_with_argument_overwrites(self):
        ctx = ExecutionContext(tool_name="t", arguments={"k": "old"})
        ctx2 = ctx.with_argument("k", "new")
        assert ctx2.arguments["k"] == "new"

    def test_env_vars_are_copied_not_shared(self):
        ctx = ExecutionContext(tool_name="t", arguments={})
        ctx2 = ctx.with_env("K", "V")
        ctx2.env_vars["K"] = "modified"
        # original not affected
        assert ctx.env_vars.get("K") is None


class TestToolRegistry:
    """ToolRegistry auto-registers common tools."""

    def test_init_creates_registry(self):
        reg = ToolRegistry()
        assert reg is not None

    def test_get_tool_returns_tool(self):
        reg = ToolRegistry()
        tool = reg.get_tool("BashTool")
        assert tool is not None
        assert tool.name == "BashTool"

    def test_get_tool_unknown_returns_none(self):
        reg = ToolRegistry()
        tool = reg.get_tool("NonExistentTool")
        assert tool is None

    def test_list_tools_returns_all(self):
        reg = ToolRegistry()
        tools = reg.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert any(t.name == "BashTool" for t in tools)

    def test_list_tools_filter_by_category(self):
        reg = ToolRegistry()
        tools = reg.list_tools(category="system")
        assert all(t.category == "system" for t in tools)
        assert any(t.name == "BashTool" for t in tools)

    def test_list_tools_filter_no_match(self):
        reg = ToolRegistry()
        tools = reg.list_tools(category="nonexistent")
        assert tools == []
