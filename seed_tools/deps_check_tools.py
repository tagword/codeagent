"""
依赖检查工具 — 检查依赖版本、安全漏洞、过期包

子命令:
  check    检查依赖安全漏洞  deps_check(command="check", path=".")
  outdated 列出过期包         deps_check(command="outdated", path=".")
  tree     依赖树             deps_check(command="tree", path=".")
"""

import json
import os
import subprocess
from typing import List

from seed_tools.models import Tool


def _find_requirements(path: str) -> str:
    """从目录中查找依赖文件。"""
    for fname in ["requirements.txt", "pyproject.toml", "Pipfile"]:
        fp = os.path.join(path, fname)
        if os.path.isfile(fp):
            return fp
    return ""


def _find_package_json(path: str) -> str:
    fp = os.path.join(path, "package.json")
    return fp if os.path.isfile(fp) else ""


def _check_python_deps(path: str) -> List[str]:
    """用 pip-audit 检查 Python 依赖漏洞。"""
    req = _find_requirements(path)
    if not req:
        return []

    lines = [f"  📦 依赖文件: {os.path.basename(req)}"]

    try:
        cmd = ["pip-audit", "-r", req, "--desc", "--format", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            lines.append("  ✅ pip-audit: 未发现已知安全漏洞")
        else:
            try:
                data = json.loads(result.stdout)
                vulns = data.get("vulnerabilities", [])
                if vulns:
                    lines.append(f"  ⚠️  pip-audit: 发现 {len(vulns)} 个安全漏洞")
                    for v in vulns[:10]:
                        name = v.get("name", "?")
                        ver = v.get("version", "?")
                        vuln_id = v.get("id", "?")
                        severity = v.get("severity", "")
                        sev_str = f" [{severity}]" if severity else ""
                        desc = v.get("description", "")[:80]
                        lines.append(f"     ❌ {name}=={ver}  {vuln_id}{sev_str}")
                        if desc:
                            lines.append(f"        {desc}")
                    if len(vulns) > 10:
                        lines.append(f"     ... 还有 {len(vulns) - 10} 个漏洞")
                else:
                    lines.append("  ✅ pip-audit: 未发现已知安全漏洞")
            except json.JSONDecodeError:
                lines.append(f"  ⚠️  pip-audit 输出解析失败: {result.stdout[:200]}")

    except FileNotFoundError:
        lines.append("  ⚠️  pip-audit 未安装，可用: pip install pip-audit")
    except subprocess.TimeoutExpired:
        lines.append("  ⚠️  pip-audit 超时")
    except Exception as e:
        lines.append(f"  ⚠️  pip-audit 失败: {e}")

    return lines


def _check_node_deps(path: str) -> List[str]:
    """用 npm audit 检查 Node 依赖漏洞。"""
    pkg = _find_package_json(path)
    if not pkg:
        return []

    lines = ["  📦 依赖文件: package.json"]

    try:
        result = subprocess.run(
            ["npm", "audit", "--json"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            lines.append("  ✅ npm audit: 未发现已知安全漏洞")
        else:
            try:
                data = json.loads(result.stdout)
                vulns = data.get("vulnerabilities", {})
                if vulns:
                    total = sum(v.get("count", 0) for v in vulns.values())
                    lines.append(f"  ⚠️  npm audit: 发现 {total} 个问题")
                    for pkg_name, info in list(vulns.items())[:10]:
                        severity = info.get("severity", "?")
                        count = info.get("count", 0)
                        lines.append(f"     ❌ {pkg_name}  [{severity}] ({count})")
                    if len(vulns) > 10:
                        lines.append(f"     ... 还有 {len(vulns) - 10} 个包")
                else:
                    lines.append("  ✅ npm audit: 未发现已知安全漏洞")
            except (json.JSONDecodeError, ValueError):
                lines.append("  ⚠️  npm audit 输出解析失败")

    except FileNotFoundError:
        lines.append("  ⚠️  npm 未安装")
    except subprocess.TimeoutExpired:
        lines.append("  ⚠️  npm audit 超时")
    except Exception as e:
        lines.append(f"  ⚠️  npm audit 失败: {e}")

    return lines


def _get_outdated_python(path: str) -> List[str]:
    """用 pip list --outdated 检查过期包。"""
    lines = []
    try:
        result = subprocess.run(
            ["pip", "list", "--outdated", "--format=columns"],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip()
        if output:
            lines.append("  📋 pip 过期包:")
            for line in output.split("\n")[2:][:20]:  # skip header
                if line.strip():
                    lines.append(f"     {line}")
        else:
            lines.append("  ✅ pip: 无过期包")
    except Exception as e:
        lines.append(f"  ⚠️  pip outdated 失败: {e}")
    return lines


def deps_check_handler(command: str = "", path: str = "") -> str:
    """
    依赖管理工具 — 检查依赖版本、安全漏洞、过期包。
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return (
            "📗 **deps_check 工具使用帮助**\n\n"
            "子命令:\n"
            "  check    检查依赖安全漏洞 (pip-audit + npm audit)\n"
            "  outdated 列出过期包\n"
            "  tree     分析依赖树\n"
        )

    try:
        if cmd == "check":
            results = []
            py_results = _check_python_deps(base)
            if py_results:
                results.append("🐍 **Python 依赖检查:**")
                results.extend(py_results)
                results.append("")

            node_results = _check_node_deps(base)
            if node_results:
                results.append("📦 **Node 依赖检查:**")
                results.extend(node_results)
                results.append("")

            if not py_results and not node_results:
                results.append("📭 未找到依赖文件 (requirements.txt / pyproject.toml / package.json)")

            return "\n".join(results)

        elif cmd == "outdated":
            results = ["📋 **过期包检查**\n"]
            results.extend(_get_outdated_python(base))
            return "\n".join(results)

        elif cmd == "tree":
            req = _find_requirements(base)
            if not req:
                return "📭 未找到依赖文件"

            try:
                result = subprocess.run(
                    ["pip", "list", "--format=columns"],
                    capture_output=True, text=True, timeout=30,
                )
                output = result.stdout.strip()
                packages = []
                for line in output.split("\n")[2:]:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            packages.append(f"  {parts[0]:30s} {parts[1]}")

                return "🌲 **已安装依赖**\n\n" + "\n".join(packages[:50])
            except Exception as e:
                return f"❌ 获取依赖列表失败: {e}"

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


deps_check_tool_def = Tool(
    name="deps_check",
    description="依赖管理工具，检查依赖安全漏洞、过期包和依赖树。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: check, outdated, tree"},
        "path": {"type": "string", "required": False, "description": "项目路径"},
    },
    returns="string",
    category="dev",
)
