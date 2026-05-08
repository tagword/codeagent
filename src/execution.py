"""Tool execution framework - Handles command execution and tracking"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from src.models_pkg import PortingModule


@dataclass
class ToolExecution:
    """Result of tool execution attempt"""
    success: bool
    handled: bool
    tool_name: str
    result: str
    timestamp: datetime
    error: Optional[str] = None
    payload_size: int = 0
    execution_duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'handled': self.handled,
            'tool_name': self.tool_name,
            'result': self.result,
            'timestamp': self.timestamp.isoformat(),
            'error': self.error,
            'payload_size': self.payload_size,
            'execution_duration': self.execution_duration
        }


@dataclass
class ExecutionContext:
    """Context for tool execution"""
    tool_name: str
    arguments: Dict[str, Any]
    env_vars: Dict[str, str] = field(default_factory=dict)
    timeout: float = 60.0
    working_dir: Optional[str] = None
    
    def with_env(self, key: str, value: str) -> "ExecutionContext":
        new_ctx = ExecutionContext(
            tool_name=self.tool_name,
            arguments=self.arguments,
            env_vars=self.env_vars.copy(),
            timeout=self.timeout,
            working_dir=self.working_dir
        )
        new_ctx.env_vars[key] = value
        return new_ctx

    def with_argument(self, key: str, value: Any) -> "ExecutionContext":
        new_ctx = ExecutionContext(
            tool_name=self.tool_name,
            arguments=self.arguments.copy(),
            env_vars=self.env_vars.copy(),
            timeout=self.timeout,
            working_dir=self.working_dir
        )
        new_ctx.arguments[key] = value
        return new_ctx


class ToolRegistry:
    """Registry of available tools"""
    
    def __init__(self):
        self._tools: Dict[str, PortingModule] = {}
        self._auto_register()
    
    def _auto_register(self):
        """Auto-register common tools"""
        # BashTool - Execute shell commands
        self._tools['BashTool'] = PortingModule(
            name='BashTool',
            description='Execute shell commands',
            category='system'
        )
        
        # FileReadTool - Read file contents
        self._tools['FileReadTool'] = PortingModule(
            name='FileReadTool',
            description='Read file contents',
            category='filesystem'
        )
        
        # FileEditTool - Edit files
        self._tools['FileEditTool'] = PortingModule(
            name='FileEditTool',
            description='Edit file contents',
            category='filesystem'
        )
        
        # FileSystemTool - File system operations
        self._tools['FileSystemTool'] = PortingModule(
            name='FileSystemTool',
            description='File system operations',
            category='filesystem'
        )
    
    def get_tool(self, name: str) -> Optional[PortingModule]:
        """Get tool by name"""
        return self._tools.get(name)
    
    def list_tools(self, category: Optional[str] = None) -> List[PortingModule]:
        """List all tools, optionally filtered by category"""
        if category is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.category == category]


def execute_tool(tool_name: str, payload: str, ctx: Optional[ExecutionContext] = None) -> ToolExecution:
    """
    Execute a tool with the given payload.
    
    Arguments:
        tool_name: Name of the tool to execute
        payload: Tool payload (typically JSON string)
        ctx: Optional execution context with environment
    
    Returns:
        ToolExecution result
    """
    registry = ToolRegistry()
    tool = registry.get_tool(tool_name)
    
    if tool is None:
        return ToolExecution(
            success=False,
            handled=False,
            tool_name=tool_name,
            result=f"Unknown tool: {tool_name}",
            timestamp=datetime.now()
        )
    
    # Mock execution - in real impl would actually execute
    # Here we just return handled status
    return ToolExecution(
        success=True,
        handled=True,
        tool_name=tool_name,
        result=f"Executed: {tool.description}",
        timestamp=datetime.now(),
        payload_size=len(payload)
    )
