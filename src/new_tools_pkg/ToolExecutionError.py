"""
Core MVP Tools for CodeAgent
6 essential tools from claw-code integration
"""
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Exception raised for tool execution errors"""
    pass


# =============================================================================
# Tool 1: file_read - Read file contents
# =============================================================================

def file_read_tool(filepath: str, limit: int = 1000) -> str:
    """
    Read contents of a file.
    
    Args:
        filepath: Path to the file to read
        limit: Maximum lines to return (default: 1000)
    
    Returns:
        File contents as string
    """
    try:
        if not os.path.exists(filepath):
            raise ToolExecutionError(f"File not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Truncate if too large
        lines = content.split('\n')
        if len(lines) > limit:
            content = '\n'.join(lines[:limit]) + f'\n...[{len(lines) - limit} lines truncated]'
        
        return content
    except Exception as e:
        raise ToolExecutionError(f"Failed to read file: {e}")


file_read_tool_def = {
    "name": "file_read",
    "description": "Read contents of a file",
    "parameters": {
        "filepath": {"type": "string", "required": True, "description": "Path to the file to read"},
        "limit": {"type": "integer", "required": False, "description": "Maximum lines to return (default: 1000)"}
    },
    "returns": "string: File contents"
}


# =============================================================================
# Tool 2: file_write - Write contents to a file
# =============================================================================

def file_write_tool(filepath: str, content: str, mode: str = "overwrite") -> str:
    """
    Write content to a file.
    
    Args:
        filepath: Path to the file to write
        content: Content to write
        mode: "overwrite" or "append"
    
    Returns:
        Success message
    """
    try:
        # Ensure parent directory exists
        parent_dir = os.path.dirname(filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        
        # Determine write mode
        if mode == "overwrite":
            write_mode = 'w'
        elif mode == "append":
            write_mode = 'a'
        else:
            raise ToolExecutionError(f"Invalid mode: {mode}. Use 'overwrite' or 'append'")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"Successfully wrote to {filepath} ({len(content)} bytes)"
    except Exception as e:
        raise ToolExecutionError(f"Failed to write file: {e}")


file_write_tool_def = {
    "name": "file_write",
    "description": "Write content to a file",
    "parameters": {
        "filepath": {"type": "string", "required": True, "description": "Path to the file to write"},
        "content": {"type": "string", "required": True, "description": "Content to write"},
        "mode": {"type": "string", "required": False, "description": "Mode: 'overwrite' or 'append' (default: overwrite)"}
    },
    "returns": "string: Success message"
}


# =============================================================================
# Tool 3: file_search - Search for files matching a pattern
# =============================================================================

def file_search_tool(pattern: str, directory: str = ".", max_results: int = 20) -> List[str]:
    """
    Search for files matching a pattern using glob.
    
    Args:
        pattern: Glob pattern to match files (e.g., '*.py', 'test_*')
        directory: Directory to search in (default: current directory)
        max_results: Maximum number of results to return
    
    Returns:
        List of matching file paths
    """
    try:
        import glob as glob_module
        
        search_path = os.path.join(directory, pattern)
        matching_files = glob_module.glob(search_path, recursive=True)
        
        # Limit results
        return matching_files[:max_results]
    except Exception as e:
        raise ToolExecutionError(f"Failed to search files: {e}")


file_search_tool_def = {
    "name": "file_search",
    "description": "Search for files matching a glob pattern",
    "parameters": {
        "pattern": {"type": "string", "required": True, "description": "Glob pattern (e.g., '*.py', 'test_*')"},
        "directory": {"type": "string", "required": False, "description": "Directory to search in (default: current directory)"},
        "max_results": {"type": "integer", "required": False, "description": "Maximum results to return (default: 20)"}
    },
    "returns": "list[str]: Matching file paths"
}


# =============================================================================
# Tool 4: bash_exec - Execute shell commands
# =============================================================================

