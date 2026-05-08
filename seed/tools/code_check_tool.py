"""code_check — ruff/eslint when available; syntax + built-in heuristics as fallback."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from typing import List, Optional

from seed.tools._builtin_checks import _builtin_checks


def _get_ruff_argv() -> Optional[List[str]]:
    """Resolve ruff CLI: `ruff` on PATH or ``python -m ruff``."""
    import shutil

    if shutil.which("ruff"):
        return ["ruff"]
    try:
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return [sys.executable, "-m", "ruff"]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _python_syntax_issues(path: str) -> List[str]:
    import py_compile

    out: List[str] = []
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        msg = getattr(e, "msg", str(e)) or str(e)
        lineno = getattr(e, "lineno", None)
        line_s = str(lineno) if lineno is not None else "?"
        out.append(f"❌ 第 {line_s} 行: 语法错误 — {msg}")
    return out


def _parse_ruff_concise(raw_output: str) -> tuple[List[str], int]:
    """Parse ``ruff check --output-format=concise`` lines."""
    issues: List[str] = []
    fixable_count = 0
    for line_text in raw_output.split("\n"):
        line_text = line_text.strip()
        if not line_text or "Warning:" in line_text:
            continue
        m = re.match(r"^.*\.py:(\d+):(\d+):\s+(\w+)\s+(.+)$", line_text)
        if m:
            ln, col, sev, msg = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            fixable = "[*]" in line_text
            icon = "🔧" if fixable else "⚠️"
            issues.append(f"{icon} 第 {ln} 行 第 {col} 列 [{sev}] {msg}")
            if fixable:
                fixable_count += 1
        elif line_text and not line_text.startswith("="):
            issues.append(f"  {line_text}")
    return issues, fixable_count


def code_check_tool(code: str = "", filepath: str = "", language: str = "auto", fix: bool = False) -> str:
    """
    Check code for issues using ruff (Python) / eslint (JS/TS) when installed,
    plus stdlib syntax check and built-in heuristics as fallback.
    """
    try:
        source_code = ""
        lang = language
        source_name = "inline"

        if filepath and os.path.isfile(filepath):
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                source_code = fh.read()
            base = os.path.basename(filepath)
            source_name = base
            if lang == "auto":
                ext = os.path.splitext(base)[1].lower()
                ext_map = {
                    ".py": "python",
                    ".js": "javascript",
                    ".jsx": "javascript",
                    ".ts": "typescript",
                    ".tsx": "typescript",
                    ".html": "html",
                    ".htm": "html",
                    ".css": "css",
                    ".json": "json",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                    ".md": "markdown",
                    ".rs": "rust",
                    ".go": "go",
                    ".java": "java",
                    ".c": "c",
                    ".cpp": "cpp",
                    ".h": "c",
                }
                lang = ext_map.get(ext, "unknown")
        elif code:
            source_code = code
            if lang == "auto":
                lang = "python"
        else:
            return "❌ 请提供 filepath 或 code 参数"

        if not source_code.strip():
            return "⚠️ 代码为空，跳过检查"

        lines = source_code.split("\n")
        total_lines = len(lines)

        # --- Python: ruff if present; always syntax + built-in ---
        if lang == "python":
            tmp_path: Optional[str] = None
            try:
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
                tmp.write(source_code)
                tmp.close()
                tmp_path = tmp.name

                syntax_issues = _python_syntax_issues(tmp_path)
                builtin_issues = _builtin_checks(source_code, lang, lines)

                ruff_argv = _get_ruff_argv()
                fix_note = ""
                fixable_count = 0
                no_ruff_hint = ""
                ruff_issues: List[str] = []
                if ruff_argv:
                    cmd = ruff_argv + ["check", "--output-format=concise", tmp_path]
                    if fix:
                        cmd.append("--fix")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    raw_output = (result.stdout or "") + (result.stderr or "")
                    ruff_issues, fixable_count = _parse_ruff_concise(raw_output)
                    if fix and result.returncode == 0 and not ruff_issues:
                        fix_note = "\n✅ 自动修复已应用（ruff）"
                    elif fix and ruff_issues:
                        fix_note = "\n⚠️ 部分问题需要手动修复（ruff）"
                else:
                    no_ruff_hint = (
                        "⚠️ 未检测到 ruff（可执行文件不在 PATH，且 ``python -m ruff`` 不可用）。"
                        "已使用 **语法编译检查** 与 **内置规则**。安装完整检查：`pip install ruff` 或 "
                        "`pip install -e \".[lint]\"`。\n\n"
                    )
                    if fix:
                        fix_note = "\n⚠️ fix=True 需要安装 ruff 后才可自动修复"

                seen: set[str] = set()
                issues: List[str] = []
                for group in (ruff_issues, syntax_issues, builtin_issues):
                    for item in group:
                        if item not in seen:
                            seen.add(item)
                            issues.append(item)

                if not issues:
                    return (
                        f"✅ **{source_name}** — 未发现语法问题；内置规则通过 ({total_lines} 行)"
                        + (f"\n\n{no_ruff_hint.rstrip()}" if no_ruff_hint else "")
                        + fix_note
                    )

                header = f"📋 **{source_name}** 检查结果 ({total_lines} 行)"
                if ruff_argv and fixable_count > 0:
                    header += f"\n💡 其中约 {fixable_count} 条可用 fix=True 尝试自动修复（ruff）"
                body = "\n".join(issues)
                prefix = no_ruff_hint if no_ruff_hint else ""
                return prefix + header + "\n\n" + body + fix_note
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        # --- JS/TS: eslint + built-in ---
        elif lang in ("javascript", "typescript"):
            issues: List[str] = []
            has_eslint = False
            try:
                subprocess.run(["eslint", "--version"], capture_output=True, text=True, timeout=5)
                has_eslint = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            tmp_path: Optional[str] = None
            if has_eslint:
                suffix = ".js" if lang == "javascript" else ".ts"
                try:
                    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
                    tmp.write(source_code)
                    tmp.close()
                    tmp_path = tmp.name
                    cmd = ["eslint", "--format=compact", tmp_path]
                    if fix:
                        cmd.append("--fix")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    raw = (result.stdout or "") + (result.stderr or "")
                    for line_text in raw.split("\n"):
                        line_text = line_text.strip()
                        if not line_text:
                            continue
                        m = re.match(
                            r"^.*\.(js|ts):line\s+(\d+),col\s+(\d+),\s+(?:Error|Warning)\s+-\s+(.+)$",
                            line_text,
                        )
                        if m:
                            issues.append(f"⚠️ 第 {m.group(2)} 行 第 {m.group(3)} 列 {m.group(4).strip()}")
                        elif "Error" in line_text or "Warning" in line_text:
                            issues.append(f"  {line_text}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

                if issues:
                    return f"📋 **{source_name}** eslint 检查结果 ({total_lines} 行)\n\n" + "\n".join(issues)

            js_issues = _builtin_checks(source_code, lang, lines)
            no_eslint = (
                "⚠️ eslint 未安装，使用内置基础检查。安装：`npm install -g eslint`\n\n"
                if not has_eslint
                else ""
            )
            if not js_issues:
                return f"✅ **{source_name}** — 基础检查通过 ({total_lines} 行)"
            return f"📋 **{source_name}** 基础检查结果 ({total_lines} 行)\n" + no_eslint + "\n".join(js_issues)

        # --- Other languages: built-in only ---
        issues = _builtin_checks(source_code, lang, lines)
        if not issues:
            return f"✅ **{source_name}** — 基础检查通过 ({total_lines} 行, {lang})"
        return f"📋 **{source_name}** 基础检查结果 ({total_lines} 行, {lang})\n\n" + "\n".join(issues)

    except Exception as e:
        return f"❌ 代码检查执行失败: {e}"
