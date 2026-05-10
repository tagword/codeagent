"""
部署工具 — 分析项目并生成 Dockerfile / docker-compose / GitHub Actions CI

子命令:
  analyze      分析项目环境  deploy(command="analyze", path=".")
  dockerfile   生成 Dockerfile  deploy(command="dockerfile", path=".")
  compose      生成 docker-compose.yml  deploy(command="compose", path=".")
  ci           生成 GitHub Actions CI  deploy(command="ci", path=".")
"""

import os

from seed_tools.models import Tool


def _detect_project_type(path: str) -> str:
    """检测项目类型。"""
    has_requirements = os.path.isfile(os.path.join(path, "requirements.txt"))
    has_pyproject = os.path.isfile(os.path.join(path, "pyproject.toml"))
    has_setup = os.path.isfile(os.path.join(path, "setup.py"))
    has_package = os.path.isfile(os.path.join(path, "package.json"))
    has_fastapi = False
    has_flask = False
    has_django = False

    # 扫描 Python 文件
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__", "venv", "env", "node_modules", ".git"))]
        for f in files:
            if not f.endswith(".py"):
                continue
            try:
                with open(os.path.join(root, f), "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                    if "fastapi" in content.lower():
                        has_fastapi = True
                    if "flask" in content.lower():
                        has_flask = True
                    if "django" in content.lower():
                        has_django = True
            except Exception:
                continue

    if has_fastapi:
        return "fastapi"
    if has_flask or has_django:
        return "flask" if has_flask else "django"
    if has_package:
        return "node"
    if has_requirements or has_pyproject or has_setup:
        return "python"
    return "unknown"


def _generate_dockerfile(project_type: str, path: str) -> str:
    """Generate Dockerfile based on project type."""
    lines = []

    if project_type == "node":
        lines.extend([
            "FROM node:20-alpine",
            "",
            "WORKDIR /app",
            "COPY package*.json ./",
            "RUN npm ci --only=production",
            "COPY . .",
            "",
            "EXPOSE 3000",
            'CMD ["node", "index.js"]',
        ])
    elif project_type in ("fastapi", "flask", "python"):
        lines.extend([
            "FROM python:3.11-slim",
            "",
            "WORKDIR /app",
            "",
            "# Install dependencies",
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir -r requirements.txt",
            "",
            "# Copy application",
            "COPY . .",
            "",
            "# Run",
        ])
        if project_type == "fastapi":
            lines.append('CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]')
        elif project_type == "flask":
            lines.append('CMD ["python", "app.py"]')
        else:
            lines.append('CMD ["python", "main.py"]')
    else:
        lines.extend([
            "FROM python:3.11-slim",
            "",
            "WORKDIR /app",
            "COPY . .",
            'CMD ["python", "main.py"]',
        ])

    return "\n".join(lines)


def _generate_compose(project_type: str, path: str) -> str:
    """Generate docker-compose.yml."""
    lines = [
        "version: '3.8'",
        "",
        "services:",
        "  app:",
        "    build: .",
        "    ports:",
    ]

    if project_type == "node":
        lines.append('      - "3000:3000"')
    elif project_type == "fastapi":
        lines.append('      - "8000:8000"')
    elif project_type == "flask":
        lines.append('      - "5000:5000"')
    else:
        lines.append('      - "8000:8000"')

    lines.extend([
        "    volumes:",
        '      - .:/app',
        '    environment:',
        '      - PYTHONUNBUFFERED=1',
    ])

    return "\n".join(lines)


def _generate_ci(project_type: str, path: str) -> str:
    """Generate GitHub Actions CI YAML."""
    lines = [
        "name: CI",
        "",
        "on:",
        "  push:",
        "    branches: [main]",
        "  pull_request:",
        "    branches: [main]",
        "",
        "jobs:",
        "  test:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
    ]

    if project_type == "node":
        lines.extend([
            "      - uses: actions/setup-node@v4",
            "        with:",
            "          node-version: 20",
            "      - run: npm ci",
            "      - run: npm test",
        ])
    else:
        lines.extend([
            "      - uses: actions/setup-python@v5",
            "        with:",
            "          python-version: '3.11'",
            "      - run: pip install -r requirements.txt",
            "      - run: pip install pytest",
            "      - run: pytest",
        ])

    return "\n".join(lines)


def deploy_handler(command: str = "", path: str = "") -> str:
    """
    部署工具 — 分析项目并生成 Dockerfile / docker-compose / GitHub Actions CI。
    """
    cmd = command.strip().lower()
    base = path or os.getcwd()

    if not os.path.exists(base):
        return f"❌ 路径不存在: {base}"

    if not cmd or cmd == "help":
        return (
            "📗 **deploy 工具使用帮助**\n\n"
            "子命令:\n"
            '  analyze    分析项目环境\n'
            '  dockerfile 生成 Dockerfile\n'
            '  compose    生成 docker-compose.yml\n'
            '  ci         生成 GitHub Actions CI\n\n'
            "示例:\n"
            '  deploy(command="analyze", path=".")\n'
            '  deploy(command="dockerfile", path=".")\n'
            '  deploy(command="compose", path=".")\n'
            '  deploy(command="ci", path=".")'
        )

    try:
        ptype = _detect_project_type(base)

        if cmd == "analyze":
            return (
                f"🔍 **项目分析: {os.path.basename(base)}**\n\n"
                f"  项目类型: {ptype}\n"
                f"  Python: {'✅ requirements.txt 存在' if os.path.isfile(os.path.join(base, 'requirements.txt')) else '❌ 未检测到 requirements.txt'}\n"
                f"  Node: {'✅ package.json 存在' if os.path.isfile(os.path.join(base, 'package.json')) else '❌ 未检测到 package.json'}"
            )

        elif cmd == "dockerfile":
            content = _generate_dockerfile(ptype, base)
            out_path = os.path.join(base, "Dockerfile")
            with open(out_path, "w") as f:
                f.write(content)
            return f"✅ **Dockerfile 已生成**\n\n```dockerfile\n{content}\n```"

        elif cmd == "compose":
            content = _generate_compose(ptype, base)
            out_path = os.path.join(base, "docker-compose.yml")
            with open(out_path, "w") as f:
                f.write(content)
            return f"✅ **docker-compose.yml 已生成**\n\n```yaml\n{content}\n```"

        elif cmd == "ci":
            content = _generate_ci(ptype, base)
            ci_dir = os.path.join(base, ".github", "workflows")
            os.makedirs(ci_dir, exist_ok=True)
            out_path = os.path.join(ci_dir, "ci.yml")
            with open(out_path, "w") as f:
                f.write(content)
            return f"✅ **GitHub Actions CI 已生成**\n\n```yaml\n{content}\n```"

        else:
            return f"❌ 未知子命令: {command}"

    except Exception as e:
        return f"❌ 操作失败: {e}"


deploy_tool_def = Tool(
    name="deploy",
    description="部署工具，分析项目并生成 Dockerfile / docker-compose / GitHub Actions CI 配置。",
    parameters={
        "command": {"type": "string", "required": True, "description": "子命令: analyze, dockerfile, compose, ci"},
        "path": {"type": "string", "required": False, "description": "项目路径"},
    },
    returns="string",
    category="dev",
)
