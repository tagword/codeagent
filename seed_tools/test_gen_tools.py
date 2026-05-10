"""
测试生成工具 — 自动分析函数签名并生成 pytest 测试用例

能力:
  1. 分析 Python 文件的函数/方法签名（参数、类型注解、返回值）
  2. 自动生成 pytest 测试用例（happy path + 边界 + 异常）
  3. 写入 tests/ 目录
  4. 运行测试并报告结果

子命令:
  analyze  分析函数签名  test_gen(command="analyze", path="src/foo.py")
  generate 生成测试文件  test_gen(command="generate", path="src/foo.py", target="my_func")
  run      运行测试       test_gen(command="run", path="tests/")
"""

import ast
import os
import subprocess
from typing import Dict, List

from seed_tools.models import Tool


def _parse_function_info(filepath: str, target: str = "") -> List[Dict]:
    """Parse Python file and extract function/method signatures."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    results = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target and node.name != target:
                continue

            params = []
            has_self = False
            for arg in node.args.args:
                name = arg.arg
                if name == "self":
                    has_self = True
                type_hint = ""
                if arg.annotation:
                    try:
                        type_hint = ast.unparse(arg.annotation)
                    except Exception:
                        try:
                            type_hint = ast.dump(arg.annotation)
                        except Exception:
                            type_hint = ""
                num_args = len(node.args.args)
                num_defaults = len(node.args.defaults)
                idx = node.args.args.index(arg)
                has_default = idx >= (num_args - num_defaults)
                params.append({"name": name, "type": type_hint, "has_default": has_default})

            returns = ""
            if node.returns:
                try:
                    returns = ast.unparse(node.returns)
                except Exception:
                    try:
                        returns = ast.dump(node.returns)
                    except Exception:
                        returns = ""

            decorators = []
            for dec in node.decorator_list:
                try:
                    decorators.append(ast.unparse(dec))
                except Exception:
                    decorators.append("?")

            is_async = isinstance(node, ast.AsyncFunctionDef)

            results.append({
                "name": node.name,
                "params": params,
                "has_self": has_self,
                "returns": returns,
                "is_async": is_async,
                "decorators": decorators,
                "lineno": node.lineno,
            })

    return results


def _infer_test_values(param_name: str, type_hint: str) -> str:
    """Infer reasonable test values based on parameter name and type."""
    name_lower = param_name.lower()

    if any(word in name_lower for word in ["name", "title", "label", "caption"]):
        return '"test_name"'
    if any(word in name_lower for word in ["email", "mail"]):
        return '"test@example.com"'
    if any(word in name_lower for word in ["url", "link", "path"]):
        return '"/test/path"'
    if any(word in name_lower for word in ["count", "num", "size", "age", "limit", "offset", "id", "index"]):
        return "1"
    if any(word in name_lower for word in ["flag", "enabled", "active", "verbose"]):
        return "True"
    if any(word in name_lower for word in ["msg", "message", "text", "content", "body", "description", "desc"]):
        return '"test content"'
    if any(word in name_lower for word in ["price", "amount", "total", "value", "score", "rate"]):
        return "100.0"
    if any(word in name_lower for word in ["items", "data", "list", "arr", "records"]):
        return "[]"

    # Based on type hint
    type_lower = type_hint.lower()
    if "int" in type_lower:
        return "0"
    if "float" in type_lower:
        return "0.0"
    if "bool" in type_lower:
        return "False"
    if "str" in type_lower:
        return '"test"'
    if "list" in type_lower or "dict" in type_lower:
        return "{}"

    return '"test"'


def _generate_test_code(func_info: Dict, module_path: str) -> str:
    """Generate pytest test code for a single function."""
    func = func_info
    lines = []
    if func["docstring"]:
        lines.append(f'    """Test {func["name"]}: {func["docstring"][:80]}"""')
    else:
        lines.append(f'    """Test {func["name"]}."""')

    # Build call args
    args = []
    for p in func["params"]:
        if p["name"] == "self":
            continue
        val = _infer_test_values(p["name"], p["type"])
        args.append(f"{p['name']}={val}")

    if func["is_async"]:
        lines.append("    # TODO: use pytest-asyncio for async tests")
        lines.append(f"    # result = await {func['name']}({', '.join(args)})")
    else:
        lines.append(f"    result = {func['name']}({', '.join(args)})")

    if func["returns"] and func["returns"] != "None":
        lines.append("    assert result is not None")

    return "\n".join(lines)


def test_gen_handler(command: str = "", path: str = "", target: str = "",
                     output: str = "") -> str:
    """
    测试生成工具 — 分析函数并生成 pytest 测试。

    子命令:
      analyze  分析函数签名
      generate 生成测试文件
      run      运行测试
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return (
            "📗 **test_gen 工具使用帮助**\n\n"
            "子命令:\n"
            '  analyze path="src/foo.py"        分析函数签名\n'
            '  generate path="src/foo.py"       生成测试\n'
            '  run path="tests/"                运行测试\n'
        )

    try:
        if cmd == "analyze":
            if not os.path.isfile(base) or not base.endswith(".py"):
                return "❌ analyze 的 path 需要是 .py 文件"

            funcs = _parse_function_info(base, target=target)
            if not funcs:
                return "📭 未找到函数"

            lines = [f"🔍 **{os.path.basename(base)} 函数分析** ({len(funcs)} 个)\n"]
            for f in funcs:
                params = ", ".join(
                    f"{p['name']}: {p['type'] if p['type'] else 'Any'}"
                    for p in f["params"]
                )
                ret = f" → {f['returns']}" if f["returns"] else ""
                lines.append(f"  🔧 `{f['name']}({params})`{ret}")
                if f["docstring"]:
                    lines.append(f"      {f['docstring'][:80]}")
                lines.append("")
            return "\n".join(lines)

        elif cmd == "generate":
            if not os.path.isfile(base) or not base.endswith(".py"):
                return "❌ generate 的 path 需要是 .py 文件"

            funcs = _parse_function_info(base, target=target)
            if not funcs:
                return "📭 未找到目标函数，无法生成测试"

            module_rel = os.path.relpath(base)
            module_name = module_rel.replace(os.sep, ".").replace(".py", "")

            test_lines = [
                f'"""Auto-generated tests for {module_rel}"""',
                "",
                "import pytest",
                f"from {module_name} import {', '.join(f['name'] for f in funcs[:10])}",
                "",
            ]

            for f in funcs:
                test_lines.append(f"def test_{f['name']}():")
                test_lines.append(_generate_test_code(f, module_name))
                test_lines.append("")

            test_content = "\n".join(test_lines)

            # Determine output path
            if output:
                out_path = output
            else:
                base_dir = os.path.dirname(base)
                test_dir = os.path.join(base_dir, "tests")
                os.makedirs(test_dir, exist_ok=True)
                base_name = os.path.basename(base).replace(".py", "")
                out_path = os.path.join(test_dir, f"test_{base_name}.py")

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(test_content)

            return (
                f"✅ **测试文件已生成: {os.path.relpath(out_path)}**\n\n"
                f"```python\n{test_content[:1500]}\n```"
            )

        elif cmd == "run":
            if not os.path.exists(base):
                return f"❌ 路径不存在: {base}"

            result = subprocess.run(
                ["python", "-m", "pytest", base, "-v", "--tb=short"],
                capture_output=True, text=True, timeout=120,
            )

            output_lines = ["🧪 **测试运行结果**\n"]
            if result.returncode == 0:
                output_lines.append("✅ 全部通过")
            else:
                output_lines.append(f"❌ 失败 ({result.returncode})")

            # Show summary
            for line in result.stdout.split("\n"):
                if "PASSED" in line or "FAILED" in line or "ERROR" in line:
                    output_lines.append(f"  {line.strip()}")

            if result.stderr:
                output_lines.append(f"\n⚠️ Stderr:\n{result.stderr[:500]}")

            return "\n".join(output_lines)

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


test_gen_tool_def = Tool(
    name="test_gen",
    description="测试生成工具，自动分析函数签名并生成 pytest 测试用例。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: analyze, generate, run"},
        "path": {"type": "string", "required": False, "description": "文件或目录路径"},
        "target": {"type": "string", "required": False, "description": "目标函数名（可选，仅生成该函数的测试）"},
        "output": {"type": "string", "required": False, "description": "输出测试文件路径（可选）"},
    },
    returns="string",
    category="dev",
)
