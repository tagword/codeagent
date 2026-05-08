def _builtin_checks(source_code: str, lang: str, lines: list) -> list:
    """内置基础检查（所有语言通用）"""
    issues = []
    for i, line_text in enumerate(lines, 1):
        stripped = line_text.strip()
        if stripped.startswith(("#", "//", "/*")):
            for kw in ("TODO", "FIXME", "HACK", "XXX"):
                if kw in stripped:
                    issues.append(f"📌 第 {i} 行: 待办注释「{stripped[:60]}」")
                    break
        if len(line_text.rstrip()) > 200:
            issues.append(f"📏 第 {i} 行: 行过长 ({len(line_text.rstrip())} 字符)")
    trailing = sum(1 for i, l in enumerate(lines, 1) if l.rstrip() != l and l.strip())
    if trailing > 0:
        issues.append(f"🧹 发现 {trailing} 行有尾部空白")
    if not source_code.endswith("\n"):
        issues.append("📄 文件末尾缺少换行符")
    if lang == "python":
        for i, line_text in enumerate(lines, 1):
            stripped = line_text.strip()
            if stripped == "except:":
                issues.append(f"⚠️ 第 {i} 行: 裸 except: 应指定异常类型")
            if "import *" in stripped and not stripped.startswith("#"):
                issues.append(f"⚠️ 第 {i} 行: 避免使用 from X import *")
            if "\t" in line_text:
                issues.append(f"⚠️ 第 {i} 行: 混入了 Tab 缩进")
    if lang in ("javascript", "typescript"):
        for i, line_text in enumerate(lines, 1):
            stripped = line_text.strip()
            if "==" in stripped and "===" not in stripped and "!==" not in stripped:
                issues.append(f"⚠️ 第 {i} 行: 建议用 === 代替 ==")
            if "var " in stripped and not stripped.startswith("//"):
                issues.append(f"⚠️ 第 {i} 行: 建议用 const/let 代替 var")
            if "\t" in line_text:
                issues.append(f"⚠️ 第 {i} 行: 混入了 Tab 缩进")
    if lang == "html":
        if "<!DOCTYPE html>" not in source_code.upper():
            issues.append("⚠️ 缺少 DOCTYPE 声明")
    return issues


code_check_tool_def = {
    "name": "code_check",
    "description": "Check code for issues using real linters (ruff for Python, eslint for JS/TS) and built-in heuristics. Supports auto-fix.",
    "parameters": {
        "code": {"type": "string", "required": False, "description": "Code string to check"},
        "filepath": {"type": "string", "required": False, "description": "Path to file to check. Language auto-detected from extension."},
        "language": {"type": "string", "required": False, "description": "Programming language (auto = detect from extension or default python)"},
        "fix": {"type": "boolean", "required": False, "description": "Auto-fix fixable issues. Default: false"}
    },
    "returns": "string: Structured report of issues found"
}

# 兼容旧的 code_analyze
code_analyze_tool_def = {
    "name": "code_analyze",
    "description": "[Legacy] Analyze code for issues. Consider using 'code_check' instead.",
    "parameters": {
        "code": {"type": "string", "required": False, "description": "Code to analyze"},
        "filepath": {"type": "string", "required": False, "description": "Path to file to analyze"},
        "language": {"type": "string", "required": False, "description": "Programming language (default: python)"},
        "focus": {"type": "string", "required": False, "description": "'issues', 'suggestions', 'explain', or 'fix' (default: issues)"}
    },
    "returns": "string: Analysis results"
}

# =============================================================================
# Tool 7: git — 统一的 git 操作工具
# =============================================================================

