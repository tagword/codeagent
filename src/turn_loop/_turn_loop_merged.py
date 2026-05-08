from __future__ import annotations
from __future__ import annotations
from __future__ import annotations




import logging
import os
from typing import Optional, Tuple

from src.commands_pkg import CommandRouter
from src.llm_exec_pkg import LLMAPIExecutor
from src.mem_sys_pkg import MemorySystem
from src.models_pkg import Session, TurnResult, UsageSummary
from src.tools import ToolExecutor, ToolRegistry

logger = logging.getLogger(__name__)


class TurnLoopEngine:
    """
    Core turn loop engine for the autonomous agent.
    
    Handles the main loop:
    1. Receive input
    2. Route to command/tool
    3. Execute and collect results
    4. Track turns and tokens
    5. Update session state
    6. Check termination conditions
    
    Synchronous-only as per requirements.
    """
    
    def __init__(
        self,
        session: Session,
        command_router: CommandRouter,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        config: Optional[TurnLoopConfig] = None,
        llm_executor: Optional[LLMAPIExecutor] = None
    ):
        self.session = session
        self.router = command_router
        self.registry = tool_registry
        self.executor = tool_executor
        self.config = config or TurnLoopConfig()
        # Override llm_executor from constructor if provided
        if llm_executor is not None:
            self.config.llm_executor = llm_executor
        
        # Turn tracking
        self.turn_count = 0
        self.token_usage = UsageSummary()
        self.running = False
        
        # Initialize MemorySystem if running with session
        self.memory_system = None
        if session.id:
            # Get base_path from __file__ to point to project root
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.memory_system = MemorySystem(base_path=base_path)
            # Load memory on session start
            self.memory_system.load_all()
            logger.info(f"MemorySystem initialized for session {session.id[:8]}...")
        
    def _check_turn_limit(self) -> Tuple[bool, Optional[str]]:
        """Check if we should continue or stop based on turn limit"""
        if self.turn_count >= self.config.max_turns:
            return False, f"Max turns ({self.config.max_turns}) reached"
        return True, None
    
    def _check_token_budget(self) -> Tuple[bool, Optional[str]]:
        """Check if we should continue or stop based on token budget"""
        total_tokens = self.token_usage.total_tokens
        if total_tokens >= self.config.token_budget:
            return False, f"Token budget ({self.config.token_budget}) exceeded"
        return True, None
    
    def _should_continue(self) -> Tuple[bool, Optional[str]]:
        """Check all termination conditions"""
        # Check turn limit first
        continue_turns, msg = self._check_turn_limit()
        if not continue_turns:
            return False, msg
        
        # Check token budget
        continue_tokens, msg = self._check_token_budget()
        if not continue_tokens:
            return False, msg
        
        return True, None
    
    def _estimate_turn_token_cost(self, prompt: str, potential_response: Optional[str] = None) -> int:
        """Estimate token cost for a turn"""
        prompt_tokens = estimate_tokens(prompt)
        response_tokens = estimate_tokens(potential_response) if potential_response else 0
        return prompt_tokens + response_tokens
    
    def _update_session_messages(self, role: str, content: str) -> None:
        """Add message to session"""
        self.session.add_message(role, content)
        
    def _record_turn_result(self, turn_result: TurnResult) -> None:
        """Record turn result in session"""
        self.session.add_turn(turn_result)
    
    def _save_session_if_enabled(self) -> None:
        """Save session if auto-save is enabled"""
        if self.config.auto_save:
            import os
            from pathlib import Path

            from src.llm_sess_pkg import llm_sessions_dir
            from src.sess_store_pkg import SessionManager

            raw = os.environ.get("CODEAGENT_SESSION_DIR", "").strip()
            base = str(Path(raw).expanduser().resolve()) if raw else str(llm_sessions_dir())
            manager = SessionManager(base)
            manager.update_session(self.session)
            logger.debug(f"Session auto-saved: {self.session.id}")
    


def run_interactive(self, initial_prompt: Optional[str] = None) -> List[TurnResult]:
    """
    Run interactive turn loop with user input.
    
    Args:
        initial_prompt: Optional first prompt
    
    Returns:
        List of TurnResult objects
    """
    results: List[TurnResult] = []
    self.running = True
    
    print("\n" + "=" * 60)
    print(f"CodeAgent Turn Loop")
    print(f"Session: {self.session.name} ({self.session.id[:8]}...)")
    print(f"Turns: {self.turn_count}/{self.config.max_turns}")
    print(f"Tokens: {self.token_usage.total_tokens}/{self.config.token_budget}")
    print("=" * 60)
    print("Type 'exit' to stop, 'help' for commands")
    print()
    
    # Get initial prompt if provided
    if initial_prompt:
        result = self.run_turn(initial_prompt)
        results.append(result)
    
    # Interactive loop
    while self.running:
        # Check termination conditions
        should_continue, reason = self._should_continue()
        if not should_continue:
            print(f"\nLoop ended: {reason}")
            break
        
        # Get user input
        try:
            user_input = input("[?] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break
        
        if not user_input:
            continue
        
        # Handle special commands
        if user_input.lower() in ['exit', 'quit', 'q']:
            print("Exiting turn loop...")
            self.running = False
            break
        
        if user_input.lower() == 'help':
            print("\nAvailable commands:")
            print("  exit/quit/q - End the session")
            print("  help - Show this help message")
            print("  turns - Show current turn count")
            print("  tokens - Show token usage")
            print("  continue - Continue to next turn")
            print()
            continue
        
        if user_input.lower() == 'turns':
            print(f"\nCurrent turns: {self.turn_count}/{self.config.max_turns}")
            continue
        
        if user_input.lower() == 'tokens':
            print(f"\nToken usage:")
            print(f"  Input:  {self.token_usage.input_tokens}")
            print(f"  Output: {self.token_usage.output_tokens}")
            print(f"  Total:  {self.token_usage.total_tokens}/{self.config.token_budget}")
            continue
        
        if user_input.lower() == 'continue':
            continue
        
        # Execute user input as a turn
        result = self.run_turn(user_input)
        results.append(result)
        
        # Auto-save
        self._save_session_if_enabled()
    
    self.running = False
    self._save_session_if_enabled()
    
    return results

def get_summary(self) -> Dict[str, Any]:
    """
    Get a summary of the turn loop execution.
    
    Returns:
        Dictionary with execution summary
    """
    return {
        'session_id': self.session.id,
        'session_name': self.session.name,
        'turn_count': self.turn_count,
        'turns_executed': self.turn_count,
        'max_turns': self.config.max_turns,
        'tokens': {
            'input': self.token_usage.input_tokens,
            'output': self.token_usage.output_tokens,
            'total': self.token_usage.total_tokens,
            'budget': self.config.token_budget,
            'remaining': max(0, self.config.token_budget - self.token_usage.total_tokens),
        },
        'session_messages': len(self.session.messages),
        'session_turns': len(self.session.turns),
        'running': self.running,
    }

def stop(self) -> None:
    """Stop the turn loop"""
    self.running = False
    logger.info("Turn loop stopped by user")

def shutdown(self) -> None:
    """
    Shutdown the turn loop and save session memory.
    Logs session experience and capabilities to memory system.
    """
    self.running = False
    
    # Log session experience to memory
    if self.memory_system:
        # Get all tools that were used
        tools_used = [tool.name for tool in self.registry.list_all()]
        
        # Get all turns executed
        total_turns = len(self.session.turns)
        total_tokens = self.token_usage.total_tokens
        outcome = f"Session completed: {total_turns} turns, {total_tokens} tokens"
        
        self.memory_system.log_experience(
            task_id=f"session_{self.session.id}",
            outcome=outcome,
            tools_used=tools_used
        )
        
        logger.info(f"Session experience logged to memory for {self.session.id[:8]}...")




"""Turn loop engine for CodeAgent - Core autonomous agent loop"""
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from src.models_pkg import Session, TurnResult, UsageSummary, CommandRoutingResult, Command
from src.commands_pkg import CommandRouter, tokenize_input
from src.tools import ToolRegistry, ToolExecutor, ToolExecutionError, setup_builtin_tools
from src.llm_exec_pkg import LLMAPIExecutor, LLMError
from src.mem_sys_pkg import MemorySystem
from datetime import datetime

logger = logging.getLogger(__name__)


def execute_command_as_tool(cmd: Any, prompt: str, command_args: List[str], executor: 'ToolExecutor') -> Optional[str]:
    """
    Execute a command (which may be a tool) with intelligent parameter parsing.
    
    Args:
        cmd: Command object from CommandRouter
        prompt: User prompt string
        command_args: Parsed command arguments
        executor: ToolExecutor instance
    
    Returns:
        Execution result or None
    """
    tool_name = cmd.name
    
    # Map command arguments based on tool signature
    if tool_name == 'calculate':
        # calculate expression -> calculate(add, 1, 2)
        # Parse: "calculate 2 + 2" -> expression = "2 + 2"
        # Parse: "calculate add 1 2" -> operation="add", a=1, b=2 (fallback)
        expression = ' '.join(command_args) if command_args else ""
        
        # Try to detect if user provided "op a b" format vs "a op b" format
        if len(command_args) >= 3:
            first_arg = command_args[0].lower()
            if first_arg in ['add', 'subtract', 'multiply', 'divide']:
                # Format: "calculate add 1 2"
                operation = command_args[0]
                try:
                    a = int(command_args[1])
                except (ValueError, IndexError):
                    a = 1
                try:
                    b = int(command_args[2])
                except (ValueError, IndexError):
                    b = 1
            else:
                # Format: "calculate 2 + 2" - parse as expression
                # Simple parser for "number op number"
                op_map = {
                    '+': 'add',
                    '-': 'subtract',
                    '*': 'multiply',
                    '/': 'divide'
                }
                parts = expression.split()
                if len(parts) >= 3:
                    try:
                        a = int(parts[0])
                        op = parts[1]
                        b = int(parts[2])
                        operation = op_map.get(op, 'add')
                    except (ValueError, IndexError):
                        operation = 'add'
                        a = 1
                        b = 1
                else:
                    operation = 'add'
                    a = 1
                    b = 1
        else:
            operation = 'add'
            a = 1
            b = 1
            
        return executor.execute_with_validation(tool_name, {
            'operation': operation,
            'a': a,
            'b': b
        })
    
    elif tool_name == 'echo':
        # echo message [prefix] -> echo("hello world", ">>")
        # Parse: "echo hello world" -> command_args = ["hello", "world"]
        if len(command_args) >= 1:
            message = ' '.join(command_args)
            prefix = ""
        else:
            message = prompt.strip('"').strip("'")
            prefix = ""
        return executor.execute(tool_name, message=message, prefix=prefix)
    
    elif tool_name == 'counter':
        # counter count [prefix] -> counter(5, "[Count]")
        # Parse: "counter 5" -> command_args = ["5"]
        if len(command_args) >= 1:
            try:
                count = int(command_args[0])
            except ValueError:
                count = 1
            prefix = command_args[1] if len(command_args) > 1 else "[Count]"
        else:
            count = 1
            prefix = "[Count]"
        return executor.execute(tool_name, count=count, prefix=prefix)
    
    elif tool_name == 'whoami':
        # whoami - no args needed
        return executor.execute(tool_name)
    
    elif tool_name == 'get_session_info':
        # get_session_info - no args needed
        return executor.execute(tool_name)
    
    elif tool_name == 'clear_messages':
        # clear_messages - no args needed
        return executor.execute(tool_name)
    
    elif tool_name == 'reset_session':
        # reset_session - no args needed
        return executor.execute(tool_name)
    
    # Default fallback: try common parameter patterns
    # First try: message string param
    try:
        return executor.execute(tool_name, message=prompt)
    except Exception:
        pass
    
    # Second try: text string param
    try:
        return executor.execute(tool_name, text=prompt)
    except Exception:
        pass
    
    # Third try: query string param
    try:
        return executor.execute(tool_name, query=prompt)
    except Exception:
        pass
    
    # Last try: no args
    return executor.execute(tool_name)


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation (bytes / 4 = approximate tokens for ASCII/UTF-8)
    This is a simplified estimate; production should use actual tokenizer
    """
    return len(text.encode('utf-8')) // 4 if text else 0


class TurnLoopConfig:
    """Configuration for the turn loop engine"""
    
    def __init__(
        self,
        max_turns: int = 8,
        token_budget: int = 2000,
        auto_save: bool = True,
        verbose: bool = True,
        llm_executor: Optional[LLMAPIExecutor] = None
    ):
        self.max_turns = max_turns
        self.token_budget = token_budget
        self.auto_save = auto_save
        self.verbose = verbose
        self.llm_executor = llm_executor





import logging
from typing import Any, Dict, List

from src.llm_exec_pkg import LLMAPIExecutor
from src.models_pkg import Session

logger = logging.getLogger(__name__)


class AutonomousAgent:
    """
    Autonomous agent that uses LLM to drive the turn loop for task completion.
    
    Features:
    - LLM-driven decision making
    - Tool usage for task execution
    - Automated 10-task pipeline
    - Continuous task execution until completion
    """
    
    def __init__(
        self,
        session: Session,
        turn_loop: TurnLoopEngine,
        llm_executor: LLMAPIExecutor
    ):
        """
        Initialize the autonomous agent.
        
        Args:
            session: Session to use for the agent
            turn_loop: TurnLoopEngine instance
            llm_executor: LLMAPIExecutor for LLM calls
        """
        self.session = session
        self.turn_loop = turn_loop
        self.llm_executor = llm_executor
        self.task_count = 0
        self.success_count = 0
        self.failed_count = 0
        
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions for LLM.
        
        Returns:
            List of tool definition dictionaries in LLM-compatible format
        """
        tools = []
        for tool in self.turn_loop.registry.list_all():
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
            
            # Add parameters
            props = {}
            required = []
            if tool.parameters:
                for param_name, param_def in tool.parameters.items():
                    prop = {
                        "type": param_def.get("type", "string"),
                        "description": param_def.get("description", "")
                    }
                    props[param_name] = prop
                    if param_def.get("required", False):
                        required.append(param_name)
            
            tool_def["function"]["parameters"]["properties"] = props
            tool_def["function"]["parameters"]["required"] = required
            
            tools.append(tool_def)
        
        return tools
    
    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for the autonomous agent.
        
        Returns:
            System prompt string
        """
        available_tools = self.turn_loop.registry.list_all()
        tool_names = [t.name for t in available_tools]
        
        system_prompt = f"""You are an autonomous agent capable of using tools to complete tasks.

Your available tools: {', '.join(tool_names)}

For each task, you should:
1. Analyze the task requirements
2. Determine which tool(s) to use
3. Execute the tool(s) with appropriate parameters
4. Verify the result
5. Report completion

Available tools:
"""
        for tool in available_tools:
            system_prompt += f"\n- {tool.name}: {tool.description}"
            if tool.parameters:
                for param_name, param_def in tool.parameters.items():
                    system_prompt += f"\n  - {param_name} ({param_def.get('type', 'any')}): {param_def.get('description', '')}"
        
        system_prompt += """

Always respond with:
- A brief explanation of what you're doing
- The tool name and parameters you're using
- The results received

Continue processing tasks until all are complete."""
        
        return system_prompt
    
    def _create_agent_task(self, task_number: int, task_description: str) -> str:
        """
        Create a well-formatted task specification.
        
        Args:
            task_number: Task number (1-10)
            task_description: Brief task description
        
        Returns:
            Formatted task string
        """
        return f"Task {task_number}: {task_description}"
    
    def _execute_autonomous_turn(self, task_description: str) -> Dict[str, Any]:
        """
        Execute a single autonomous turn for a task.
        
        Args:
            task_description: Task to complete
        
        Returns:
            Dict with success status, message, and error if any
        """
        # Build conversation history
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": task_description}
        ]
        
        # Add existing session messages for context
        for msg in self.session.messages:
            if msg["role"] not in ["system", "user"]:
                continue
            messages.append(msg)
        
        try:
            # Call LLM with tools
            content, metadata = self.llm_executor.generate(
                messages=messages,
                tools=self._get_tool_definitions(),
                max_turns=1,
                temperature=0.7
            )
            
            # Parse LLM response - look for tool calls
            # Expected format: "I will use [tool] with params..." or JSON-like structure
            result = {
                "success": True,
                "content": content,
                "metadata": metadata,
                "tool_calls": metadata.get("tool_calls", [])
            }
            
            if metadata.get("tool_calls"):
                logger.info(f"LLM called tools: {metadata['tool_calls']}")
                result["tool_calls_executed"] = True
            else:
                # No tool calls, just log the content
                logger.info(f"LLM response: {content[:200]}...")
            
            return result
            
        except LLMError as e:
            logger.error(f"LLM error: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": f"Error: {e.message}"
            }
    


def _execute_tool_from_response(self, tool_call: Dict[str, Any]) -> Any:
    """
    Execute a tool call from LLM response.
    
    Args:
        tool_call: Tool call definition from LLM
    
    Returns:
        Tool execution result
    """
    import json
    
    func = tool_call.get("function", {})
    tool_name = func.get("name")
    args_str = func.get("arguments", "{}")
    
    # Parse arguments - handle both dict and string
    try:
        if isinstance(args_str, str):
            args = json.loads(args_str)
        else:
            args = args_str
    except (json.JSONDecodeError, TypeError):
        args = {}
    
    logger.info(f"Executing tool from LLM: {tool_name} with {args}")
    
    try:
        return self.turn_loop.executor.execute(tool_name, **args)
    except ToolExecutionError as e:
        logger.error(f"Tool execution failed: {e}")
        return f"Error: {e.message}"

def run_task(self, task_description: str) -> Dict[str, Any]:
    """
    Run a single task autonomously.
    
    Args:
        task_description: What to do
    
    Returns:
        Dict with task results
    """
    self.task_count += 1
    logger.info(f"Starting task {self.task_count}: {task_description}")
    
    result = self._execute_autonomous_turn(task_description)
    
    if result.get("success"):
        self.success_count += 1
        logger.info(f"Task {self.task_count} completed successfully")
    else:
        self.failed_count += 1
        logger.error(f"Task {self.task_count} failed: {result.get('error')}")
    
    # Add result to session
    self.session.add_message("agent", result.get("content", "No response"))
    
    return result

def run_task_pipeline(self, tasks: List[str]) -> List[Dict[str, Any]]:
    """
    Run a pipeline of tasks autonomously.
    
    Args:
        tasks: List of task descriptions
    
    Returns:
        List of task results
    """
    results = []
    for i, task in enumerate(tasks, 1):
        logger.info(f"Running task {i}/{len(tasks)}")
        result = self.run_task(task)
        results.append({
            "task_number": i,
            "task_description": task,
            "result": result
        })
    
    return results

def _execute_direct_tool(self, task_number: int, tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Directly execute a tool with known parameters for standard pipeline verification.
    
    Args:
        task_number: Task number (1-10)
        tool_name: Tool to execute
        **kwargs: Tool arguments
        
    Returns:
        Dict with score, status, result
    """
    try:
        result = self.turn_loop.executor.execute(tool_name, **kwargs)
        
        # Scoring: 20 points per task
        score = 20
        status = "completed"
        
        return {
            "task_number": task_number,
            "score": score,
            "status": status,
            "result": str(result),
            "tool_used": tool_name
        }
    except Exception as e:
        return {
            "task_number": task_number,
            "score": 0,
            "status": "failed",
            "error": str(e),
            "tool_used": tool_name
        }




from typing import Optional

from src.commands_pkg import CommandRouter
from src.llm_exec_pkg import LLMAPIExecutor
from src.models_pkg import Session
from src.tools import ToolExecutor, ToolRegistry


class AutonomousTurnLoop(TurnLoopEngine):
    """
    Compatibility wrapper to expose the pre-existing name used in tests:
    AutonomousTurnLoop -> TurnLoopEngine
    """

    def __init__(
        self,
        session: Session,
        command_router: CommandRouter,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        config: Optional[TurnLoopConfig] = None,
        llm_executor: Optional[LLMAPIExecutor] = None,
    ):
        super().__init__(session, command_router, tool_registry, tool_executor, config, llm_executor)

