# Code Agent 环境变量（`CODEAGENT_*`）

**Code Agent** 是构建在 [Seed](../seed/) 之上的产品层。本产品**长期保留** `CODEAGENT_*` 前缀，用于 Web UI、skills、日记、计费展示等产品行为。

**默认数据目录**：`~/.codeagent`（`CODEAGENT_HOME`）。启动时同步为内核的 `SEED_PROJECT_ROOT`，与仅用 Seed 时的 `~/.seed` 分离。见 [`MULTI_PRODUCT.md`](MULTI_PRODUCT.md)。

通用内核与集成（LLM、沙箱、MCP、hooks、会话存储等）使用 **`SEED_*`**，见 [`seed/docs/ENV_REFERENCE.md`](../seed/docs/ENV_REFERENCE.md)。

---

## 产品与 Web UI

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_HOME` | `~/.codeagent` | 产品数据根（agents、config、会话等） |
| `CODEAGENT_PROJECT_ROOT` | 同 `CODEAGENT_HOME` | 可选显式覆盖数据根 |
| `CODEAGENT_AGENT_ID` | `default` | 默认 logical agent id |
| `CODEAGENT_LOG_LEVEL` | `INFO` | 服务日志级别 |
| `CODEAGENT_PORT` | `8765` | HTTP 端口 |
| `CODEAGENT_WEBUI_TOKEN` | （空） | Web UI 访问令牌 |
| `CODEAGENT_SKIP_FOLDER_PICKER` | （空） | 跳过原生目录选择（无 GUI 的 Linux 服务器建议设为 `1`，改手填路径） |
| `CODEAGENT_LLM_PROJECTION_AUDIT` | `0` | `1` 时每轮 LLM 请求前写入完整 `messages` 快照（经 bridge → `SEED_*`） |
| `CODEAGENT_LLM_PROJECTION_AUDIT_DIR` | （空） | 可选覆盖审计目录（默认 `agents/.../sessions/_audit/<session>/`） |
| `CODEAGENT_WEBUI_SESSION_HISTORY_MAX_CHARS` | `12000` | 会话历史单条字符上限 |
| `CODEAGENT_WEBUI_SESSION_HISTORY_USER_BLOCKS` | `10` | 历史用户块窗口 |
| `CODEAGENT_WEBUI_SESSION_HISTORY_MAX_MESSAGES` | `300` | 单次 API 最多消息条数 |
| `CODEAGENT_WEBUI_SESSION_HISTORY_REASONING_MAX_CHARS` | `50000` | reasoning 展示上限 |

## Skills 与日记（Phase 1）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_SKILLS_AUTO` | `1` | `0` 关闭按 query 动态选 skill |
| `CODEAGENT_SKILLS_TOP_K` | `3` | 每轮最多注入 skill 数 |
| `CODEAGENT_DIARY` | `1` | `0` 关闭日记 |
| `CODEAGENT_DIARY_KEEP_DAYS` | `7` | 日记保留天数 |

## 聊天与工具策略

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_CHAT_USER_ROUNDS` | `12` | API 投影保留用户轮数 |
| `CODEAGENT_MAX_TOOL_ROUNDS` | `24` | 单轮 chat 最大工具轮次 |
| `CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT` | `0` | 触顶后自动续跑 |
| `CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS` | `4` | 自动续跑最大段数 |
| `CODEAGENT_CHAT_MAX_TOOL_ROUNDS_DEFAULT` | `16` | Web 设置页默认工具轮次 |
| `CODEAGENT_AGENT_TOOLS_NO_CACHE` | `0` | `1` 禁用 per-agent 工具缓存 |
| `CODEAGENT_AGENT_TOOLS_MODE` | （空） | `all` 时不按 tools.json 过滤 |

## 多模态附件与 Vision（工具优先）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_ATTACHMENTS_MAX_COUNT` | `8` | 单条消息最多附件数 |
| `CODEAGENT_ATTACHMENTS_MAX_BYTES` | `20971520` (20MB) | 单文件大小上限 |
| `CODEAGENT_ATTACHMENTS_DIR_MAX_FILES` | `32` | 目录批次最多图片数 |
| `CODEAGENT_ATTACHMENTS_ALLOWED_MIME` | `image/,application/pdf,text/` | 允许的 MIME 前缀 |
| `CODEAGENT_IMAGE_DIR_ALLOWED_GLOB` | `*.png,*.jpg,...` | 目录扫描 glob |
| `CODEAGENT_VISION_MODE` | `tool` | 预留；首期仅工具优先 |
| `CODEAGENT_VISION_PRESET_ID` | （空） | CLI/工具 fallback 的 Vision preset id |
| `CODEAGENT_VISION_ANALYZE_MAX_IMAGES` | `4` | 单次 `vision_analyze` 最多图片数 |
| `CODEAGENT_VISION_MAX_TOKENS` | `4096` | Vision RPC max_tokens |
| `CODEAGENT_VISION_RESULT_MAX_CHARS` | `12000` | 超长分析走 artifact 阈值 |

图片一律落盘到 `agents/<id>/sessions/attachments/<session>/`；session 仅存 `[attachment:id]` 引用。主 Agent 上下文不含 base64。识图二选一（可并存）：**多模态 LLM** — `vision_analyze` + Web UI 选择 `supports_vision` 预设；**MiniMax MCP** — 配置 `config/mcp.json` 的 `MiniMax` 服务后，可无 vision 预设上传图片，Agent 通过 `attachment_resolve_path` + `mcp__MiniMax__understand_image` 理解。视频分析仍须 vision 预设 + `video_analyze`。

PDF 文本提取可选依赖：`pip install 'codeagent[vision]'`（`pypdf`）。

## 图片生成（image_generate）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_IMAGE_GEN_PRESET_ID` | （空） | `image_generate` 工具使用的 preset id |
| `CODEAGENT_IMAGE_GEN_DEFAULT_SIZE` | `1024x1024` | 默认输出尺寸 |
| `CODEAGENT_IMAGE_GEN_MAX_COUNT` | `4` | 单次最多生成张数 |
| `CODEAGENT_IMAGE_GEN_TIMEOUT_SEC` | `180` | 生图 API 超时（秒） |

在 `config/seed.models.json` 中为生图模型（如 `dall-e-3`）设置 `"supports_image_gen": true`，并建议设置 `"provider"`（如 `openai`、`openai_compatible`）。Web UI 预设表单可选择 Provider，按服务商切换聊天/生图协议；未填时按 Base URL 推断（如 `api.deepseek.com` → DeepSeek 协议）。Agent 调用 `image_generate` 后图片落盘为 attachment，tool trace 与 `/api/attachments/{id}` 可预览。

## 音乐生成（music_generate）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_MUSIC_GEN_PRESET_ID` | （空） | `music_generate` 工具使用的 preset id |
| `CODEAGENT_MUSIC_GEN_TIMEOUT_SEC` | `300` | 音乐生成 API 超时（秒） |

在 `config/seed.models.json` 中为 MiniMax 音乐模型（如 `music-2.6`）设置 `"supports_music": true`，`provider: minimax`。Web UI compose 区可选择音乐 preset；Agent 调用 `music_generate` 后 MP3 落盘为 attachment，tool trace 内嵌播放器预览。文档：[MiniMax 音乐生成](https://platform.minimaxi.com/docs/guides/music-generation)。

## MCP（MiniMax Token Plan 等）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SEED_MCP_ENABLED` | `1` | MCP 桥接总开关 |
| `SEED_MCP_REGISTER_TOOLS` | `1` | 将 MCP 工具注册为 `mcp__<server>__<tool>` 供 Agent 调用 |
| `SEED_MCP_CALL_TIMEOUT` | `120` | 单次 MCP 调用超时（秒） |
| `SEED_MCP_INIT_TIMEOUT` | `180` | MCP 握手 `initialize` 超时（秒）；首次 `uvx minimax-coding-plan-mcp` 拉包可能需 1–3 分钟 |

**Web UI → 配置 → MCP 服务**：管理 `config/mcp.json` 中的多个 stdio MCP（不限 MiniMax）。

| 操作 | 说明 |
|------|------|
| **+ 添加 MCP** | 模板：MiniMax Token Plan、uvx 包、npx 包、自定义 stdio |
| **卡片** | 展开编辑；「测试」探测连接并列出工具；「删除」后需点「保存全部」 |
| **保存全部** | 写入 `mcp.json` 并重载 MCP 管理器 |

**通用字段**：`command`、`args`、`env`（每行 `KEY=value`）、可选 `cwd`。Agent 工具名为 `mcp__<服务ID>__<工具名>`。

**MiniMax 模板**（ID 固定 `MiniMax`）：Token Plan Key、可选朗读 Key；工具含 `understand_image`、`web_search`。与 vision preset 可并存。

文档：[MiniMax Token Plan MCP](https://platform.minimaxi.com/docs/guides/token-plan-mcp-guide)

## 气泡朗读（TTS）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_TTS_VOICE_ID` | `male-qn-qingse` | 默认音色 |
| `CODEAGENT_TTS_MODEL` | `speech-2.8-turbo` | 默认 TTS 模型 |
| `CODEAGENT_TTS_API_KEY` | （空） | **开放平台按量 API Key**（优先于 Token Plan Key） |
| `CODEAGENT_TTS_API_HOST` | `https://api.minimaxi.com` | TTS API Host |
| `CODEAGENT_TTS_MAX_CHARS` | `2000` | 单次朗读最大字符数 |
| `CODEAGENT_TTS_TIMEOUT_SEC` | `120` | TTS 请求超时（秒） |

Web UI **配置 → MCP 服务** 中 MiniMax 卡片可填「朗读 API Key（开放平台按量，可选）」，写入 `mcp.json` 的 `MINIMAX_TTS_API_KEY`。

**注意**：Token Plan Key（`sk-cp-…`）与聊天/MCP 共用，但 **TTS（Speech）有独立的每日字符额度**。若 API 返回 `2056` 且 `(0/0 used)`，表示当前套餐**未分配**朗读额度（不是已用完），需填写开放平台按量 Key 或升级含 Speech 额度的 Token Plan 档位。

本地输出目录默认：`~/.codeagent/mcp-minimax-out`（`MINIMAX_MCP_BASE_PATH`）。文档：[MiniMax Token Plan MCP](https://platform.minimaxi.com/docs/guides/token-plan-mcp-guide)。

## 多模型预设（Web UI）

配置页 **多模型预设** 按能力分组（对话 / 识图 / 生图 / 音频 / 音乐 / 朗读）。每条 preset 对应一种用途，保存时 UI 自动写入 `use_type` 与 `supports_*`，一般无需手改 `config/seed.models.json`。

**自部署示例（Ollama）**

1. 对话：用途选「对话」→ 服务商 **Ollama** → Base URL `http://127.0.0.1:11434/v1` → 模型 `qwen2.5:7b`
2. 识图：用途选「识图」→ 同上连接 → 模型 `llava:13b`；或点「复制连接」从对话 preset 带入 Base URL
3. 聊天页 **模型栈** 中分别选用；仅配置一条时自动选中

**能力标记（由 UI 自动写入）**

| 用途 | `use_type` | `supports_*` |
|------|------------|--------------|
| 对话 | `chat` | （无） |
| 识图 | `vision` | `supports_vision: true` |
| 生图 | `image` | `supports_image_gen: true` |
| 音频 | `audio` | `supports_audio: true` |
| 音乐 | `music` | `supports_music: true` |
| 朗读 | `speech` | `supports_speech: true` |

自部署服务商（Ollama、OpenAI 兼容、SGLang、自定义）在表单中始终显示 Base URL / 模型名；云厂商从目录选模型即可。

### Preset 字段 `provider`

| 值 | 聊天协议 | 生图协议（勾选 supports_image_gen 时） |
|----|----------|----------------------------------------|
| `volcengine` | OpenAI 兼容 `/v1/chat/completions` | `volcengine_images` → Seedream `/images/generations` |
| `minimax` | OpenAI 兼容 `/v1/chat/completions` | `minimax_image` → `POST /v1/image_generation`，模型如 `image-01` |
| `deepseek` | DeepSeek thinking + reasoning_content | OpenAI `/images/generations`（需自建网关） |
| `openai` / `openai_compatible` | 标准 OpenAI 兼容 | `openai_images` |
| `sglang` | SGLang separate_reasoning | `openai_images`（若网关支持） |
| `custom` / 空 | 按 URL 推断 | 同上 |

统一参数与图生图规则见 `codeagent/docs/IMAGE_GEN_PROVIDERS.md`。

内置目录：`GET /api/ui/llm/providers` 或 `GET /api/ui/llm/presets` 响应中的 `providers`。

## 视频 / 音频（audio_transcribe / video_analyze）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_AUDIO_PRESET_ID` | （空） | 音频转写 preset（如 `whisper-1`） |
| `CODEAGENT_MEDIA_MAX_BYTES` | `104857600` (100MB) | 单条 video/audio 附件上限 |
| `CODEAGENT_VIDEO_MAX_FRAMES` | `8` | `video_analyze` 最多采样帧数 |
| `CODEAGENT_VIDEO_FRAME_INTERVAL_SEC` | `2` | 抽帧间隔（秒） |
| `CODEAGENT_AUDIO_TRANSCRIBE_TIMEOUT_SEC` | `300` | 转写 API 超时 |
| `CODEAGENT_MEDIA_RESULT_MAX_CHARS` | `12000` | 超长结果走 artifact |

默认允许 MIME 前缀含 `video/`、`audio/`（见 `CODEAGENT_ATTACHMENTS_ALLOWED_MIME`）。

- **音频**：preset 设 `"supports_audio": true`（模型如 `whisper-1`），Agent 调 `audio_transcribe`
- **视频**：需 **vision preset** + 服务端安装 **ffmpeg**；Agent 调 `video_analyze`（抽帧 + 可选音轨转写）

Web UI compose 区「音频转写」下拉对应 `audio_llm_id`；视频上传需「多模态模型」。

## 摄像头（Web UI）

浏览器 **📷 摄像头** 按钮：`getUserMedia` 实时预览 → 单张拍照或每 3 秒定时截帧（最多 8 张），帧落盘为 attachment 后随消息发送。移动端 fallback：`capture="environment"` 调起系统相机。需 HTTPS 或 localhost，且已选 vision preset。

## 与 Seed 的关系

- 内核项：写在 **`config/seed.env`**（`SEED_*`）。
- 产品项：写在 **`config/codeagent.env`**（`CODEAGENT_*`）；两个文件会一并加载（见 `seed.integrations.env_config`）。
- 也可写在同一文件或进程环境中；启动时调用 `codeagent.core.bootstrap.bootstrap_codeagent_runtime()`。
- 启动或保存配置后，`codeagent.core.seed_bridge.bridge_codeagent_env_to_seed()` 会把与内核同后缀的 `CODEAGENT_*` 复制为 `SEED_*`（仅当 `SEED_*` 未设置时），供 Seed / seed-tools 使用。

---

## 相关文档

- [`ROADMAP.md`](../../ROADMAP.md) — `SEED_*` / `CODEAGENT_*` 分层与 Phase 6.7–6.8
- [`PUBLIC_API.md`](../../PUBLIC_API.md) — 包依赖与公开面
