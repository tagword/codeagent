"""
API 文档工具 — 扫描路由代码，自动生成 OpenAPI / Markdown 文档

子命令:
  scan     扫描路由定义  api_docs(command="scan", path=".")
  generate 生成文档       api_docs(command="generate", path=".", format="md")
"""

import ast
import json
import os
from typing import Dict, List

from seed.models import Tool


def _find_py_files(path: str) -> List[str]:
    py_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules"))]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def _scan_routes(filepath: str) -> List[Dict]:
    """扫描文件中的路由定义（FastAPI router / Flask route）。"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    routes = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return routes

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    func_name = ""
                    if isinstance(dec.func, ast.Attribute):
                        func_name = dec.func.attr
                    elif isinstance(dec.func, ast.Name):
                        func_name = dec.func.id

                    if func_name.lower() in ("get", "post", "put", "delete", "patch", "route", "add_url_rule"):
                        path_str = ""
                        summary = ast.get_docstring(node) or ""
                        if dec.args:
                            try:
                                path_str = ast.literal_eval(dec.args[0])
                            except Exception:
                                path_str = str(dec.args[0]) if hasattr(ast, 'unparse') else "?"

                        params = []
                        for arg in node.args.args:
                            if arg.arg != "self":
                                params.append(arg.arg)

                        routes.append({
                            "method": func_name.upper(),
                            "path": path_str,
                            "function": node.name,
                            "file": os.path.relpath(filepath),
                            "line": node.lineno,
                            "summary": summary[:120],
                            "params": params,
                        })

    return routes


def _generate_markdown(routes: List[Dict]) -> str:
    """生成 Markdown API 文档。"""
    if not routes:
        return "# API 文档\n\n未发现路由定义"

    lines = ["# API 文档\n", f"共 {len(routes)} 个接口\n", "---\n"]

    by_file = {}
    for r in routes:
        by_file.setdefault(r["file"], []).append(r)

    for filepath, file_routes in sorted(by_file.items()):
        lines.append(f"## {filepath}\n")
        for r in sorted(file_routes, key=lambda x: (x["method"], x["path"])):
            lines.append(f"### `{r['method']}` {r['path']}")
            if r["summary"]:
                lines.append(f"\n{r['summary']}")
            lines.append(f"\n- **函数**: `{r['function']}` (第 {r['line']} 行)")
            if r["params"]:
                lines.append(f"- **参数**: `{', '.join(r['params'])}`")
            lines.append("")

    return "\n".join(lines)


def _generate_openapi(routes: List[Dict]) -> str:
    """生成 OpenAPI 3.0 JSON 结构。"""
    paths = {}
    for r in routes:
        path_key = r["path"]
        if path_key not in paths:
            paths[path_key] = {}
        method_lower = r["method"].lower()
        paths[path_key][method_lower] = {
            "summary": r["summary"] or f"Auto-generated: {r['function']}",
            "operationId": r["function"],
            "parameters": [
                {"name": p, "in": "query", "required": False, "schema": {"type": "string"}}
                for p in r["params"]
            ],
            "responses": {
                "200": {"description": "Successful response"}
            },
        }

    spec = {
        "openapi": "3.0.3",
        "info": {"title": "API Documentation", "version": "1.0.0"},
        "paths": paths,
    }
    return json.dumps(spec, indent=2, ensure_ascii=False)


def api_docs_handler(command: str = "", path: str = "", format: str = "md") -> str:
    """
    API 文档工具 — 扫描路由代码，自动生成 OpenAPI / Markdown 文档。
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return "📗 **api_docs 工具**\n\n子命令:\n  scan     扫描路由\n  generate 生成文档\n\n参数:\n  format=md   输出格式 (md/json)\n  path=.     项目路径"

    try:
        if os.path.isfile(base):
            files = [base]
        else:
            files = _find_py_files(base)

        all_routes = []
        for fp in files:
            routes = _scan_routes(fp)
            all_routes.extend(routes)

        if cmd == "scan":
            if not all_routes:
                return "📭 未发现路由定义"
            lines = [f"🔍 **扫描结果: {len(all_routes)} 个路由**\n"]
            for r in sorted(all_routes, key=lambda x: (x["file"], x["method"], x["path"])):
                lines.append(f"  `{r['method']:6s}` {r['path']:40s} → {r['function']}  ({r['file']}:{r['line']})")
            return "\n".join(lines)

        elif cmd == "generate":
            if not all_routes:
                return "📭 未发现路由定义，无法生成文档"

            fmt = format.lower()
            if fmt == "json":
                content = _generate_openapi(all_routes)
                ext = ".json"
            else:
                content = _generate_markdown(all_routes)
                ext = ".md"

            out_name = f"api_docs{ext}"
            out_path = os.path.join(base, out_name)
            with open(out_path, "w") as f:
                f.write(content)

            return f"✅ 文档已生成: {out_name} ({len(all_routes)} 个接口)\n\n```\n{content[:800]}\n```"

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


api_docs_tool_def = Tool(
    name="api_docs",
    description="扫描 FastAPI/Flask 路由，自动生成 Markdown / OpenAPI 文档。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: scan, generate"},
        "path": {"type": "string", "required": False, "description": "项目路径"},
        "format": {"type": "string", "required": False, "description": "输出格式: md (Markdown) 或 json (OpenAPI)"},
    },
    returns="string",
    category="dev",
)
