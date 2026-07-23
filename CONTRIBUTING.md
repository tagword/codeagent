# Contributing

## 开发环境

```bash
# 克隆
git clone https://github.com/tagword/codeagent
cd codeagent

# 虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装（开发者模式）
pip install -e ".[dev,lint,yaml,vision]"
```

## 依赖关系

CodeAgent 依赖以下核心包（三者均为私有仓库，通过 git+https 安装）：

| 包 | PyPI | 仓库 |
|----|------|------|
| `seed-kernel` | `seed-kernel` | `github.com/tagword/seed` |
| `seed-toolbox` | `seed-toolbox` | `github.com/tagword/seed-tools` |
| `seed-model-providers` | `seed-model-providers` | `github.com/tagword/seed-model-providers` |

```bash
# 如需本地调试依赖包，可 clone 后 pip install -e 指向本地路径
```

## 运行

```bash
# CLI 模式
codeagent

# Web UI
codeagent --serve
# 或直接启动 uvicorn
uvicorn codeagent.server.app_factory:create_app --reload
```

## 测试

```bash
# 全部测试
pytest

# 指定文件
pytest tests/test_xxx.py

# 带覆盖率
pytest --cov=codeagent
```

## 代码规范

使用 ruff 做 lint 和格式化：

```bash
# 检查
ruff check .

# 自动修复
ruff check --fix .

# 格式化
ruff format .
```

配置见 `pyproject.toml` 中的 `[tool.ruff]` 段落。

## 提交规范

提交消息使用约定式提交格式：

```
<type>: <简短描述>

type 取值:
  feat:    新功能
  fix:     修复
  refactor: 重构（非功能非修复）
  perf:    性能优化
  docs:    文档
  chore:   构建/工具/依赖
  clean:   删除死代码
  test:    测试
  plan:    计划/设计文档
```

示例：
- `feat(webui): 项目规划面板同步展示 Agent 的 docs/ 和 plans/ 文档`
- `fix: 根治 tool messages 在 compact 中丢失的问题`
- `chore: bump version to 1.1.8`

## 分支策略

- `main` — 稳定分支，所有发布从 main 打 tag
- 功能开发直接在 main 上提交（单人开发）；涉及多人协作时使用 feature 分支

## 发布流程

参见 `.codeagent/skills/pypi-release/SKILL.md`（内部 skill，不公开）。

简要步骤：
1. 更新 `pyproject.toml` 和 `codeagent/__init__.py` 的版本号
2. 更新 `CHANGELOG.md`
3. `git commit` + `git tag vX.Y.Z`
4. `python -m build` + `twine upload dist/*`
5. `git push origin main --tags`

## 项目结构

```
codeagent/
├── codeagent/           # 主代码
│   ├── cli/             # CLI 入口
│   ├── core/            # 核心逻辑（路径、技能选择、prompt 增强等）
│   ├── runtime/         # 运行时（prompt enrichment、compact summarizer 等）
│   ├── server/          # Web 服务器（FastAPI/Starlette）
│   ├── web/static/      # Web UI 前端（HTML/CSS/JS）
│   ├── persona_defaults/# 默认人格模板（随包安装）
│   └── skills/          # 技能选择引擎
├── .codeagent/          # 本地开发配置（不提交 Git）
│   ├── default/         # 默认 Agent 状态
│   └── skills/          # 项目级发布 skill
├── packaging/           # 构建/打包脚本
├── assets/              # 图标等资源文件
├── pyproject.toml       # 项目配置与版本
└── README.md
```
