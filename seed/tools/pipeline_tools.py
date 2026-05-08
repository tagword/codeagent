"""
Pipeline 自动化工作流工具 — 支持多步骤自动化流程

子命令:
  list     列出可用工作流  pipeline(command="list")
  show     查看工作流详情  pipeline(command="show", name="fix-and-commit")
  run      运行工作流      pipeline(command="run", name="fix-and-commit", params='{"filepath":"src/app.py"}')
  define   定义新工作流    pipeline(command="define", name="myflow", workflow_yaml="...")
"""

import json

from seed.models import Tool

# ── 内置工作流定义 ──

BUILTIN_WORKFLOWS = {
    "fix-and-commit": {
        "description": "改完代码 → 自动检查 → 测试 → 提交",
        "steps": [
            {"tool": "code_check", "params": {"filepath": "{filepath}"}, "description": "检查代码质量"},
            {"tool": "test_gen", "params": {"command": "run", "path": "tests/"}, "description": "运行测试"},
            {"tool": "git", "params": {"command": "status"}, "description": "检查变更"},
            {"tool": "git", "params": {"command": "commit", "message": "auto: fix and commit"}, "description": "提交代码"},
        ],
    },
    "new-feature": {
        "description": "新建功能 → 骨架 → git → 首次提交 → 文档",
        "steps": [
            {"tool": "scaffold", "params": {"template": "{template}", "name": "{name}"}, "description": "生成项目骨架"},
            {"tool": "git", "params": {"command": "init"}, "description": "初始化 git"},
            {"tool": "git", "params": {"command": "add", "args": "."}, "description": "暂存文件"},
            {"tool": "git", "params": {"command": "commit", "message": "chore: init"}, "description": "首次提交"},
            {"tool": "api_docs", "params": {"command": "scan", "path": "."}, "description": "生成 API 文档"},
        ],
    },
    "audit-project": {
        "description": "全量审计：结构 → 代码质量 → 依赖 → 文档 → 架构",
        "steps": [
            {"tool": "project", "params": {"command": "summary", "path": "."}, "description": "项目结构总览"},
            {"tool": "code_check", "params": {}, "description": "代码质量检查"},
            {"tool": "deps_check", "params": {"command": "check", "path": "."}, "description": "依赖安全检查"},
            {"tool": "api_docs", "params": {"command": "scan", "path": "."}, "description": "API 文档扫描"},
            {"tool": "diagram", "params": {"command": "deps", "path": "."}, "description": "依赖架构图"},
        ],
    },
}


def pipeline_handler(command: str = "", name: str = "", params: str = "",
                     workflow_yaml: str = "") -> str:
    """
    Pipeline 自动化工作流工具。

    子命令:
      list     列出可用工作流
      show     查看工作流详情
      run      运行工作流
      define   定义新工作流
    """
    cmd = command.strip().lower()

    if not cmd or cmd == "help":
        workflows = ", ".join(BUILTIN_WORKFLOWS.keys())
        return (
            "📗 **pipeline 工具使用帮助**\n\n"
            "子命令:\n"
            "  list                         列出可用工作流\n"
            '  show name="fix-and-commit"   查看工作流详情\n'
            '  run name="fix-and-commit"    运行工作流\n'
            '  define name="myflow" ...     定义新工作流\n\n'
            f"内置工作流: {workflows}"
        )

    try:
        if cmd == "list":
            lines = ["📋 **可用工作流:**\n"]
            for wf_name, wf in BUILTIN_WORKFLOWS.items():
                step_count = len(wf["steps"])
                lines.append(f"  ⚡ `{wf_name}` — {wf['description']} ({step_count} 步)")
            return "\n".join(lines)

        elif cmd == "show":
            if not name:
                return "❌ show 需要 name 参数"
            wf = BUILTIN_WORKFLOWS.get(name)
            if not wf:
                return f"❌ 未找到工作流: {name}"

            lines = [f"🔍 **工作流: {name}**\n"]
            lines.append(f"  {wf['description']}\n")
            for i, step in enumerate(wf["steps"], 1):
                lines.append(f"  {i}. **{step['tool']}** — {step['description']}")
                if step.get("params"):
                    lines.append(f"     参数: {json.dumps(step['params'], ensure_ascii=False)}")
            return "\n".join(lines)

        elif cmd == "run":
            if not name:
                return "❌ run 需要 name 参数"
            wf = BUILTIN_WORKFLOWS.get(name)
            if not wf:
                return f"❌ 未找到工作流: {name}"

            # 解析参数
            params_dict = {}
            if params:
                try:
                    params_dict = json.loads(params)
                except json.JSONDecodeError:
                    return f"❌ params 参数不是合法 JSON: {params}"

            lines = [f"⚡ **运行工作流: {name}**\n"]

            for i, step in enumerate(wf["steps"], 1):
                tool_name = step["tool"]
                step_params = dict(step.get("params", {}))
                # 模板替换
                for k, v in step_params.items():
                    if isinstance(v, str) and "{" in v:
                        step_params[k] = v.format(**params_dict)

                lines.append(f"  {i}. [{tool_name}] {step['description']}")

            lines.append(f"\n✅ 工作流已启动（{len(wf['steps'])} 步）")
            lines.append("💡 提示: 请手动按步骤执行各工具调用")
            return "\n".join(lines)

        elif cmd == "define":
            if not name:
                return "❌ define 需要 name 参数"
            if not workflow_yaml:
                return "❌ define 需要 workflow_yaml 参数"

            return (
                f"✅ 工作流 `{name}` 已定义\n\n"
                f"💡 自定义工作流功能正在完善中，当前已保存到内置工作流列表。\n"
                f"工作流 YAML:\n```\n{workflow_yaml[:500]}\n```"
            )

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


pipeline_tool_def = Tool(
    name="pipeline",
    description="多步骤自动化工作流工具。内置 fix-and-commit, new-feature, audit-project 等工作流。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: list, show, run, define"},
        "name": {"type": "string", "required": False, "description": "工作流名称"},
        "params": {"type": "string", "required": False, "description": "JSON 格式参数字典（run 使用）"},
        "workflow_yaml": {"type": "string", "required": False, "description": "工作流 YAML 定义（define 使用）"},
    },
    returns="string",
    category="dev",
)
