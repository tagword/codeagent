"""Tool module: web_tools"""
import json
import logging
import os
import urllib.request
from typing import Dict, List

from seed.models import Tool
from seed.tools.artifact_helpers import (
    _artifact_summary,
    _artifact_write_text,
    _summarize_text_with_fallback,
)
from seed.tools.shell_helpers import _env_truthy

logger = logging.getLogger(__name__)

def web_fetch_handler(url: str, timeout: int = 10) -> str:
    """Fetch content from a URL"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="replace")

            # Always try to persist the full body as an artifact (large pages often blow up context).
            ap = _artifact_write_text(kind="web_fetch", name_hint="page", text=content)

            summarize_on = _env_truthy("CODEAGENT_WEB_FETCH_CHUNK_SUMMARY", "1")
            try:
                threshold_chars = int(os.environ.get("CODEAGENT_WEB_FETCH_CHUNK_SUMMARY_THRESHOLD_CHARS", "30000") or 30000)
            except Exception:
                threshold_chars = 30000
            try:
                chunk_chars = int(os.environ.get("CODEAGENT_WEB_FETCH_CHUNK_CHARS", "30000") or 30000)
            except Exception:
                chunk_chars = 30000
            try:
                max_chunks = int(os.environ.get("CODEAGENT_WEB_FETCH_MAX_CHUNKS", "10") or 10)
            except Exception:
                max_chunks = 10
            try:
                summary_max_tokens = int(os.environ.get("CODEAGENT_WEB_FETCH_SUMMARY_MAX_TOKENS", "1200") or 1200)
            except Exception:
                summary_max_tokens = 1200
            try:
                roll_max_chars = int(os.environ.get("CODEAGENT_WEB_FETCH_ROLLING_SUMMARY_CHARS", "2000") or 2000)
            except Exception:
                roll_max_chars = 2000

            threshold_chars = max(2000, min(threshold_chars, 400_000))
            chunk_chars = max(2000, min(chunk_chars, 200_000))
            max_chunks = max(1, min(max_chunks, 200))
            summary_max_tokens = max(128, min(summary_max_tokens, 8192))
            roll_max_chars = max(200, min(roll_max_chars, 20_000))

            # Small page: keep prior behavior (artifact excerpt) to avoid extra LLM calls.
            if (not summarize_on) or len(content) < threshold_chars:
                if ap:
                    return _artifact_summary(title=f"[web_fetch] {url}", text=content, path=ap)
                return content[:50000]

            # Large page: chunk + rolling summary, keep context small.
            summary = ""
            chunks_done = 0
            idx = 0
            n = len(content)
            while idx < n and chunks_done < max_chunks:
                chunk = content[idx : idx + chunk_chars]
                idx += chunk_chars
                if not chunk.strip():
                    continue
                if not summary.strip():
                    summary = _summarize_text_with_fallback(text=chunk, max_tokens=summary_max_tokens)
                else:
                    merged_in = (
                        "当前摘要（请保持其不变或进一步压缩）：\n"
                        + summary.strip()[:roll_max_chars]
                        + "\n\n新增内容（请把关键信息合并进摘要）：\n"
                        + chunk
                    )
                    summary = _summarize_text_with_fallback(text=merged_in, max_tokens=summary_max_tokens)
                if len(summary) > roll_max_chars:
                    summary = summary[:roll_max_chars].rstrip() + "…"
                chunks_done += 1

            meta = {
                "ok": True,
                "mode": "chunk_summary",
                "url": url,
                "saved_to": ap,
                "chars": len(content),
                "chunks_summarized": chunks_done,
                "max_chunks": max_chunks,
                "truncated": bool(idx < n),
                "summary_chars": len(summary or ""),
            }
            return json.dumps(meta, ensure_ascii=False) + "\n\n" + (summary or "").strip()
    except Exception as e:
        return f"Error fetching URL: {e}"

web_fetch_def = Tool(
    name="web_fetch",
    description="Fetch content from a URL",
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to fetch"},
        "timeout": {"type": "integer", "required": False, "description": "Request timeout in seconds (default: 10)"}
    },
    returns="string: Web page content"
)

# =========================================================================
# Core Tool: code_check — 真正的代码检查器（集成 ruff + 多语言兜底）
# =========================================================================

def web_search_handler(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Search the web for information"""
    try:
        from ddgs import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results
    except Exception as e:
        return [{"error": f"Web search error: {e}"}]

web_search_def = Tool(
    name="web_search_tool",
    description="Search the web for information",
    parameters={
        "query": {"type": "string", "required": True, "description": "Search query"},
        "num_results": {"type": "integer", "required": False, "description": "Number of results to return", "default": 5}
    },
    returns="list[dict]: Search results with title, url, snippet"
)

# Claw-code Tool 7: JupyterNotebookEditorTool - Notebook editing

