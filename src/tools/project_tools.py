"""
项目理解工具 — AST 分析 + 符号索引 + 项目总览

子命令:
  summary   项目结构总览  project(command="summary", path=".")
  symbols   搜索符号      project(command="symbols", name="my_func", path=".")
  functions 列出函数      project(command="functions", path="src/")
  classes   列出类        project(command="classes", path="src/")
  file      查看文件结构  project(command="file", path="src/foo.py")
  deps      分析依赖树    project(command="deps", path=".")
"""

import ast
import os
from typing import Dict, List

from src.models_pkg import Tool


def _find_py_files(path: str, max_files: int = 200) -> List[str]:
    """递归查找所有 Python 文件。"""
    py_files = []
    base = os.path.abspath(path)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules", "dist", "build", ".git"))]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
                if len(py_files) >= max_files:
                    return py_files
    return py_files


def _parse_file_symbols(filepath: str) -> Dict:
    """解析单个文件的符号。"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    rel_path = os.path.relpath(filepath)

    result = {
        "path": rel_path,
        "size": len(source),
        "lines": len(source.split("\n")),
        "functions": [],
        "classes": [],
        "imports": [],
        "errors": [],
    }

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        result["errors"].append(str(e))
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func = {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, 'end_lineno', node.lineno),
                "params": [arg.arg for arg in node.args.args],
                "decorators": [],
                "docstring": ast.get_docstring(node) or "",
            }
            for dec in node.decorator_list:
                try:
                    func["decorators"].append(ast.unparse(dec))
                except Exception:
                    func["decorators"].append("?")
            result["functions"].append(func)

        elif isinstance(node, ast.ClassDef):
            cls = {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, 'end_lineno', node.lineno),
                "bases": [],
                "methods": [],
                "docstring": ast.get_docstring(node) or "",
            }
            for base in node.bases:
                try:
                    cls["bases"].append(ast.unparse(base))
                except Exception:
                    cls["bases"].append("?")
            for item in ast.iter_child_nodes(node):
                if isinstance(item, ast.FunctionDef):
                    cls["methods"].append({
                        "name": item.name,
                        "lineno": item.lineno,
                        "params": [arg.arg for arg in item.args.args],
                    })
            result["classes"].append(cls)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)

    return result


def _build_dependency_tree(path: str) -> Dict[str, List[str]]:
    """分析项目模块依赖树。"""
    py_files = _find_py_files(path)
    deps = {}

    for fp in py_files:
        rel = os.path.relpath(fp)
        mod = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
        deps[mod] = []

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, Exception):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps[mod].append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps[mod].append(node.module.split(".")[0])

    # 只保留项目内部模块
    local_modules = set(deps.keys())
    filtered = {}
    for mod, mod_deps in deps.items():
        local = [d for d in mod_deps if d in local_modules]
        if local:
            filtered[mod] = local

    return filtered


def project_handler(command: str = "", path: str = "", name: str = "") -> str:
    """
    项目理解工具 — AST 分析 + 符号索引 + 项目总览。
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return (
            "📗 **project 工具使用帮助**\n\n"
            "子命令:\n"
            "  summary    项目结构总览\n"
            "  functions  列出所有函数\n"
            "  classes    列出所有类\n"
            "  file       查看单个文件结构\n"
            "  deps       分析依赖树\n"
            "  symbols    搜索符号\n"
        )

    try:
        if cmd == "summary":
            py_files = _find_py_files(base)
            total_funcs = 0
            total_classes = 0
            total_lines = 0

            for fp in py_files:
                info = _parse_file_symbols(fp)
                total_funcs += len(info["functions"])
                total_classes += len(info["classes"])
                total_lines += info["lines"]

            return (
                f"📊 **项目总览: {os.path.basename(base)}**\n\n"
                f"  📄 Python 文件: {len(py_files)}\n"
                f"  🔧 函数/方法:   {total_funcs}\n"
                f"  🏛️  类:          {total_classes}\n"
                f"  📏 总代码行数:   {total_lines}"
            )

        elif cmd == "symbols":
            query = name
            if not query:
                return "❌ symbols 需要 name 参数"

            py_files = _find_py_files(base)
            results = []
            for fp in py_files:
                info = _parse_file_symbols(fp)
                for func in info["functions"]:
                    if query in func["name"]:
                        results.append(f"  🔧 `{func['name']}()`  ({info['path']}:{func['lineno']})")
                for cls in info["classes"]:
                    if query in cls["name"]:
                        results.append(f"  🏛️  `{cls['name']}`  ({info['path']}:{cls['lineno']})")

            if not results:
                return f"🔍 未找到包含「{query}」的符号"
            return f"🔍 **符号搜索: {query}** ({len(results)} 处)\n\n" + "\n".join(results)

        elif cmd == "functions":
            py_files = _find_py_files(base)
            results = []
            for fp in py_files:
                info = _parse_file_symbols(fp)
                for func in info["functions"]:
                    params = ", ".join(func["params"][:5])
                    results.append(f"  🔧 `{func['name']}({params})`  ({info['path']}:{func['lineno']})")

            if not results:
                return "📭 未找到函数"
            return f"🔧 **函数列表** ({len(results)} 个)\n\n" + "\n".join(results)

        elif cmd == "classes":
            py_files = _find_py_files(base)
            results = []
            for fp in py_files:
                info = _parse_file_symbols(fp)
                for cls in info["classes"]:
                    bases = ", ".join(cls["bases"]) if cls["bases"] else ""
                    base_str = f"({bases})" if bases else ""
                    results.append(f"  🏛️  `{cls['name']}`{base_str}  ({info['path']}:{cls['lineno']})")

            if not results:
                return "📭 未找到类"
            return f"🏛️  **类列表** ({len(results)} 个)\n\n" + "\n".join(results)

        elif cmd == "file":
            if not os.path.isfile(base):
                return "❌ file 命令的 path 需要指向 .py 文件"

            info = _parse_file_symbols(base)
            lines = [
                f"📄 **{info['path']}** ({info['size']} bytes, {info['lines']} 行)\n"
            ]
            if info["errors"]:
                lines.append(f"⚠️ 解析错误: {info['errors'][0]}\n")

            if info["classes"]:
                lines.append(f"🏛️  **类 ({len(info['classes'])}):**")
                for cls in info["classes"]:
                    methods = ", ".join(m["name"] for m in cls["methods"][:10])
                    lines.append(f"  `{cls['name']}`  (第 {cls['lineno']} 行)")
                    if methods:
                        lines.append(f"    方法: {methods}")
                lines.append("")

            if info["functions"]:
                lines.append(f"🔧 **函数 ({len(info['functions'])}):**")
                for func in info["functions"]:
                    params = ", ".join(func["params"][:5])
                    lines.append(f"  `{func['name']}({params})`  (第 {func['lineno']} 行)")
                lines.append("")

            if info["imports"]:
                lines.append(f"📦 **导入 ({len(info['imports'])}):**")
                for imp in info["imports"][:20]:
                    lines.append(f"  `{imp}`")

            return "\n".join(lines)

        elif cmd == "deps":
            dep_tree = _build_dependency_tree(base)
            if not dep_tree:
                return "📭 未发现本地模块依赖关系"

            lines = [f"🔗 **模块依赖图** ({len(dep_tree)} 个模块)\n"]
            for mod, mod_deps in sorted(dep_tree.items()):
                if mod_deps:
                    deps_str = ", ".join(mod_deps[:8])
                    lines.append(f"  `{mod}` → [{deps_str}]")
            return "\n".join(lines)

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


project_tool_def = Tool(
    name="project",
    description="项目理解工具，通过 AST 分析提取项目结构、符号索引、依赖树等信息。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: summary, symbols, functions, classes, file, deps"},
        "path": {"type": "string", "required": False, "description": "项目路径"},
        "name": {"type": "string", "required": False, "description": "要搜索的符号名（symbols 使用）"},
    },
    returns="string",
    category="dev",
)
