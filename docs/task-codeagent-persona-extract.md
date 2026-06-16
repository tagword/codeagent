# task.md — Persona 剥离 & 独立仓库

## 目标
把 codeagent 内置的 6 个 persona 硬编码从 `codeagent/core/paths.py` 剥离为独立 GitHub 仓库 `codeagent-persona`，通过环境变量 `CODEAGENT_PERSONA_PATH` 引入，附带版本兼容检查。

---

## Wave 1: 创建独立 persona 仓库
  依赖: 无
  验收条件: 仓库目录完整、6 个 persona 文件与当前运行版本一致、VERSION 和 compat 文件到位
  任务:
    - [W1.1] 创建仓库目录结构 `codeagent-persona/persona/`
    - [W1.2] 写入 6 个 persona .md 文件（以当前磁盘运行版本为准）
    - [W1.3] 写入 VERSION（v1.0）和 `codeagent-compat.json`
    - [W1.4] 写入 README.md 和 CHANGELOG.md
    - [W1.5] git init + initial commit

## Wave 2: 修改 codeagent 加载逻辑
  依赖: Wave 1
  验收条件: 设 CODEAGENT_PERSONA_PATH 时从外部 repo 加载persona；不设时回退内置硬编码；版本不兼容时警告并回退
  任务:
    - [W2.1] 在 `codeagent/core/paths.py` 增加 `_load_persona_from_external()` 函数
    - [W2.2] 添加版本兼容校验逻辑
    - [W2.3] 修改 `_ensure_default_persona_files()` 调用新逻辑
    - [W2.4] 配套测试

## Wave 3: 整理内置默认（精简）
  依赖: Wave 2
  验收条件: 内置硬编码保留但精简为真正最小化 fallback
  任务:
    - [W3.1] 精简 `paths.py` 中的 inline defaults 为骨架版
    - [W3.2] 全局搜索引用 `_ensure_default_persona_files` 确认不破坏

## Wave 4: 交付
  依赖: Wave 3
  验收条件: 全链路自测通过
  任务:
    - [W4.1] 测试链条：外部 repo → 加载 → 版本检查 → 回退
    - [W4.2] 提交 + 清场
