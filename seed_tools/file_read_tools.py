"""File read/search tools"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from seed_tools.models import Tool
from seed_tools.artifact_helpers import (
    _artifact_summary,
    _artifact_write_text,
    _summarize_text_with_fallback,
)
from seed_tools.shell_helpers import _active_agent_and_session, _env_truthy

logger = logging.getLogger(__name__)


def _file_read_line_window(filepath: str, start_line: int, limit: int, max_bytes: int) -> str:
    """Read up to ``limit`` lines starting at 1-based ``start_line`` (inclusive)."""
    lines_out: List[str] = []
    line_no = 0
    bytes_used = 0
    truncated_bytes = False
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_no += 1
            if line_no < start_line:
                continue
            b = len(line.encode("utf-8", errors="replace"))
            if bytes_used + b > max_bytes:
                truncated_bytes = True
                break
            bytes_used += b
            lines_out.append(line)
            if limit > 0 and len(lines_out) >= limit:
                break
    content = "".join(lines_out)
    meta_tail = ""
    if truncated_bytes:
        meta_tail = f"\n...[file bytes truncated at {max_bytes}]"
    if not lines_out:
        return f"Error: start={start_line} is beyond end of file (file has {line_no} lines)"
    ap = _artifact_write_text(kind="file_read", name_hint=os.path.basename(filepath), text=content)
    if ap:
        return _artifact_summary(title=f"[file_read] {filepath} (lines {start_line}+)", text=content, path=ap) + meta_tail
    return content + meta_tail


def file_read_handler(filepath: str, limit: int = 1000, start: int = 1) -> str:
    """Read contents of a file. ``start`` is 1-based line number to begin from (inclusive)."""
    try:
        if not os.path.exists(filepath):
            return f"Error: File not found: {filepath}"
        start_line = max(1, int(start))
        try:
            max_bytes = int(os.environ.get("CODEAGENT_FILE_READ_MAX_BYTES", "2097152") or 2097152)
        except Exception:
            max_bytes = 2097152
        max_bytes = max(64 * 1024, min(max_bytes, 200 * 1024 * 1024))

        if start_line > 1:
            return _file_read_line_window(filepath, start_line, limit, max_bytes)
        # Adaptive mode:
        # - Small files: return content (optionally artifact summary).
        # - Large files: stream chunks, persist full text as artifact, return rolling summary.
        summarize_on = _env_truthy("CODEAGENT_FILE_READ_CHUNK_SUMMARY", "1")
        try:
            threshold_chars = int(os.environ.get("CODEAGENT_FILE_READ_CHUNK_SUMMARY_THRESHOLD_CHARS", "30000") or 30000)
        except Exception:
            threshold_chars = 30000
        try:
            chunk_chars = int(os.environ.get("CODEAGENT_FILE_READ_CHUNK_CHARS", "30000") or 30000)
        except Exception:
            chunk_chars = 30000
        try:
            max_chunks = int(os.environ.get("CODEAGENT_FILE_READ_MAX_CHUNKS", "12") or 12)
        except Exception:
            max_chunks = 12
        try:
            summary_max_tokens = int(os.environ.get("CODEAGENT_FILE_READ_SUMMARY_MAX_TOKENS", "1200") or 1200)
        except Exception:
            summary_max_tokens = 1200
        try:
            roll_max_chars = int(os.environ.get("CODEAGENT_FILE_READ_ROLLING_SUMMARY_CHARS", "2000") or 2000)
        except Exception:
            roll_max_chars = 2000

        threshold_chars = max(2000, min(threshold_chars, 400_000))
        chunk_chars = max(2000, min(chunk_chars, 200_000))
        max_chunks = max(1, min(max_chunks, 200))
        summary_max_tokens = max(128, min(summary_max_tokens, 8192))
        roll_max_chars = max(200, min(roll_max_chars, 20_000))

        # Prepare an artifact file for the raw text (streamed, no large in-memory buffer).
        raw_path: Optional[str] = None
        raw_fp = None
        try:
            if _env_truthy("CODEAGENT_TOOL_ARTIFACTS", "1"):
                from seed.llm_sess import llm_sessions_dir

                agent_id, session_id = _active_agent_and_session()
                base = os.path.join(str(llm_sessions_dir(agent_id)), "_artifacts", session_id)
                os.makedirs(base, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in os.path.basename(filepath))[:64]
                raw_path = os.path.join(base, f"{ts}_file_read_{safe}.txt")
                raw_fp = open(raw_path, "w", encoding="utf-8", errors="replace")
        except Exception:
            raw_path = None
            raw_fp = None

        prefix_buf: List[str] = []
        prefix_len = 0
        summary = ""
        in_chunk_summary = False
        chunk_buf: List[str] = []
        chunk_len = 0
        chunks_done = 0
        bytes_used = 0
        truncated = False
        lines_seen = 0

        def _flush_chunk_into_summary(chunk_text: str) -> None:
            nonlocal summary, chunks_done
            if not summarize_on:
                return
            if not chunk_text.strip():
                return
            if chunks_done >= max_chunks:
                return
            if not summary.strip():
                summary = _summarize_text_with_fallback(text=chunk_text, max_tokens=summary_max_tokens)
            else:
                merged_in = (
                    "当前摘要（请保持其不变或进一步压缩）：\n"
                    + summary.strip()[:roll_max_chars]
                    + "\n\n新增内容（请把关键信息合并进摘要）：\n"
                    + chunk_text
                )
                summary = _summarize_text_with_fallback(text=merged_in, max_tokens=summary_max_tokens)
            if len(summary) > roll_max_chars:
                summary = summary[:roll_max_chars].rstrip() + "…"
            chunks_done += 1

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    lines_seen += 1
                    b = len(line.encode("utf-8", errors="replace"))
                    if bytes_used + b > max_bytes:
                        truncated = True
                        break
                    bytes_used += b
                    if raw_fp is not None:
                        try:
                            raw_fp.write(line)
                        except Exception:
                            pass

                    if not in_chunk_summary:
                        if prefix_len < threshold_chars:
                            prefix_buf.append(line)
                            prefix_len += len(line)
                            continue
                        # Switch to chunk summary mode: summarize the prefix first.
                        in_chunk_summary = True
                        _flush_chunk_into_summary("".join(prefix_buf))
                        prefix_buf = []

                    # Now in chunk summary mode: accumulate chunk and flush when big.
                    chunk_buf.append(line)
                    chunk_len += len(line)
                    if chunk_len >= chunk_chars:
                        _flush_chunk_into_summary("".join(chunk_buf))
                        chunk_buf = []
                        chunk_len = 0
                        if chunks_done >= max_chunks:
                            truncated = True
                            break

        finally:
            try:
                if raw_fp is not None:
                    raw_fp.close()
            except Exception:
                pass

        # If we never switched into chunk summary mode, behave like the old implementation (but with bytes cap).
        if not in_chunk_summary:
            content = "".join(prefix_buf)
            lines = content.split("\n")
            if limit and limit > 0 and len(lines) > limit:
                content = "\n".join(lines[:limit]) + f"\n...[{len(lines) - limit} lines truncated]"
            if truncated:
                content = content.rstrip() + f"\n...[file bytes truncated at {max_bytes}]"
            ap = _artifact_write_text(kind="file_read", name_hint=os.path.basename(filepath), text=content)
            if ap:
                return _artifact_summary(title=f"[file_read] {filepath}", text=content, path=ap)
            return content

        # Flush the tail chunk if any.
        if chunk_buf and chunks_done < max_chunks:
            _flush_chunk_into_summary("".join(chunk_buf))

        meta = {
            "ok": True,
            "mode": "chunk_summary",
            "filepath": filepath,
            "saved_to": raw_path,
            "bytes_read": bytes_used,
            "max_bytes": max_bytes,
            "lines_seen": lines_seen,
            "chunks_summarized": chunks_done,
            "max_chunks": max_chunks,
            "truncated": bool(truncated),
            "summary_chars": len(summary or ""),
        }
        return json.dumps(meta, ensure_ascii=False) + "\n\n" + (summary or "").strip()
    except Exception as e:
        return f"Error reading file: {e}"

file_read_def = Tool(
    name="file_read",
    description="Read contents of a file",
    parameters={
        "filepath": {"type": "string", "required": True, "description": "Path to the file to read"},
        "start": {
            "type": "integer",
            "required": False,
            "description": "1-based line number to start reading from (inclusive). Default 1 = file beginning.",
        },
        "limit": {"type": "integer", "required": False, "description": "Maximum lines to return (default: 1000)"},
    },
    returns="string: File contents"
)

# Artifact helper: read a saved long tool output precisely.
