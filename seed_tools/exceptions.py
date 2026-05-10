from typing import Optional


class ToolExecutionError(Exception):
    """Exception raised for tool execution errors"""
    
    def __init__(self, tool_name: str, message: str, original_error: Optional[Exception] = None):
        self.tool_name = tool_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' execution error: {message}")



