from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from seed_tools.models import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing available tools"""
    
    def __init__(self):
        """Initialize the tool registry"""
        self.tools: Dict[str, Tool] = {}
        self.handlers: Dict[str, Callable[..., Any]] = {}
    
    def register(self, tool: Tool, handler: Callable[..., Any]) -> None:
        """
        Register a tool with its handler function.
        
        Args:
            tool: Tool metadata
            handler: Callable function that implements the tool
        """
        if tool.name in self.tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        
        self.tools[tool.name] = tool
        self.handlers[tool.name] = handler
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.
        
        Args:
            name: Name of the tool to unregister
        
        Returns:
            True if unregistered, False if not found
        """
        if name in self.tools:
            del self.tools[name]
            if name in self.handlers:
                del self.handlers[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.
        
        Args:
            name: Name of the tool
        
        Returns:
            Tool if found, None otherwise
        """
        return self.tools.get(name)
    
    def list_all(self) -> List[Tool]:
        """
        Get list of all registered tools.
        
        Returns:
            List of all tools
        """
        return list(self.tools.values())
    
    def count(self) -> int:
        """
        Get count of registered tools.
        
        Returns:
            Number of tools
        """
        return len(self.tools)
    
    def exists(self, name: str) -> bool:
        """
        Check if a tool exists.
        
        Args:
            name: Name of the tool
        
        Returns:
            True if exists, False otherwise
        """
        return name in self.tools
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools with their metadata.
        
        Returns:
            List of tool metadata dictionaries
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "returns": tool.returns,
                "category": getattr(tool, 'category', 'builtin'),
                "version": getattr(tool, 'version', '1.0')
            }
            for tool in self.tools.values()
        ]



