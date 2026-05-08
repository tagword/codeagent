from __future__ import annotations


import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Set

from seed.tools import ToolRegistry, setup_builtin_tools
from seed.persistence import ensure_session_dir, list_sessions, save_session
from seed.routing import find_commands, get_all_commands, get_command


def _pids_listening_on_port_windows(port: int) -> Set[int]:
    """
    Returns process IDs listening on TCP port using `netstat -ano`.
    Works on Windows; best-effort parsing.
    """
    try:
        cp = subprocess.run(
            ["netstat", "-ano"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_win_no_window_kwargs(),
        )
    except Exception:
        return set()
    out = cp.stdout or ""
    pids: Set[int] = set()
    needle = f":{int(port)}"
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Example:
        # TCP    127.0.0.1:8765   0.0.0.0:0   LISTENING   32352
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid > 0:
            pids.add(pid)
    return pids


def _kill_pid_windows(pid: int) -> bool:
    try:
        cp = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_win_no_window_kwargs(),
        )
        return cp.returncode == 0
    except Exception:
        return False


def _wait_port_released_windows(port: int, timeout_sec: float) -> bool:
    deadline = time.time() + max(0.1, float(timeout_sec))
    while time.time() < deadline:
        if not _pids_listening_on_port_windows(port):
            return True
        time.sleep(0.15)
    return not _pids_listening_on_port_windows(port)


def cmd_restart(args):
    tgt = getattr(args, "restart_cmd", "")
    if tgt != "serve":
        print("Usage: codeagent restart serve [--host ... --port ...]", file=sys.stderr)
        sys.exit(2)

    port = int(getattr(args, "port", 8765))
    timeout_sec = float(getattr(args, "timeout_sec", 5.0))

    # Best effort: stop any existing listeners on this port.
    if os.name == "nt":
        pids = _pids_listening_on_port_windows(port)
        pids.discard(os.getpid())
        if pids:
            print(f"Stopping existing listener(s) on port {port}: {sorted(pids)}")
        for pid in sorted(pids):
            ok = _kill_pid_windows(pid)
            if not ok:
                print(f"Warning: failed to stop pid {pid}", file=sys.stderr)
        _wait_port_released_windows(port, timeout_sec)
    else:
        print(
            "restart serve: automatic stop is only implemented on Windows right now; "
            "continuing to start serve.",
            file=sys.stderr,
        )

    # Start server in current process (foreground).
    cmd_serve(args)

def cmd_run(args):
    """Handle run subcommand."""
    prompt = getattr(args, 'prompt', '')
    if not prompt:
        print("Usage: codeagent run [options] <prompt>")
        sys.exit(1)

    ensure_session_dir()
    session_id = args.save if args.save else f"agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    matched = find_commands(prompt, limit=5)
    matches = [c for c in matched if hasattr(c, 'name') and c]
    
    print("=== CodeAgent Run Result")
    print(f"Session ID: {session_id}")
    print(f"Prompt: {prompt}")
    print(f"Matched commands: {len(matches)}")
    
    for cmd_entry in matched:
        name = cmd_entry.name if hasattr(cmd_entry, 'name') else repr(cmd_entry)
        cmd = get_command(name)
        if cmd:
            print(f" - {name}: {cmd.description}")
    
    if args.save:
        save_session(session_id, [prompt], 0, 0)
        print(f"Session saved to: ~/.codeagent/sessions/{session_id}.json")

def cmd_route(args):
    """Handle route subcommand."""
    prompt = getattr(args, 'prompt', '')
    limit = getattr(args, 'limit', 20)
    
    print("=== CodeAgent Route Result")
    print(f"Query: {prompt}")
    
    matched = find_commands(prompt, limit=limit)
    print(f"Matches found: {len(matched)}")
    
    for cmd in matched[:limit]:
        name = cmd.name if hasattr(cmd, 'name') else repr(cmd)
        desc = cmd.description if hasattr(cmd, 'description') else ""
        print(f" - {name}: {desc}")

def cmd_commands(args):
    """Handle commands subcommand."""
    all_cmds = get_all_commands()
    limit = getattr(args, 'limit', 50)
    result_cmds = all_cmds[:limit]
    
    print("=== CodeAgent Commands")
    print(f"Total commands: {len(result_cmds)}")
    
    for cmd in result_cmds:
        cat = "default"
        if hasattr(cmd, 'category') and cmd.category:
            cat = cmd.category
        if hasattr(cmd, 'name'):
            print(f" [{cat}] {cmd.name}")
            if hasattr(cmd, 'description') and cmd.description:
                print(f"        {cmd.description}")

def cmd_tools(args):
    """Handle tools subcommand."""
    registry = ToolRegistry()
    setup_builtin_tools(registry)
    tools = registry.list_all()
    limit = getattr(args, 'limit', 50)
    result_tools = tools[:limit]
    
    print("=== CodeAgent Tools")
    print(f"Total tools: {len(result_tools)}")
    
    for tool in result_tools:
        print(f" - [basic]: {tool.name} - {tool.description}")

def cmd_summary(args):
    """Handle summary subcommand."""
    session_id = getattr(args, 'session', None)
    
    print("=== CodeAgent Session Summary")
    
    if session_id:
        save_dir = os.path.expanduser("~/.codeagent/sessions")
        file_path = os.path.join(save_dir, f"{session_id}.json")
        
        if not os.path.exists(file_path):
            print(f"Warning: Session file not found: {file_path}")
            sessions = list_sessions()
            print(f"Available sessions: {len(sessions)}")
        else:
            print(f"Session: {session_id}")
            print(f"File: {file_path}")
    else:
        sessions = list_sessions()
        if not sessions:
            print("No saved sessions.")
        print("Sessions directory: ~/.codeagent/sessions/")
        print(f"Found {len(sessions)} sessions.")



"""
CodeAgent CLI - Main entry point
Provides command routing, tool execution, and session management.
"""
import argparse
import sys
import os
import subprocess
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _win_no_window_kwargs() -> Dict[str, Any]:
    """Suppress the black cmd window when this CLI helper runs under a windowed
    parent (e.g. ``CodeAgentTray.exe``). No-op on POSIX."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    si.wShowWindow = 0  # SW_HIDE
    return {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW

def main():
    """Main CLI entry point."""

    from seed.env_config import apply_codeagent_env_from_config

    apply_codeagent_env_from_config()

    parser = argparse.ArgumentParser(
        prog='codeagent',
        description='CodeAgent: Autonomous agent for task execution with command routing and session management',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--version', action='version', version='CodeAgent v1.0.0')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run agent with a prompt')
    run_parser.add_argument('prompt', nargs='?', help='Prompt to execute', default='')
    run_parser.add_argument('--max-turns', type=int, default=8, help='Maximum turns')
    run_parser.add_argument('--budget', type=int, default=2000, help='Token budget')
    run_parser.add_argument('--save', '-s', help='Save session ID')

    # Route command
    route_parser = subparsers.add_parser('route', help='Route prompt to commands')
    route_parser.add_argument('prompt', help='Prompt to route')
    route_parser.add_argument('--limit', type=int, default=20, help='Limit results')

    # Commands command
    cmd_parser = subparsers.add_parser('commands', help='List all commands')
    cmd_parser.add_argument('--query', '-q', help='Filter by query', default=None)
    cmd_parser.add_argument('--limit', '-n', type=int, default=50, help='Limit output')
    cmd_parser.add_argument('--category', '-c', help='Filter by category', default=None)

    # Tools command
    tools_parser = subparsers.add_parser('tools', help='List all tools')
    tools_parser.add_argument('--query', '-i', help='Filter by query')
    tools_parser.add_argument('--limit', '-n', type=int, default=50, help='Limit output')
    tools_parser.add_argument('--simple', '-s', action='store_true', help='Basic tools only')

    # Summary command
    summary_parser = subparsers.add_parser('summary', help='Show session summary')
    summary_parser.add_argument('--session', '-S', help='Session ID')

    # Session command
    sess_parser = subparsers.add_parser('session', help='Manage sessions')
    sess_parser.add_argument('action', choices=['list', 'save', 'load', 'delete', 'help'], help='Action')
    sess_parser.add_argument('session_id', nargs='?', help='Session ID')

    # Interactive chat (command routing only until LLM runtime is wired)
    chat_parser = subparsers.add_parser(
        'chat',
        help='Interactive REPL: use --llm for full tool loop; else command routing only',
    )
    chat_parser.add_argument('--limit', '-n', type=int, default=8, help='Max matches per line (without --llm)')
    chat_parser.add_argument(
        '--session',
        '-S',
        help='LLM chat session id: resume/save transcript under <CODEAGENT_PROJECT_ROOT>/llm_sessions/ (override CODEAGENT_LLM_SESSIONS_DIR)',
    )
    chat_parser.add_argument(
        '--llm',
        action='store_true',
        help='Use CODEAGENT_LLM_BASEURL / CODEAGENT_LLM_MODEL and builtin tools (multi-turn tool loop); optional config/codeagent.env',
    )
    chat_parser.add_argument('--max-tool-rounds', type=int, default=16, help='Max LLM/tool cycles per user line')

    serve_parser = subparsers.add_parser(
        'serve',
        help=(
            'HTTP: GET /, POST /api/chat, WS /ws; optional Web UI token (codeagent webui-token init); '
            'webhooks stay public — pip install codeagent[server]。'
            '默认 --host 0.0.0.0：启动时会打印本机与局域网 URL，便于其它设备打开配置或填写 Webhook。'
        ),
    )
    serve_parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Bind address（0.0.0.0 表示局域网可访问）',
    )
    serve_parser.add_argument('--port', type=int, default=8765, help='Port')

    restart_parser = subparsers.add_parser(
        'restart',
        help='Restart helpers (e.g. restart serve). Tries to stop existing listener first.',
    )
    restart_sub = restart_parser.add_subparsers(dest='restart_cmd', required=True, metavar='target')
    restart_serve = restart_sub.add_parser('serve', help='Restart HTTP server (kill listener on port, then run serve)')
    restart_serve.add_argument('--host', default='0.0.0.0', help='Bind address')
    restart_serve.add_argument('--port', type=int, default=8765, help='Port')
    restart_serve.add_argument(
        '--timeout-sec',
        type=float,
        default=5.0,
        help='How long to wait for port to be released after killing (seconds)',
    )

    cfg_parser = subparsers.add_parser('config', help='Manage Markdown config under config/')
    cfg_sub = cfg_parser.add_subparsers(dest='cfg_cmd', help='Config action')
    cfg_init = cfg_sub.add_parser('init', help='Create default agent.md, identity.md, soul.md, tools.md, user.md')

    wt_parser = subparsers.add_parser(
        "webui-token",
        help="Web UI: create/show/reset access token (local CLI only; file config/codeagent.webui.token)",
    )
    wt_sub = wt_parser.add_subparsers(dest="wt_action", required=True, metavar="action")
    wt_sub.add_parser("init", help="Create token file if missing (fails if file already exists)")
    wt_sub.add_parser("reset", help="Write a new token (invalidates existing browser sessions)")
    wt_sub.add_parser("show", help="Print token from file (environment CODEAGENT_WEBUI_TOKEN is not printed)")

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    cmd = getattr(args, 'command', None)
    if cmd == 'run':
        cmd_run(args)
    elif cmd == 'route':
        cmd_route(args)
    elif cmd == 'commands':
        cmd_commands(args)
    elif cmd == 'tools':
        cmd_tools(args)
    elif cmd == 'summary':
        cmd_summary(args)
    elif cmd == 'session':
        cmd_session(args)
    elif cmd == 'chat':
        cmd_chat(args)
    elif cmd == 'serve':
        cmd_serve(args)
    elif cmd == 'restart':
        cmd_restart(args)
    elif cmd == 'config':
        cmd_config(args)
    elif cmd == "webui-token":
        cmd_webui_token(args)
    else:
        parser.print_help()




import asyncio
import os
import sys
from datetime import datetime

from seed.routing import find_commands


def cmd_chat(args):
    """Interactive loop: routing-only or LLM + tools."""
    if getattr(args, 'llm', False):
        _cmd_chat_llm(args)
        return

    limit = getattr(args, 'limit', 8)
    sess = getattr(args, 'session', None)
    print("CodeAgent chat — 每行输入会做命令匹配（无 --llm）；exit / quit 退出。")
    if sess:
        print(f"Session label: {sess}")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ('exit', 'quit', 'q'):
            break
        matched = find_commands(line, limit=limit)
        if not matched:
            print("  (无匹配命令)")
            continue
        for c in matched:
            desc = c.description if getattr(c, 'description', None) else ''
            print(f"  - {c.name}: {desc}")


def _cmd_chat_llm(args):

    from seed.tools import setup_builtin_tools
    from seed.llm_exec import LLMError
    from seed.llm_presets import llm_executor_from_resolved, resolve_preset
    from seed.agent_context import set_active_llm_session
    from seed.agent_runtime import (
        build_api_projection_messages,
        default_system_prompt,
        maybe_compact_context_messages,
        merge_llm_tail_into_full,
        run_llm_tool_loop,
    )
    from seed.llm_sess import (
        load_or_create_chat_session,
        merge_fresh_system,
        persist_chat_session,
    )
    from seed.mem_bridge import apply_episodic_to_messages
    from seed.session_title import maybe_llm_refresh_session_title

    name = getattr(args, 'session', None) or 'cli-chat'
    max_rounds = getattr(args, 'max_tool_rounds', 16) or 16

    registry, executor = setup_builtin_tools()
    llm = llm_executor_from_resolved(resolve_preset(None))
    from seed.config_plane import project_root as _project_root

    project_root = _project_root()
    chat_sess = load_or_create_chat_session(name)
    fresh_sys = default_system_prompt()
    chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

    print(f"CodeAgent LLM chat — session «{name}» — {len(registry.list_all())} tools — exit / quit 结束。")
    print(f"  API: {llm.baseURL}  model: {llm.model}")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ('exit', 'quit', 'q'):
            break
        chat_sess.messages.append({"role": "user", "content": line})
        try:
            from seed.transcript_store import append_transcript_entries

            append_transcript_entries(name, [chat_sess.messages[-1]], agent_id=None)
        except Exception:
            pass
        max_hist = int(os.environ.get("CODEAGENT_CHAT_USER_ROUNDS", "12"))
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            max_user_rounds=max_hist,
            skills_suffix=None,
        )
        maybe_compact_context_messages(api_msgs, llm)
        apply_episodic_to_messages(api_msgs, project_root, name)
        set_active_llm_session(name)
        try:
            n_before = len(api_msgs)
            reply, _, tools_used, _tool_trace, _loop_meta = asyncio.run(
                run_llm_tool_loop(
                    llm,
                    executor,
                    messages=api_msgs,
                    registry=registry,
                    max_tool_rounds=max_rounds,
                )
            )
            tail = merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before)
            try:
                from seed.transcript_store import append_transcript_entries

                if tail:
                    append_transcript_entries(name, tail, agent_id=None)
            except Exception:
                pass
            print(reply)
            if tools_used:
                print(f"  [tools] {', '.join(tools_used)}")
            try:
                persist_chat_session(chat_sess)
            except Exception:
                pass
            try:
                maybe_llm_refresh_session_title(llm, chat_sess)
            except Exception:
                pass
            if os.environ.get("CODEAGENT_MEMORY_LOG", "1").lower() not in ("0", "false", "no"):
                try:
                    from seed.mem_sys import MemorySystem

                    mem = MemorySystem(base_path=project_root)
                    mem.log_experience(
                        task_id=f"chat-{datetime.now().isoformat()}",
                        outcome=(reply or "")[:2000],
                        tools_used=tools_used,
                        session_id=name,
                    )
                except Exception:
                    pass
        except LLMError as e:
            print(f"[LLM error] {e}")
            chat_sess.messages.pop()
        finally:
            set_active_llm_session(None)


def cmd_webui_token(args):
    import secrets

    from codeagent.web.auth_impl import TOKEN_FILENAME

    # cmd_webui_token can be invoked directly; ensure env file is loaded.
    from seed.env_config import apply_codeagent_env_from_config

    apply_codeagent_env_from_config()
    from seed.config_plane import project_root as _project_root

    root = _project_root()
    cfg = root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    path = cfg / TOKEN_FILENAME
    act = args.wt_action

    if act == "show":
        if not path.is_file():
            print(f"(no token file) {path}")
            if os.environ.get("CODEAGENT_WEBUI_TOKEN", "").strip():
                print("CODEAGENT_WEBUI_TOKEN is set in the environment (value not shown).")
            return
        print(path)
        print(path.read_text(encoding="utf-8").strip())
        return

    if act == "init":
        if path.exists():
            print(f"Already exists: {path}")
            print("Use: codeagent webui-token reset")
            sys.exit(1)
        token = secrets.token_urlsafe(32)
        path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except (OSError, NotImplementedError, AttributeError):
            pass
        print(f"Written: {path}")
        print(f"Token (save it): {token}")
        return

    if act == "reset":
        token = secrets.token_urlsafe(32)
        path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except (OSError, NotImplementedError, AttributeError):
            pass
        print(f"Written: {path}")
        print(f"New token: {token}")
        return




import sys

from seed.persistence import list_sessions, save_session


def cmd_serve(args):
    try:
        from codeagent.server import main as server_main
    except ImportError as e:
        print(f"无法加载 HTTP 服务模块: {e}", file=sys.stderr)
        print(
            "请先安装 Web 依赖，例如在仓库根目录执行: pip install -e '.[server]'",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        server_main(host=args.host, port=args.port)
    except OSError as e:
        print(f"服务启动失败（端口或地址不可用）: {e}", file=sys.stderr)
        print(
            f"可尝试更换端口: codeagent serve --host {args.host} --port {(args.port or 8765) + 1}",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_serve_tray(args):
    print("serve-tray has been removed.", file=sys.stderr)
    sys.exit(1)


def cmd_config(args):
    from seed.config_plane import ensure_default_config_files, project_root

    sub = getattr(args, 'cfg_cmd', None)
    if sub == 'init':
        root = project_root()
        ensure_default_config_files(root)
        ex = root / "config" / "codeagent.env.example"
        print(f"Default Markdown written under: {root / 'config'}")
        print("Tip: optional plugin skills live in config/skills/ directory.")
        if ex.is_file():
            print(f"Context/LLM env template: {ex}  -> copy to config/codeagent.env if you want repo-local settings.")
        return
    print("Usage: codeagent config init")


def cmd_session(args):
    """Handle session subcommand."""
    action = getattr(args, 'action', 'list')
    session_id = getattr(args, 'session_id', None)
    
    if action == 'list':
        sessions = list_sessions()
        print("=== Session List")
        print(f"Total: {len(sessions)}")
        for s in sessions:
            print(f" - {s}")
    elif action == 'help':
        print("Available actions: list, save, load, delete, help")
    elif action == 'delete' and session_id:
        from seed.persistence import delete_session
        if delete_session(session_id):
            print(f"Session deleted: {session_id}")
        else:
            print(f"Session not found: {session_id}")
    elif action == 'save' and session_id:
        save_session(session_id, [], 0, 0)
        print(f"Session saved: {session_id}")
    else:
        print(f"Session action '{action}': invalid or missing arguments.")

# Note: entry points are __main__.py / main.py / cli_pkg, not this file directly