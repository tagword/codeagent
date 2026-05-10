"""Command routing engine with exact and partial matching"""

import re
from functools import lru_cache
from typing import Optional, List
from seed_engine.models import CommandEntry


@lru_cache(maxsize=1)
def _agent_tool_entries() -> tuple:
    """CodeAgent executor tools (claw-style); cached to avoid repeated registration."""
    from seed_tools import setup_builtin_tools

    reg, _ = setup_builtin_tools()
    return tuple(
        CommandEntry(t.name, t.description or "", "agent_tool") for t in reg.list_all()
    )


def invalidate_routing_cache() -> None:
    """Clear cached tool list (e.g. after tests patch tools)."""
    _agent_tool_entries.cache_clear()


def _merged_registry() -> List[CommandEntry]:
    """Agent tools first; shell/unix registry excludes names that collide with agent tools."""
    agent = list(_agent_tool_entries())
    taken = {e.name.lower() for e in agent}
    shell = [c for c in COMMAND_REGISTRY if c.name.lower() not in taken]
    return agent + shell


# 1037 commands from claw-code snapshot - core subset for routing
COMMAND_REGISTRY = [
    CommandEntry("ls", "List directory contents", "filesystem"),
    CommandEntry("pwd", "Print working directory", "filesystem"),
    CommandEntry("cd", "Change directory", "filesystem"),
    CommandEntry("mkdir", "Create directory", "filesystem"),
    CommandEntry("rmdir", "Remove directory", "filesystem"),
    CommandEntry("cp", "Copy files", "filesystem"),
    CommandEntry("mv", "Move files", "filesystem"),
    CommandEntry("rm", "Remove files", "filesystem"),
    CommandEntry("cat", "Concatenate and display files", "filesystem"),
    CommandEntry("head", "Display first lines", "filesystem"),
    CommandEntry("tail", "Display last lines", "filesystem"),
    CommandEntry("grep", "Search text patterns", "text"),
    CommandEntry("sed", "Stream editor", "text"),
    CommandEntry("awk", "Pattern processing", "text"),
    CommandEntry("find", "Find files", "filesystem"),
    CommandEntry("locate", "Find files (database)", "filesystem"),
    CommandEntry("dirname", "Get directory path", "filesystem"),
    CommandEntry("basename", "Get filename", "filesystem"),
    CommandEntry("chmod", "Change permissions", "filesystem"),
    CommandEntry("chown", "Change ownership", "filesystem"),
    CommandEntry("df", "Display disk free", "system"),
    CommandEntry("free", "Display memory", "system"),
    CommandEntry("ps", "Process status", "system"),
    CommandEntry("top", "Display process stats", "system"),
    CommandEntry("kill", "Kill processes", "system"),
    CommandEntry("uname", "Print name", "system"),
    CommandEntry("host", "Display host info", "network"),
    CommandEntry("ifconfig", "Network interface config", "network"),
    CommandEntry("netstat", "Network statistics", "network"),
    CommandEntry("ping", "Network reachability", "network"),
    CommandEntry("traceroute", "Network trace", "network"),
    CommandEntry("curl", "Transfer data", "network"),
    CommandEntry("wget", "Download files", "network"),
    CommandEntry("ssh", "Remote login", "network"),
    CommandEntry("scp", "Copy to remote host", "network"),
    CommandEntry("systemctl", "Control system", "system"),
    CommandEntry("service", "Control service", "system"),
    CommandEntry("cron", "Job scheduler", "system"),
    CommandEntry("nohup", "Run unhupped", "system"),
    CommandEntry("strace", "System call trace", "debug"),
    CommandEntry("lsof", "List open files", "filesystem"),
    CommandEntry("mount", "Mount filesystem", "system"),
    CommandEntry("umount", "Unmount filesystem", "system"),
    CommandEntry("id", "Print id", "system"),
    CommandEntry("passwd", "Change password", "system"),
    CommandEntry("useradd", "Add user", "system"),
    CommandEntry("groupadd", "Add group", "system"),
    CommandEntry("env", "Print environment", "system"),
    CommandEntry("export", "Set environment", "system"),
    CommandEntry("set", "Set variables", "system"),
    CommandEntry("alias", "Define alias", "system"),
    CommandEntry("unalias", "Remove alias", "system"),
    CommandEntry("which", "Find command", "system"),
    CommandEntry("where", "Search command", "system"),
    CommandEntry("type", "Type command", "system"),
    CommandEntry("date", "Print date", "time"),
    CommandEntry("timedelta", "Time difference", "time"),
    CommandEntry("sleep", "Pause execution", "system"),
    CommandEntry("readline", "Read input", "text"),
    CommandEntry("echo", "Print arguments", "text"),
    CommandEntry("print", "Print string", "text"),
    CommandEntry("read", "Read variables", "system"),
    CommandEntry("test", "Evaluate condition", "system"),
    CommandEntry("if", "Conditional", "system"),
    CommandEntry("case", "Case statement", "system"),
    CommandEntry("select", "Menu select", "system"),
    CommandEntry("for", "For loop", "system"),
    CommandEntry("while", "While loop", "system"),
    CommandEntry("until", "Until loop", "system"),
]


def get_all_commands() -> List[CommandEntry]:
    """Return shell register plus agent tools (merged)."""
    return _merged_registry()


def get_command(name: str, case_insensitive: bool = True) -> Optional[CommandEntry]:
    """
    Get exact command match by name.
    
    Arguments:
        name: Command name to find
        case_insensitive: If True, match regardless of case
    
    Returns:
        CommandEntry if found, None otherwise
    """
    target = name.lower() if case_insensitive else name
    for cmd in _merged_registry():
        cmd_name = cmd.name.lower() if case_insensitive else cmd.name
        if cmd_name == target:
            return cmd
    return None


def find_commands(query: str, limit: int = 20, case_insensitive: bool = True) -> List[CommandEntry]:
    """
    Find commands using partial matching with scoring.
    
    Arguments:
        query: Search query string
        limit: Maximum number of results
        case_insensitive: If True, match regardless of case
    
    Returns:
        List of matched CommandEntry sorted by match quality
    """
    return score_entries(query, _merged_registry(), limit=limit, case_insensitive=case_insensitive)


def score_entries(
    query: str,
    entries: List[CommandEntry],
    *,
    limit: int = 20,
    case_insensitive: bool = True,
) -> List[CommandEntry]:
    """
    Score and select best entries using the same heuristic as find_commands().

    Used for routing of tools/commands and other registries (e.g. skills) as an innate capability.
    """
    query_lower = query.lower() if case_insensitive else query
    results = []
    for cmd in entries or []:
        score = 0
        cmd_lower = cmd.name.lower() if case_insensitive else cmd.name

        # Score exact match highest
        if cmd_lower == query_lower:
            score = 100
        # Score prefix match high
        elif cmd_lower.startswith(query_lower):
            score = 80
        # Score contains moderate
        elif query_lower in cmd_lower:
            score = 50

        # Score description match (full query substring)
        cmd_desc_lower = cmd.description.lower() if case_insensitive else cmd.description
        if query_lower in cmd_desc_lower:
            score += 20

        # Word/token overlap (natural language → agent tools/skills)
        tokens = [t for t in re.split(r"[\s,.;:，。；、/]+", query_lower) if len(t) >= 2]
        for tok in tokens[:16]:
            if tok in cmd_lower or tok in cmd_lower.replace("_", ""):
                score += 22
            elif len(tok) >= 3 and tok in cmd_desc_lower:
                score += 14

        if score > 0:
            results.append((score, cmd))

    results.sort(key=lambda x: x[0], reverse=True)
    lim = max(1, min(int(limit), 200))
    return [r[1] for r in results[:lim]]
