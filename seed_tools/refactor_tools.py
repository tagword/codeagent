"""
代码重构工具 — 重命名符号、提取函数、移动代码

子命令:
  rename    重命名符号     refactor(command="rename", path="file.py", old="foo", new="bar")
  find      查找引用       refactor(command="find", path=".", name="my_func")
  extract   提取函数       refactor(command="extract", path="file.py", function="long_func")
"""

import ast
import os
import re
from typing import List

from seed_tools.models import Tool


def _find_py_files(path: str) -> List[str]:
    py_files = []
    if os.path.isfile(path):
        return [path] if path.endswith(".py") else []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules"))]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def _find_references(name: str, path: str) -> List[dict]:
    """查找符号的所有引用。"""
    refs = []
    for fp in _find_py_files(path):
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            if name in line:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                refs.append({
                    "file": os.path.relpath(fp),
                    "line": i,
                    "content": line.strip()[:100],
                })

    return refs


def _rename_in_file(filepath: str, old_name: str, new_name: str) -> int:
    """在单个文件中重命名符号。"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')
    new_content, count = pattern.subn(new_name, content)

    if count > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    return count


def refactor_handler(command: str = "", path: str = "", old: str = "",
                     new: str = "", name: str = "", function: str = "") -> str:
    """
    代码重构工具 — 重命名符号、查找引用、提取函数。
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return (
            "📗 **refactor 工具使用帮助**\n\n"
            "子命令:\n"
            "  rename  old=X new=Y  重命名符号\n"
            "  find    name=X       查找符号引用\n"
            "  extract function=X   标记可提取的代码\n\n"
            "示例:\n"
            '  refactor(command="rename", path="src/foo.py", old="old_func", new="new_func")\n'
            '  refactor(command="find", path=".", name="UserModel")\n'
        )

    try:
        if cmd == "rename":
            if not old or not new:
                return "❌ rename 需要 old 和 new 参数"

            files = _find_py_files(base)
            total = 0
            changed = []

            for fp in files:
                count = _rename_in_file(fp, old, new)
                if count > 0:
                    total += count
                    changed.append((os.path.relpath(fp), count))

            if total == 0:
                return f"🔍 未找到符号「{old}」的引用"

            result = [f"✅ 重命名完成: `{old}` → `{new}` ({total} 处)\n"]
            for f, c in changed:
                result.append(f"  📄 {f}: {c} 处")
            return "\n".join(result)

        elif cmd == "find":
            query = name or old
            if not query:
                return "❌ find 需要 name 参数"

            refs = _find_references(query, base)
            if not refs:
                return f"🔍 未找到符号「{query}」的引用"

            result = [f"🔍 **符号「{query}」引用 ({len(refs)} 处)**\n"]
            for r in refs:
                result.append(f"  {r['file']}:{r['line']}  {r['content']}")
            return "\n".join(result)

        elif cmd == "extract":
            if not function:
                return "❌ extract 需要 function 参数"

            if not os.path.isfile(base):
                return "❌ extract 的 path 参数需要是 .py 文件"

            with open(base, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"❌ 语法错误: {e}"

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function:
                    start = node.lineno
                    end = getattr(node, 'end_lineno', start + 10)
                    lines_content = content.split("\n")
                    func_lines = lines_content[start - 1:end]

                    assigned = set()
                    for child in ast.walk(node):
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Name):
                                    assigned.add(target.id)

                    return (
                        f"📋 **函数 `{function}`** (第 {start}-{end} 行, {len(func_lines)} 行)\n\n"
                        f"```python\n" + "\n".join(func_lines[:30]) + "\n```\n\n"
                        f"💡 提示: 此函数包含 {len(assigned)} 个局部变量。\n"
                        f"   使用 rename 重命名, 手动提取子函数。"
                    )

            return f"❌ 未找到函数: {function}"

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 重构操作失败: {e}"


refactor_tool_def = Tool(
    name="refactor",
    description="代码重构工具。支持重命名符号（自动更新所有引用）、查找引用、提取函数分析。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: rename, find, extract"},
        "path": {"type": "string", "required": False, "description": "文件或目录路径"},
        "old": {"type": "string", "required": False, "description": "旧符号名（rename 使用）"},
        "new": {"type": "string", "required": False, "description": "新符号名（rename 使用）"},
        "name": {"type": "string", "required": False, "description": "要查找的符号名（find 使用）"},
        "function": {"type": "string", "required": False, "description": "函数名（extract 使用）"},
    },
    returns="string",
    category="dev",
)
