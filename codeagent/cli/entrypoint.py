"""CodeAgent Main CLI Entry Point - Clean Implementation"""
import argparse
import sys
from datetime import datetime

# Prefer `codeagent.py` / `python -m codeagent` — this module kept for compatibility.
from .routing import get_all_commands, find_commands
from .persistence import save_session, list_sessions, ensure_session_dir
from seed.tools import ToolRegistry, setup_builtin_tools

def main():
    parser = argparse.ArgumentParser(
        prog='codeagent',
        description="CodeAgent: Autonomous agent for task execution with command routing and session management"
    )
    parser.add_argument('--version', '-v', action='version', version='CodeAgent v1.0.0')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Run command
    run = subparsers.add_parser('run', help='Run agent with prompt')
    run.add_argument('prompt', nargs='?', default='', help='Prompt to execute')
    run.add_argument('--max-turns', type=int, default=8)
    run.add_argument('--budget', type=int, default=2000)
    run.add_argument('--save', '-s', help="Save session ID")

    # Route command
    route = subparsers.add_parser('route', help='Find matching commands')
    route.add_argument('prompt', help='Prompt to route')
    route.add_argument('--limit', '-n', type=int, default=20)

    # Commands command
    cmds = subparsers.add_parser('commands', help='List all commands')
    cmds.add_argument('--limit', '-n', type=int, default=50)
    cmds.add_argument('--query', '-q', help='Filter by query')

    # Tools command
    tools = subparsers.add_parser('tools', help='List all tools')
    tools.add_argument('--limit', '-n', type=int, default=50)

    # Summary command
    sum = subparsers.add_parser('summary', help='Show session summary')
    sum.add_argument('--session', '-S', help='Session ID')

    # Session command
    sess = subparsers.add_parser('session', help='Manage sessions')
    sess.add_argument('action', choices=['list', 'save', 'delete', 'help'])
    sess.add_argument('session_id', nargs='?', help='Session ID')

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cmd = getattr(args, 'command', None)
    if cmd == 'run':
        handle_run(args)
    elif cmd == 'route':
        handle_route(args)
    elif cmd == 'commands':
        handle_commands(args)
    elif cmd == 'tools':
        handle_tools(args)
    elif cmd == 'summary':
        handle_summary(args)
    elif cmd == 'session':
        handle_session(args)
    return 0

def handle_run(args):
    prompt = args.prompt
    if not prompt:
        print("Usage: codeagent run [options] <prompt>")
        sys.exit(1)
    ensure_session_dir()
    session_id = args.save or f"agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    matched = find_commands(prompt, limit=5)
    matches = [m for m in matched if hasattr(m, 'name')]
    print("=== CodeAgent Run Result")
    print(f"Session ID: {session_id}")
    print(f"Prompt: {prompt}")
    print(f"Matched commands: {len(matches)}")
    for c in matches:
        if hasattr(c, 'name'):
            desc = c.description if hasattr(c, 'description') else ""
            print(f" - {c.name}: {desc}")
    if args.save:
        save_session(session_id, [prompt], 0, 0)
        print(f"Session saved: ~/.codeagent/sessions/{session_id}.json")

def handle_route(args):
    prompt = args.prompt
    limit = args.limit
    print("=== CodeAgent Route Result")
    print(f"Query: {prompt}")
    matched = find_commands(prompt, limit=limit)
    print(f"Matches found: {len(matched)}")
    for c in matched[:limit]:
        name = c.name if hasattr(c, 'name') else repr(c)
        desc = c.description if hasattr(c, 'description') else ""
        print(f" - {name}: {desc}")

def handle_commands(args):
    all_cmds = get_all_commands()
    limit = args.limit or 50
    result = all_cmds[:limit]
    print("=== CodeAgent Commands")
    print(f"Total commands: {len(result)}")
    for c in result:
        cat = getattr(c, 'category', 'default')
        if hasattr(c, 'name'):
            print(f" [{cat}] {c.name}")

def handle_tools(args):
    registry = ToolRegistry()
    setup_builtin_tools(registry)
    tools = registry.list_all()
    limit = args.limit or 50
    print("=== CodeAgent Tools")
    print(f"Total tools: {len(tools)}")
    for t in tools[:limit]:
        print(f" - [basic]: {t.name} - {t.description}")

def handle_summary(args):
    session_id = getattr(args, 'session', None)
    print("=== CodeAgent Session Summary")
    sessions = list_sessions()
    print("Sessions directory: ~/.codeagent/sessions/")
    print(f"Found {len(sessions)} sessions")
    if session_id:
        print(f"Searched: {session_id}")

def handle_session(args):
    action = args.action
    session_id = args.session_id
    if action == 'list':
        sessions = list_sessions()
        print("=== Session List")
        print(f"Total: {len(sessions)}")
        for s in sessions:
            print(f" - {s}")
    elif action == 'save' and session_id:
        ensure_session_dir()
        save_session(session_id, [], 0, 0)
        print(f"Session saved: {session_id}")
    elif action == 'delete' and session_id:
        from persistence import delete_session
        if delete_session(session_id):
            print(f"Deleted: {session_id}")
        else:
            print(f"Not found: {session_id}")
    elif action == 'help':
        print("Available actions: list, save, delete, help")

if __name__ == "__main__":
    sys.exit(main() or 0)