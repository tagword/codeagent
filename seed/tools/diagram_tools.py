"""
架构图工具 — 从项目结构生成 mermaid 图

子命令:
  dir      目录结构图   diagram(command="dir", path=".")
  deps     依赖关系图   diagram(command="deps", path=".")
  classes  类图         diagram(command="classes", path=".")
"""

import ast
import os
from typing import List

from seed.models import Tool


def _find_py_files(path: str) -> List[str]:
    py_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules", "dist", "build", ".git"))]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def _dir_diagram(path: str) -> str:
    """生成目录结构 mermaid 图。"""
    base = os.path.abspath(path)
    lines = ["```mermaid", "graph TD"]

    # 根节点
    lines.append(f'    root["{os.path.basename(base)}"]')

    # 收集目录结构
    dirs_seen = set()
    file_id = 0

    def add_dir(dir_path):
        nonlocal file_id
        if dir_path in dirs_seen:
            return
        dirs_seen.add(dir_path)
        parent = os.path.dirname(dir_path)
        if parent and parent != dir_path:
            add_dir(parent)
            pname = os.path.basename(parent) or parent
            dname = os.path.basename(dir_path) or dir_path
            lines.append(f'    {pname.replace(".", "_").replace("-", "_")}[{pname}] --> {dname.replace(".", "_").replace("-", "_")}[{dname}]')

    for root, dirs, files_list in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules", ".git"))]
        rel = os.path.relpath(root, base)
        if rel == ".":
            continue
        add_dir(rel)

    # 添加文件
    for fp in _find_py_files(path)[:30]:
        rel = os.path.relpath(fp, base)
        parts = rel.split(os.sep)
        if len(parts) >= 2:
            parent = os.path.dirname(rel)
            pname = os.path.basename(parent)
            fname = os.path.basename(rel)
            fid = f"f{file_id}"
            lines.append(f'    {parent.replace(os.sep, "_").replace(".", "_").replace("-", "_")}[{pname}] --> {fid}["{fname}"]')
            file_id += 1

    lines.append("```")
    return "\n".join(lines)


def _deps_diagram(path: str) -> str:
    """生成模块依赖关系 mermaid 图。"""
    py_files = _find_py_files(path)

    imports = {}  # file -> set of dependencies

    for fp in py_files:
        rel = os.path.relpath(fp, os.path.abspath(path))
        mod_name = rel.replace(os.sep, ".").replace(".py", "").replace(".__init__", "")
        imports[mod_name] = set()

        try:
            with open(fp, "r") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, Exception):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[mod_name].add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports[mod_name].add(node.module.split(".")[0])

    local_modules = set(imports.keys())
    local_edges = []
    for mod, deps in imports.items():
        for d in deps:
            if d in local_modules and d != mod:
                local_edges.append((mod, d))

    if not local_edges:
        return "```mermaid\ngraph LR\n    root[\"无本地模块依赖\"]\n```"

    lines = ["```mermaid", "graph LR"]
    for src, dst in local_edges[:40]:
        s = src.replace(".", "_").replace("-", "_")
        d = dst.replace(".", "_").replace("-", "_")
        lines.append(f'    {s}["{src}"] --> {d}["{dst}"]')
    lines.append("```")
    return "\n".join(lines)


def _classes_diagram(path: str) -> str:
    """生成类继承关系 mermaid 图。"""
    py_files = _find_py_files(path)

    classes = []  # (name, bases, file)
    for fp in py_files:
        try:
            with open(fp, "r") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, Exception):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = []
                for b in node.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        bases.append("?")
                classes.append((node.name, bases, os.path.relpath(fp, os.path.abspath(path))))

    if not classes:
        return "```mermaid\nclassDiagram\n    class Empty\n```"

    lines = ["```mermaid", "classDiagram"]

    for name, bases, filepath in classes:
        lines.append(f"    class {name} {{")
        lines.append(f"        +{filepath}")
        lines.append("    }")
        for b in bases:
            if b != "object" and b != "Base" and not b.startswith("_"):
                lines.append(f"    {b} <|-- {name}")

    lines.append("```")
    return "\n".join(lines)


def diagram_handler(command: str = "", path: str = "") -> str:
    """
    架构图工具 — 从项目结构生成 mermaid 图。

    子命令:
      dir      目录结构图
      deps     模块依赖图
      classes  类继承图
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return "📗 **diagram 工具**\n\n子命令:\n  dir      目录结构图\n  deps     模块依赖图\n  classes  类继承图\n\n生成的 mermaid 代码可直接在 GitHub / MkDocs 中渲染。"

    try:
        if cmd == "dir":
            return _dir_diagram(base)
        elif cmd == "deps":
            return _deps_diagram(base)
        elif cmd == "classes":
            return _classes_diagram(base)
        else:
            return f"❌ 未知子命令: {command}"
    except Exception as e:
        return f"❌ 生成失败: {e}"


diagram_tool_def = Tool(
    name="diagram",
    description="从项目结构生成 mermaid 架构图。支持目录结构、模块依赖、类继承关系。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: dir, deps, classes"},
        "path": {"type": "string", "required": False, "description": "项目路径"},
    },
    returns="string",
    category="dev",
)
