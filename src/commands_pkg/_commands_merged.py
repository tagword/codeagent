"""Command routing engine for CodeAgent"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
logger = logging.getLogger(__name__)

class CommandRouter:
    """
    Command routing engine that manages command registration and routing.
    
    Example:
        router = CommandRouter()
        router.add_command(Command(name="run", description="Run agent"))
        router.add_command(Command(name="status", description="Show status"))
        
        result = router.route("run --interactive")
        if result.matched and result.command:
            command_name, args = result.command.name, result.command_args
    """
    
    def __init__(self):
        """Initialize the command router"""
        self.commands: List[Command] = []
    
    def add_command(self, command: Command) -> None:
        """
        Register a command with the router.
        
        Args:
            command: Command to register
        """
        self.commands.append(command)
    
    def add_commands(self, commands: List[Command]) -> None:
        """
        Register multiple commands.
        
        Args:
            commands: List of commands to register
        """
        self.commands.extend(commands)
    
    def remove_command(self, name: str) -> bool:
        """
        Remove a command by name or alias.
        
        Args:
            name: Command name or alias to remove
        
        Returns:
            True if command was removed, False if not found
        """
        for i, cmd in enumerate(self.commands):
            if cmd.name.lower() == name.lower() or any(
                alias.lower() == name.lower() for alias in cmd.aliases
            ):
                self.commands.pop(i)
                return True
        return False
    
    def get_command(self, name: str) -> Optional[Command]:
        """
        Get a command by name or alias.
        
        Args:
            name: Command name or alias
        
        Returns:
            Command if found, None otherwise
        """
        for cmd in self.commands:
            if cmd.name.lower() == name.lower() or any(
                alias.lower() == name.lower() for alias in cmd.aliases
            ):
                return cmd
        return None
    
    def list_commands(self) -> List[Command]:
        """
        Get list of all registered commands.
        
        Returns:
            List of commands
        """
        return self.commands.copy()
    
    def count_commands(self) -> int:
        """
        Get count of registered commands.
        
        Returns:
            Number of commands
        """
        return len(self.commands)
    
    def route(self, input_string: str, fuzzy_threshold: int = 3) -> CommandRoutingResult:
        """
        Route an input string to a command.
        
        Args:
            input_string: Raw input string like "run --interactive session1"
            fuzzy_threshold: Edit distance threshold for fuzzy matching
        
        Returns:
            CommandRoutingResult with matched command or suggestions
        """
        command_name, arguments = tokenize_input(input_string)
        
        if not command_name:
            return CommandRoutingResult(
                matched=False,
                command=None,
                command_args=[],
                error="Empty input"
            )
        
        result = find_command(command_name, self.commands, fuzzy_threshold)
        result.command_args = arguments
        
        return result


"""Command routing engine for CodeAgent"""
"""Command routing engine for CodeAgent"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
logger = logging.getLogger(__name__)

import re
from typing import List, Optional
from src.models_pkg import Command, CommandRoutingResult


def tokenize_input(input_string: str) -> tuple[str, List[str]]:
    """
    Tokenize command input into command name and arguments.
    
    Args:
        input_string: Raw command input like "run --interactive session1"
    
    Returns:
        Tuple of (command_name, list_of_arguments)
    """
    tokens = input_string.strip().split()
    if not tokens:
        return "", []
    
    command_name = tokens[0]
    arguments = tokens[1:] if len(tokens) > 1 else []
    
    return command_name, arguments


def edit_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein edit distance between two strings.
    Used for fuzzy matching of commands.
    
    Args:
        s1: First string
        s2: Second string
    
    Returns:
        Integer edit distance (lower = more similar)
    """
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def fuzzy_match(input_cmd: str, commands: List[Command], threshold: int = 3) -> List[str]:
    """
    Find similar commands using edit distance.
    
    Args:
        input_cmd: Input command that might be misspelled
        commands: List of available commands to match against
        threshold: Maximum edit distance for a valid suggestion
    
    Returns:
        List of suggested command names
    """
    suggestions = []
    input_lower = input_cmd.lower()
    
    for cmd in commands:
        # Check exact match on name or aliases
        if cmd.name.lower() == input_lower or any(
            alias.lower() == input_lower for alias in cmd.aliases
        ):
            return [cmd.name]  # Return exact match as primary
        
        # Check fuzzy match
        distance = edit_distance(input_lower, cmd.name.lower())
        if distance <= threshold:
            suggestions.append((distance, cmd.name))
    
    # Sort by edit distance (closest first) and return unique names
    suggestions.sort(key=lambda x: x[0])
    return [name for _, name in suggestions[:3]] if suggestions else []


def find_command(input_cmd: str, commands: List[Command], fuzzy_threshold: int = 3) -> CommandRoutingResult:
    """
    Find and route to the best matching command.
    
    Args:
        input_cmd: Input command string
        commands: List of available commands
        fuzzy_threshold: Edit distance threshold for fuzzy matching
    
    Returns:
        CommandRoutingResult with matched command or suggestions
    """
    input_lower = input_cmd.lower().strip()
    
    # Step 1: Try exact match
    for cmd in commands:
        if cmd.name.lower() == input_lower:
            return CommandRoutingResult(
                matched=True,
                command=cmd,
                command_args=[]
            )
        
        # Check aliases
        for alias in cmd.aliases:
            if alias.lower() == input_lower:
                return CommandRoutingResult(
                    matched=True,
                    command=cmd,
                    command_args=[],
                    suggestions=[cmd.name]
                )
    
    # Step 2: Try partial prefix match
    prefix_matches = [
        cmd for cmd in commands
        if cmd.name.lower().startswith(input_lower)
        or any(alias.lower().startswith(input_lower) for alias in cmd.aliases)
    ]
    
    if len(prefix_matches) == 1:
        return CommandRoutingResult(
            matched=True,
            command=prefix_matches[0],
            command_args=[]
        )
    
    # Step 3: Fuzzy matching for typos
    suggestions = fuzzy_match(input_cmd, commands, fuzzy_threshold)
    
    # Step 4: Build result
    if prefix_matches:
        return CommandRoutingResult(
            matched=False,
            command=None,
            command_args=[],
            suggestions=[cmd.name for cmd in prefix_matches[:3]],
            error=f"Ambiguous prefix match. Did you mean one of: {', '.join([cmd.name for cmd in prefix_matches[:3]])}?"
        )
    
    if suggestions:
        return CommandRoutingResult(
            matched=False,
            command=None,
            command_args=[],
            suggestions=suggestions,
            error=f"Command not found. Did you mean: {', '.join(suggestions)}?"
        )
    
    # Step 5: No matches at all
    return CommandRoutingResult(
        matched=False,
        command=None,
        command_args=[],
        suggestions=[],
        error=f"Command '{input_cmd}' not found. Use 'commands' to see available commands."
    )


