from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

from seed_tools import setup_builtin_tools

from seed.core.persistence import ensure_session_dir, list_sessions, save_session
from seed.core.routing import find_commands, get_all_commands, get_command


def cmd_restart(args):
    tgt = getattr(args, "restart_cmd", "")
    if tgt != "serve":
        print("Usage: codeagent restart serve [--host ... --port ...]", file=sys.stderr)
        sys.exit(2)

    port = int(getattr(args, "port", 8765))
    timeout_sec = float(getattr(args, "timeout_sec", 5.0))

    from codeagent.core.process_ports import stop_listeners_on_port

    stopped = stop_listeners_on_port(
        port,
        timeout_sec=timeout_sec,
        exclude_pid=os.getpid(),
        log=print,
    )
    if not stopped and os.name != "nt":
        import shutil

        if not shutil.which("lsof") and not shutil.which("ss") and not shutil.which("fuser"):
            print(
                "restart serve: install lsof (macOS) or iproute2/ss (Linux) "
                "to stop the previous listener automatically.",
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
        from seed.core.llm_sess import agent_sessions_dir

        print(f"Session saved to: {agent_sessions_dir() / f'{session_id}.json'}")

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
    registry, _executor = setup_builtin_tools()
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

    from seed.core.llm_sess import agent_sessions_dir, list_stored_sessions_meta

    if session_id:
        from codeagent.core import env as ca_env

        aid = ca_env.default_agent_id()
        file_path = agent_sessions_dir(aid) / f"{session_id}.json"

        if not file_path.is_file():
            print(f"Warning: Session file not found: {file_path}")
            rows = list_stored_sessions_meta(limit=50, agent_id=aid)
            print(f"Available chat sessions: {len(rows)}")
        else:
            print(f"Session: {session_id}")
            print(f"File: {file_path}")
    else:
        sessions = list_sessions()
        if not sessions:
            print("No saved sessions (legacy QueryEngine store).")
        print(f"Chat sessions directory: {agent_sessions_dir()}")
        rows = list_stored_sessions_meta(limit=200)
        print(f"Stored chat sessions: {len(rows)}")
        print(f"Legacy persistence sessions: {len(sessions)}")



"""
CodeAgent CLI - Main entry point
Provides command routing, tool execution, and session management.
"""
import argparse  # noqa: E402
from typing import Any  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _win_no_window_kwargs() -> dict[str, Any]:
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

    from codeagent.core.bootstrap import bootstrap_codeagent_runtime

    bootstrap_codeagent_runtime()

    parser = argparse.ArgumentParser(
        prog='codeagent',
        description='CodeAgent: Autonomous agent for task execution with command routing and session management',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--version', action='version', version='CodeAgent v1.1.0')
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
    sess_parser = subparsers.add_parser('session', help='Manage chat sessions (agents/<id>/sessions/)')
    sess_parser.add_argument(
        'action',
        choices=['list', 'migrate', 'delete', 'audit-list', 'audit-show', 'help'],
        help='Action',
    )
    sess_parser.add_argument(
        '--seq',
        type=int,
        default=None,
        help='With audit-show: snapshot sequence number from audit-list',
    )
    sess_parser.add_argument(
        '--project-id',
        default=None,
        help='Project id when session lives under projects-data/<id>/sessions/',
    )
    sess_parser.add_argument('session_id', nargs='?', help='Session ID (for delete)')
    sess_parser.add_argument(
        '--agent-id',
        default=None,
        help='Agent id (default: CODEAGENT_AGENT_ID or default)',
    )
    sess_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='With migrate: print planned moves without writing',
    )

    # Interactive chat (command routing only until LLM runtime is wired)
    chat_parser = subparsers.add_parser(
        'chat',
        help='Interactive REPL: use --llm for full tool loop; else command routing only',
    )
    chat_parser.add_argument('--limit', '-n', type=int, default=8, help='Max matches per line (without --llm)')
    chat_parser.add_argument(
        '--session',
        '-S',
        help='Chat session id: resume/save under agents/<agent>/sessions (override SEED_AGENT_SESSIONS_DIR or SEED_LLM_SESSIONS_DIR)',
    )
    chat_parser.add_argument(
        '--llm',
        action='store_true',
        help='Use SEED_LLM_BASEURL / SEED_LLM_MODEL (aliases CODEAGENT_*) and builtin tools; optional config/seed.env',
    )
    chat_parser.add_argument('--max-tool-rounds', type=int, default=16, help='Max LLM/tool cycles per user line')
    chat_parser.add_argument(
        '--image',
        action='append',
        metavar='PATH',
        help='Attach image/document file (repeatable); included with next user line',
    )
    chat_parser.add_argument(
        '--image-dir',
        metavar='PATH',
        help='Stage all images under directory (or reference with --image-dir-ref)',
    )
    chat_parser.add_argument(
        '--image-pattern',
        help='Glob patterns with --image-dir, e.g. "*.png,*.jpg"',
    )
    chat_parser.add_argument(
        '--image-dir-ref',
        action='store_true',
        help='Write [image_dir:path] reference instead of copying files',
    )
    chat_parser.add_argument(
        '--vision-llm',
        metavar='PRESET_ID',
        help='Vision preset for vision_analyze when sending images (or CODEAGENT_VISION_PRESET_ID)',
    )
    chat_parser.add_argument(
        '--image-gen-llm',
        metavar='PRESET_ID',
        help='Image generation preset for image_generate (or CODEAGENT_IMAGE_GEN_PRESET_ID)',
    )
    chat_parser.add_argument(
        '--audio-llm',
        metavar='PRESET_ID',
        help='Audio transcription preset for audio_transcribe (or CODEAGENT_AUDIO_PRESET_ID)',
    )
    chat_parser.add_argument(
        '--music-llm',
        metavar='PRESET_ID',
        help='Music generation preset for music_generate (or CODEAGENT_MUSIC_GEN_PRESET_ID)',
    )
    chat_parser.add_argument(
        '--video-gen-llm',
        metavar='PRESET_ID',
        help='Video generation preset for video_generate (or CODEAGENT_VIDEO_GEN_PRESET_ID)',
    )

    serve_parser = subparsers.add_parser(
        'serve',
        help=(
            'HTTP: GET /, POST /api/chat, WS /ws; optional Web UI token (codeagent webui-token init); '
            'webhooks. 默认 --host 0.0.0.0：启动时会打印本机与局域网 URL，便于其它设备打开配置或填写 Webhook。'
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
    cfg_sub.add_parser('init', help='Create default agent.md, identity.md, soul.md, tools.md, user.md')

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




import asyncio  # noqa: E402
import contextlib  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402


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


def _cli_audio_preset_id(args) -> str:
    from codeagent.core import env as ca_env

    pid = (getattr(args, 'audio_llm', None) or '').strip()
    if pid:
        return pid
    return ca_env.pick_default('', 'CODEAGENT_AUDIO_PRESET_ID').strip()


def _cli_image_gen_preset_id(args) -> str:
    from codeagent.core import env as ca_env

    pid = (getattr(args, 'image_gen_llm', None) or '').strip()
    if pid:
        return pid
    return ca_env.pick_default('', 'CODEAGENT_IMAGE_GEN_PRESET_ID').strip()


def _cli_music_preset_id(args) -> str:
    from codeagent.core import env as ca_env

    pid = (getattr(args, 'music_llm', None) or '').strip()
    if pid:
        return pid
    return ca_env.pick_default('', 'CODEAGENT_MUSIC_GEN_PRESET_ID').strip()


def _cli_video_gen_preset_id(args) -> str:
    from codeagent.core import env as ca_env

    pid = (getattr(args, 'video_gen_llm', None) or '').strip()
    if pid:
        return pid
    return ca_env.pick_default('', 'CODEAGENT_VIDEO_GEN_PRESET_ID').strip()


def _cli_vision_preset_id(args) -> str:
    from codeagent.core import env as ca_env

    vid = (getattr(args, 'vision_llm', None) or '').strip()
    if vid:
        return vid
    return ca_env.pick_default('', 'CODEAGENT_VISION_PRESET_ID').strip()


def _cli_stage_path_attachment(path: str, *, agent_id: str, session_id: str):
    from pathlib import Path

    import mimetypes

    from codeagent.core.attachments import save_attachment

    p = Path(path).expanduser()
    if not p.is_file():
        print(f'  [warn] not a file: {path}')
        return None
    try:
        raw = p.read_bytes()
        mime = mimetypes.guess_type(str(p))[0] or ''
        return save_attachment(
            agent_id=agent_id,
            session_id=session_id,
            raw_bytes=raw,
            filename=p.name,
            mime=mime,
        )
    except Exception as e:
        print(f'  [warn] attach failed {path}: {e}')
        return None


def _cli_startup_attachments(args, *, agent_id: str, session_id: str, project_root):
    from pathlib import Path

    from codeagent.core import env as ca_env
    from codeagent.core.attachments import scan_image_directory

    metas = []
    image_dir_tag = ''
    for path in getattr(args, 'image', None) or []:
        meta = _cli_stage_path_attachment(path, agent_id=agent_id, session_id=session_id)
        if meta:
            metas.append(meta)
            print(f'  [attach] {meta.filename} → {meta.id}')

    image_dir = (getattr(args, 'image_dir', None) or '').strip()
    if image_dir:
        if getattr(args, 'image_dir_ref', False):
            rel = image_dir.replace('\\', '/').lstrip('/')
            mx = ca_env.pick_int(32, 'CODEAGENT_ATTACHMENTS_DIR_MAX_FILES')
            image_dir_tag = f'[image_dir:{rel} max={mx}]'
            print(f'  [image-dir-ref] {image_dir_tag}')
        else:
            pattern = (getattr(args, 'image_pattern', None) or '').strip() or None
            try:
                paths, truncated = scan_image_directory(
                    Path(project_root),
                    image_dir,
                    pattern=pattern,
                )
            except ValueError as e:
                print(f'  [warn] image-dir: {e}')
                paths, truncated = [], False
            for p in paths:
                meta = _cli_stage_path_attachment(str(p), agent_id=agent_id, session_id=session_id)
                if meta:
                    metas.append(meta)
            if metas:
                print(f'  [image-dir] staged {len(metas)} file(s)' + (' (truncated)' if truncated else ''))
            elif not truncated:
                print(f'  [warn] no images found in {image_dir}')
    return metas, image_dir_tag


def _cli_handle_slash_attach(line: str, *, agent_id: str, session_id: str, project_root):
    """Return (handled, attachments, image_dir_tag, message_text)."""
    from pathlib import Path

    from codeagent.core import env as ca_env
    from codeagent.core.attachments import scan_image_directory

    low = line.strip().lower()
    if low in ('/clear-vision', '/clear_vision'):
        return 'clear_vision', [], '', ''
    if line.startswith('/attach-dir '):
        path = line[len('/attach-dir '):].strip()
        if not path:
            print('  usage: /attach-dir <path>')
            return True, [], '', ''
        mx = ca_env.pick_int(32, 'CODEAGENT_ATTACHMENTS_DIR_MAX_FILES')
        tag = f'[image_dir:{path.replace(chr(92), "/").lstrip("/")} max={mx}]'
        print(f'  [image-dir-ref] {tag}')
        return True, [], tag, ''
    if line.startswith('/attach '):
        path = line[len('/attach '):].strip()
        if not path:
            print('  usage: /attach <path>')
            return True, [], '', ''
        meta = _cli_stage_path_attachment(path, agent_id=agent_id, session_id=session_id)
        if meta:
            print(f'  [attach] {meta.filename} → {meta.id}')
            return True, [meta], '', ''
        return True, [], '', ''
    return False, [], '', line


def _cmd_chat_llm(args):

    from seed_tools import setup_builtin_tools

    from seed.core.agent_context import (
        set_active_agent_id,
        set_active_audio_preset,
        set_active_image_gen_preset,
        set_active_llm_session,
        set_active_vision_preset,
        set_active_music_preset,
        set_active_video_gen_preset,
    )
    from seed.core.agent_runtime import (
        build_api_projection_messages,
        maybe_compact_context_messages,
        merge_llm_tail_into_full,
        persist_compact_summary,
        run_llm_tool_loop,
        strip_ephemeral_message_fields,
    )
    from codeagent.runtime.prompt_enrichment import (
        build_skills_suffix,
        fresh_system_prompt,
        get_cached_system_prompt,
        record_chat_turn_diary,
    )
    from seed.core.llm_exec import LLMError
    from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
    from seed.core.llm_sess import (
        load_or_create_chat_session,
        merge_fresh_system,
        persist_chat_session,
    )
    from seed.core.mem_bridge import finalize_episodic_for_llm
    from seed.integrations.session_title import maybe_llm_refresh_session_title

    name = getattr(args, 'session', None) or 'cli-chat'
    max_rounds = getattr(args, 'max_tool_rounds', 16) or 16

    registry, executor = setup_builtin_tools()
    llm = llm_executor_from_resolved(resolve_preset(None))
    from seed.core.config_plane import project_root as _project_root

    project_root = _project_root()
    from codeagent.core import env as ca_env

    agent_id = ca_env.default_agent_id()
    vision_preset_id = _cli_vision_preset_id(args)
    image_gen_preset_id = _cli_image_gen_preset_id(args)
    audio_preset_id = _cli_audio_preset_id(args)
    music_preset_id = _cli_music_preset_id(args)
    video_gen_preset_id = _cli_video_gen_preset_id(args)
    chat_sess = load_or_create_chat_session(name, agent_id)
    fresh_sys = get_cached_system_prompt(chat_sess, agent_id=agent_id)
    chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

    pending_attachments, pending_dir_tag = _cli_startup_attachments(
        args,
        agent_id=agent_id,
        session_id=name,
        project_root=project_root,
    )

    print(f"CodeAgent LLM chat — session «{name}» — {len(registry.list_all())} tools — exit / quit 结束。")
    print(f"  API: {llm.baseURL}  model: {llm.model}")
    if vision_preset_id:
        print(f"  Vision preset: {vision_preset_id}")
    if image_gen_preset_id:
        print(f"  Image gen preset: {image_gen_preset_id}")
    if audio_preset_id:
        print(f"  Audio preset: {audio_preset_id}")
    if music_preset_id:
        print(f"  Music preset: {music_preset_id}")
    if video_gen_preset_id:
        print(f"  Video gen preset: {video_gen_preset_id}")
    print("  命令: /attach <path>  /attach-dir <path>  /clear-vision")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line and not pending_attachments and not pending_dir_tag:
            continue
        if line.lower() in ('exit', 'quit', 'q'):
            break

        slash_atts: list = []
        slash_dir_tag = ''
        message_text = line
        if line.startswith('/'):
            handled, slash_atts, slash_dir_tag, message_text = _cli_handle_slash_attach(
                line,
                agent_id=agent_id,
                session_id=name,
                project_root=project_root,
            )
            if handled == 'clear_vision':
                if isinstance(chat_sess.metadata, dict):
                    chat_sess.metadata.pop('vision_context', None)
                print('  视觉上下文已清除')
                continue
            if handled is True and not slash_atts and not slash_dir_tag:
                continue
        else:
            handled = False

        if slash_atts:
            pending_attachments.extend(slash_atts)
        if slash_dir_tag:
            pending_dir_tag = slash_dir_tag

        from codeagent.core.attachments import (
            build_user_message,
            message_has_audio_attachments,
            message_has_image_attachments,
            message_has_video_attachments,
        )
        from codeagent.core.audio_models import preset_supports_audio_id
        from codeagent.core.vision_models import preset_supports_vision_id

        user_msg = build_user_message(
            message_text,
            pending_attachments,
            image_dir_tag=pending_dir_tag,
        )
        from codeagent.core.image_understanding import image_attachment_allowed, video_attachment_allowed

        if message_has_image_attachments(user_msg) or pending_dir_tag:
            if not image_attachment_allowed(vision_preset_id or ""):
                print(
                    '[error] 发送图片需要 --vision-llm（supports_vision）'
                    ' 或已配置 MiniMax MCP（understand_image）'
                )
                continue
        if message_has_video_attachments(user_msg):
            if not video_attachment_allowed(vision_preset_id or ""):
                print('[error] 发送视频需要有效的 --vision-llm 或 CODEAGENT_VISION_PRESET_ID')
                continue
        if message_has_audio_attachments(user_msg):
            if not audio_preset_id or not preset_supports_audio_id(audio_preset_id):
                print('[error] 发送音频需要有效的 --audio-llm 或 CODEAGENT_AUDIO_PRESET_ID')
                continue

        pending_attachments = []
        pending_dir_tag = ''

        chat_sess.messages.append(user_msg)
        user_text = str(user_msg.get('content') or '')
        max_hist = ca_env.pick_int(12, ca_env.CHAT_USER_ROUNDS)
        from codeagent.core.attachments import content_text_for_skills

        _skills_suffix = build_skills_suffix(agent_id, user_text=content_text_for_skills(user_text))
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            max_user_rounds=max_hist,
            skills_suffix=_skills_suffix,
        )
        compact_result = maybe_compact_context_messages(api_msgs, llm)
        persist_compact_summary(chat_sess.messages, compact_result)
        strip_ephemeral_message_fields(api_msgs)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        finalize_episodic_for_llm(
            api_msgs,
            chat_sess.metadata,
            agent_id=agent_id,
            session_id=name,
            project_id=None,
            compact_happened=compact_result is not None,
        )
        set_active_llm_session(f'{agent_id}::{name}')
        set_active_agent_id(agent_id)
        set_active_vision_preset(vision_preset_id or None)
        set_active_image_gen_preset(image_gen_preset_id or None)
        set_active_audio_preset(audio_preset_id or None)
        set_active_music_preset(music_preset_id or None)
        set_active_video_gen_preset(video_gen_preset_id or None)
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
            print(reply)
            if tools_used:
                print(f"  [tools] {', '.join(tools_used)}")
            with contextlib.suppress(Exception):
                persist_chat_session(chat_sess)
            with contextlib.suppress(Exception):
                maybe_llm_refresh_session_title(llm, chat_sess)
            with contextlib.suppress(Exception):
                record_chat_turn_diary(
                    agent_id,
                    user_text=user_text,
                    reply=reply or "",
                    tools_used=tools_used,
                )
            if os.environ.get("CODEAGENT_MEMORY_LOG", "1").lower() not in ("0", "false", "no"):
                try:
                    from seed.core.mem_sys import MemorySystem

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
            set_active_vision_preset(None)
            set_active_image_gen_preset(None)
            set_active_audio_preset(None)
            set_active_agent_id(None)


def cmd_webui_token(args):
    import secrets

    from codeagent.web.auth_impl import TOKEN_FILENAME

    # cmd_webui_token can be invoked directly; ensure env file is loaded.
    from codeagent.core.bootstrap import bootstrap_codeagent_runtime

    bootstrap_codeagent_runtime()
    from seed.core.config_plane import project_root as _project_root

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
        with contextlib.suppress(OSError, NotImplementedError, AttributeError):
            os.chmod(path, 0o600)
        print(f"Written: {path}")
        print(f"Token (save it): {token}")
        return

    if act == "reset":
        token = secrets.token_urlsafe(32)
        path.write_text(token + "\n", encoding="utf-8")
        with contextlib.suppress(OSError, NotImplementedError, AttributeError):
            os.chmod(path, 0o600)
        print(f"Written: {path}")
        print(f"New token: {token}")
        return




import sys  # noqa: E402


def cmd_serve(args):
    try:
        from codeagent.server import main as server_main
    except ImportError as e:
        print(f"无法加载 HTTP 服务模块: {e}", file=sys.stderr)
        print(
            "请确认已安装 server 依赖: pip install 'codeagent'（默认已包含 starlette + uvicorn）",
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
    from seed.core.config_plane import ensure_default_config_files, project_root

    sub = getattr(args, 'cfg_cmd', None)
    if sub == 'init':
        root = project_root()
        ensure_default_config_files(root)
        ex = root / "config" / "seed.env.example"
        print(f"Default Markdown written under: {root / 'config'}")
        print("Tip: optional plugin skills live in config/skills/ directory.")
        if ex.is_file():
            print(f"Context/LLM env template: {ex}  -> copy to config/seed.env if you want repo-local settings.")
        return
    print("Usage: codeagent config init")


def cmd_session(args):
    """Handle session subcommand (Seed chat sessions on disk)."""
    from codeagent.core import env as ca_env

    action = getattr(args, 'action', 'list')
    session_id = getattr(args, 'session_id', None)
    agent_id = (getattr(args, 'agent_id', None) or ca_env.default_agent_id()).strip() or 'default'

    if action == 'list':
        from seed.core.llm_sess import list_stored_sessions_meta

        rows = list_stored_sessions_meta(limit=200, agent_id=agent_id)
        print(f"=== Chat sessions (agent={agent_id})")
        print(f"Total: {len(rows)}")
        for row in rows:
            title = row.get('display_title') or row.get('session_id')
            print(f" - {row.get('session_id')}: {title}")
    elif action == 'migrate':
        from seed.core.llm_sess import migrate_legacy_agent_sessions

        stats = migrate_legacy_agent_sessions(
            agent_id,
            dry_run=bool(getattr(args, 'dry_run', False)),
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif action == 'audit-list':
        if not session_id:
            print("Usage: codeagent session audit-list <session_id> [--agent-id ...] [--project-id ...]")
            return
        from seed.core.projection_audit import list_projection_audit_index

        rows = list_projection_audit_index(
            session_id,
            agent_id=agent_id,
            project_id=getattr(args, 'project_id', None),
        )
        if not rows:
            print("No LLM projection audit snapshots (enable SEED_LLM_PROJECTION_AUDIT=1).")
            return
        print(f"=== LLM projection audit (agent={agent_id}, session={session_id})")
        for row in rows:
            print(
                f" seq={row.get('seq')} kind={row.get('kind')} round={row.get('round')} "
                f"bytes={row.get('body_bytes')} file={row.get('file')}"
            )
    elif action == 'audit-show':
        if not session_id:
            print("Usage: codeagent session audit-show <session_id> --seq N")
            return
        seq = getattr(args, 'seq', None)
        if seq is None:
            print("--seq is required for audit-show")
            return
        from seed.core.projection_audit import load_projection_audit_snapshot

        snap = load_projection_audit_snapshot(
            session_id,
            seq=seq,
            agent_id=agent_id,
            project_id=getattr(args, 'project_id', None),
        )
        if not snap:
            print(f"Audit snapshot not found: seq={seq}")
            return
        print(json.dumps(snap, ensure_ascii=False, indent=2))
    elif action == 'help':
        print("Actions: list, migrate, delete, audit-list, audit-show, help")
        print("  codeagent session migrate [--agent-id default] [--dry-run]")
        print("  codeagent session audit-list <session_id>")
        print("  codeagent session audit-show <session_id> --seq N")
        print("  Enable snapshots: SEED_LLM_PROJECTION_AUDIT=1 in config/seed.env")
    elif action == 'delete' and session_id:
        from seed.core.llm_sess import delete_stored_session

        if delete_stored_session(session_id, agent_id):
            print(f"Session deleted: {session_id}")
        else:
            print(f"Session not found: {session_id}")
    else:
        print(f"Session action '{action}': invalid or missing arguments.")

# Note: entry points are __main__.py / main.py / cli_pkg, not this file directly
