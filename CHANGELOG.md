# Changelog

## 1.1.8 (2026-07-24)

- feat: 项目级 skills 支持 — 自动扫描 `.codeagent/skills/`，Web UI 技能面板
- fix: 纯文本回复路径的流式占位符删除，覆盖无 tool rounds 场景
- fix: `_on_text_delta` 移除上一个流式占位符防止会话落盘重复
- docs: PyPI 安装说明 (tagword-codeagent)
- chore: 仓库清理 — 移除误入目录、整理 .gitignore、迁移构建脚本

## 1.1.7 (2026-07-20)

- feat(webui): mermaid 图表渲染 + PNG 放大/下载
- fix: 新用户无孩子时显示"添加宝贝"空状态而非白屏

## 1.1.6 (2026-07-08)

- fix: seed 私有依赖改为 git+https URL，`pip install -e .` 可直接安装
- chore: 添加 rules.md 和 upload-weapp.sh 自动上传脚本

## 1.1.5 (2026-07-07)

- fix: 根治 tool messages 在 compact 中丢失的问题 + WebUI 渲染修复
- clean: 移除 `_on_tool_round_persist` 中冗余的 `_streaming` 清理逻辑
- fix: 历史消息 API 不再过滤 `_streaming` 标记

## 1.1.4-p2 (2026-07-06)

- feat: 发布流程 pipeline — collector → raw → review → publish (WebUI + API + MCP)
- feat: 多宝贝家庭支持 — 快速入口可切换孩子
- feat: weapp 首页简化 — 选宝贝自动推荐主题/长度/语种
- feat: 工具链折叠到组容器，默认收起减少视觉干扰
- feat: 收藏按钮移至播放器左上角 + 分享按钮移至进度条右上角
- feat: 神经网络页重写 — 数据流动动画 + 实际应用案例
- feat: pcbagent 核心 + Web PCB Viewer
- feat: 播放器新增播放模式切换——连播/循环/随机
- fix: CDN marked/purify 替换为本地文件
- fix: Git 代理保存时同步写入 git config --global
- fix: MCP 连接失败不再阻塞 WebUI 加载
- refactor: 聊天对话区三刀手术切割

## 1.1.4 (2026-06-26)

- fix: 会话运行状态管理 — 三个根因修复
- fix: 项目目录对话框浏览按钮+路径展开+刷新联动

## 1.1.3 (2026-06-26)

- fix(webui): 修复 WS 断连后 running 状态丢失 + WS 事件不刷新会话列表 + DOM 重建后闪烁

## 1.1.2 (2026-06-26)

- 与 1.1.1 同日发布，包含以下补充修复

## 1.1.1 (2026-06-26)

### 多 Agent 体系 (M1)
- feat: Agent CRUD API + presets API + sessions API
- feat: Agent 管理前端页面 — 列表、创建、编辑、切换
- feat: Agent 详情页增强 — 描述、工具编辑、技能/MD 按 Agent 隔离
- feat: Agent 气泡着色 + 名称显示
- feat: WS 连接改造 — 切换 agent 时重连
- feat: Agent 切换器移至侧栏 brand，等宽不换行

### Team / Hub
- feat: Team CRUD API + Run engine + 管理前端
- feat: Hub SSE 服务端 + 前端面板
- feat: 自愈引擎 + 恢复 API + supervisord 配置
- feat: 健康看板 + CSS
- feat: M1 team foundation — config parsing, auto-registration, dispatch flow

### WebUI 重构
- refactor: 01c-session.js 拆 5 文件 (thinking / identity / tree / tree-menus / utilities)
- refactor: 11f-env-llm-presets.js / 11h-env-mcp.js 各拆 3 文件
- refactor: 00-storage.js 集中 localStorage/sessionStorage key
- refactor: 04-ws-connect.js onmessage handler 改派发表
- refactor: 抽 00-utils.js 统一 6 个散落的 escape 实现
- refactor(webui): switchToPage 回归自然布局，删除 31 行冗余 JS
- perf: 主区 scroll 检测 80ms 节流；17+8 次 getElementById 散落调用 → 集中 IIFE 缓存

### WebUI 新功能
- feat: 停止按钮交互优化 — 点按后显示 "⏳ 正在完成…"，完成时显示 "✅ 已停止。"
- feat: 上下文窗口上限 context_limit 加入环境配置页
- feat: 聊天与会话配置增加「最大输出 tokens」字段
- feat: preset 表单增加「最大输出 tokens」设置
- feat: 代码块复制按钮改为浮动右上角 style（隐藏式，hover 显现）
- feat: 项目规划面板同步展示 Agent 的 docs/ 和 plans/ 文档
- feat: 项目名右侧增加 + 按钮，hover 时显示，快速新建会话
- feat: 输入框草稿本地持久化（跨会话切换保留输入内容）
- feat: bootstrap 引导页替换为 CodeAgent 专属版（含配置指南和目录说明）
- feat: 流式生成时新增一行才触发滚动，避免同一行逐字下拉
- feat: WebUI MCP skill slash command — /skill
- feat(mcp): Streamable HTTP support
- feat: WebUI Git 凭据/SSH 管理
- feat(webui+cli): video_generate end-to-end wiring
- feat: per-session model override (model stack)

### 移动端
- fix: 手机视图顶栏抽屉覆盖全屏无法关闭根因修复
- fix: compose dock 按钮被 activity-bar 遮挡/键盘收起吞事件
- fix: 手机端项目列表按钮始终显示（桌面 hover 才显示）
- fix: token 为 0 时不显示红色；手机端 Enter 换行不发送

### 安装/脚本
- feat: Windows 安装/启动脚本 + run.sh 支持 seed 包自动安装
- feat: 一键运行脚本 run.sh + 国内源检测 + README 更新
- fix: 全面重写安装脚本，修复所有已知问题
- fix: 所有安装/启动脚本统一加超时 + 重试 + 可见输出
- fix: 跨系统自动安装 libxml2/libxslt（编译 lxml 所需）

### 其他
- feat: 添加 /api/health 健康检查端点 + 默认 persona 模板
- feat: .codeagent/{agent_id}/ 路径管理体系落地
- feat: 运行时环境信息块 (time + OS + workdir)
- feat: CodeAgent 扩展变量 + memory.md 渲染
- perf: cache system prompt per session via get_cached_system_prompt()
- refactor: token_counter → seed.core，消除逆向依赖
- refactor: web/ + webui/ + webui.html 合并为一个目录
- refactor: self_healing 配置改为惰性求值 + 安全 env 解析 + 范围约束
- refactor: 移除 codeagent/core/ 死代码 (image_gen/music/video/token_counter/llm)
- clean: 移除死代码目录（apps/tray、storage、integrations）和 webui 开发期文件
- clean: 移除未使用的 Monaco 文件编辑器组件

## 1.1.0 (2026-06-02)

- 多模态工具链：附件、图片理解、图像生成、音乐生成
- 会话存储重构与 Web UI 历史加载
- TTS 语音合成与模型栈设置
- MCP 环境配置 UI
- Tool-first multimodal pipeline with attachments, Web UI, and camera
- 移动端 WebUI + macOS 打包工具链
- auto_continue — 达到 max_tool_rounds 后自动续接
- 停止按钮 — ACTIVE_CHAT_CANCELS + is_chat_cancelled 完整链路
- 同 session 并发消息注入 + PENDING_INJECTIONS 队列
- 上下文 token 用量指示器 + DeepSeek V3 精确计费
- macOS .app bundle + DMG 安装包 + CI 自动构建
- 安装脚本 install.sh
- 代码全面清理和 ruff 修复

## 1.0.0 (2025-05-08)

- 首个公开发布版本
- 基础 Agent 执行引擎
- Web UI 界面
- 会话管理
- 工具调用系统
- 记忆存储
