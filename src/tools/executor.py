from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict

from src.models_pkg import Tool
from src.tools.exceptions import ToolExecutionError
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Executes tools based on their metadata and arguments.
    """
    
    def __init__(self, registry: ToolRegistry):
        """
        Initialize the tool executor with a registry.
        
        Args:
            registry: ToolRegistry instance containing available tools
        """
        self.registry = registry
    
    def execute(self, tool_name: str, **kwargs: Any) -> Any:
        """
        Execute a tool with the given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments to pass to the tool
        
        Returns:
            Result from tool execution
        
        Raises:
            ToolExecutionError: If tool execution fails
        """
        if not self.registry.exists(tool_name):
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        
        tool = self.registry.get(tool_name)
        handler = self.registry.handlers.get(tool_name)
        
        if not handler:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Handler for tool '{tool_name}' not found"
            )
        
        logger.info(f"Executing tool: {tool_name} with args: {kwargs}")
        
        try:
            result = handler(**kwargs)
            # Support async handlers in sync contexts (CLI/tests). In an active event loop,
            # callers should use execute_async().
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop()
                    raise ToolExecutionError(
                        tool_name=tool_name,
                        message="Async tool called from sync context; use execute_async()",
                    )
                except RuntimeError:
                    result = asyncio.run(result)  # type: ignore[arg-type]
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
        except Exception as e:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=str(e),
                original_error=e
            )

    async def execute_async(self, tool_name: str, **kwargs: Any) -> Any:
        """
        Async-aware execution (preferred under uvicorn / server event loop).
        Supports both sync and async handlers.
        """
        if not self.registry.exists(tool_name):
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        handler = self.registry.handlers.get(tool_name)
        if not handler:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Handler for tool '{tool_name}' not found"
            )
        logger.info(f"Executing tool (async): {tool_name} with args: {kwargs}")
        try:
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
        except Exception as e:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=str(e),
                original_error=e
            )
    
    def execute_with_validation(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Execute a tool with parameter validation.
        
        Args:
            tool_name: Name of the tool to execute
            args: Dictionary of parameter names to values
        
        Returns:
            Result from tool execution
        
        Raises:
            ToolExecutionError: If validation fails or execution fails
        """
        if not self.registry.exists(tool_name):
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        
        tool = self.registry.get(tool_name)
        
        if tool is None:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        
        # Validate parameters
        if tool.parameters:
            self._validate_parameters(tool, args)
        
        return self.execute(tool_name, **args)

    async def execute_with_validation_async(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if not self.registry.exists(tool_name):
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ToolExecutionError(
                tool_name=tool_name,
                message=f"Tool '{tool_name}' not found"
            )
        if tool.parameters:
            self._validate_parameters(tool, args)
        return await self.execute_async(tool_name, **args)
    
    def _validate_parameters(self, tool: Tool, args: Dict[str, Any]) -> None:
        """
        Validate arguments against tool parameter definitions.
        
        Args:
            tool: Tool metadata
            args: Arguments to validate
        
        Raises:
            ToolExecutionError: If validation fails
        """
        required = [
            name for name, params in tool.parameters.items()
            if 'required' in params and params['required']
        ]
        
        for param_name in required:
            if param_name not in args:
                raise ToolExecutionError(
                    tool_name=tool.name,
                    message=f"Missing required parameter: {param_name}"
                )
        
        for param_name in list(args.keys()):
            arg_value = args[param_name]
            if param_name in tool.parameters:
                param_def = tool.parameters[param_name]
                expected_type = param_def.get('type', 'any')
                
                if expected_type == 'string':
                    allow_empty = bool(param_def.get("allow_empty"))
                    is_required = bool(param_def.get("required"))
                    if arg_value is None:
                        if allow_empty or not is_required:
                            args[param_name] = ""
                            continue
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be a string (got null)",
                        )
                    if not isinstance(arg_value, str):
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be a string",
                        )
                    if not allow_empty and arg_value.strip() == "" and is_required:
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be a non-empty string",
                        )
                elif expected_type == 'integer':
                    is_required_int = bool(param_def.get("required"))
                    if arg_value is None:
                        if not is_required_int:
                            del args[param_name]
                            continue
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be an integer (got null)",
                        )
                    if isinstance(arg_value, bool):
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be an integer (got boolean)",
                        )
                    if isinstance(arg_value, float) and arg_value.is_integer():
                        args[param_name] = int(arg_value)
                        continue
                    if isinstance(arg_value, str):
                        stripped = arg_value.strip()
                        if stripped:
                            try:
                                args[param_name] = int(stripped, 10)
                                continue
                            except ValueError:
                                pass
                    if not isinstance(arg_value, int):
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be an integer",
                        )
                elif expected_type == 'boolean':
                    is_required_bool = bool(param_def.get("required"))
                    if arg_value is None:
                        if not is_required_bool:
                            del args[param_name]
                            continue
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be a boolean (got null)",
                        )
                    if isinstance(arg_value, bool):
                        continue
                    if isinstance(arg_value, str):
                        s = arg_value.strip().lower()
                        if s in ("1", "true", "yes", "on"):
                            args[param_name] = True
                            continue
                        if s in ("0", "false", "no", "off", ""):
                            args[param_name] = False
                            continue
                        raise ToolExecutionError(
                            tool_name=tool.name,
                            message=f"Parameter '{param_name}' must be a boolean or yes/no string",
                        )
                    if isinstance(arg_value, int) and arg_value in (0, 1):
                        args[param_name] = bool(arg_value)
                        continue
                    raise ToolExecutionError(
                        tool_name=tool.name,
                        message=f"Parameter '{param_name}' must be a boolean",
                    )



