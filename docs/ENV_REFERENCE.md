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
| `CODEAGENT_SKIP_FOLDER_PICKER` | （空） | 跳过首次目录选择 |
| `CODEAGENT_WEBUI_TRANSCRIPT_MAX_CHARS` | `12000` | transcript 单条字符上限 |
| `CODEAGENT_WEBUI_TRANSCRIPT_USER_BLOCKS` | `10` | transcript 用户块窗口 |
| `CODEAGENT_WEBUI_TRANSCRIPT_MAX_MESSAGES` | `300` | transcript 消息条数上限 |
| `CODEAGENT_WEBUI_TRANSCRIPT_REASONING_MAX_CHARS` | `50000` | reasoning 展示上限 |

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

图片一律落盘到 `agents/<id>/sessions/llm_sessions/attachments/<session>/`；session 仅存 `[attachment:id]` 引用。主 Agent 上下文不含 base64；理解图片需调用 `vision_analyze` 工具（Web UI 须选择 `supports_vision: true` 的 preset 作为 `vision_llm_id`）。

PDF 文本提取可选依赖：`pip install 'codeagent[vision]'`（`pypdf`）。

## 图片生成（image_generate）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODEAGENT_IMAGE_GEN_PRESET_ID` | （空） | `image_generate` 工具使用的 preset id |
| `CODEAGENT_IMAGE_GEN_DEFAULT_SIZE` | `1024x1024` | 默认输出尺寸 |
| `CODEAGENT_IMAGE_GEN_MAX_COUNT` | `4` | 单次最多生成张数 |
| `CODEAGENT_IMAGE_GEN_TIMEOUT_SEC` | `180` | 生图 API 超时（秒） |

在 `config/seed.models.json` 中为生图模型（如 `dall-e-3`）设置 `"supports_image_gen": true`。Web UI compose 区可选「生图模型」；Agent 调用 `image_generate` 后图片落盘为 attachment，tool trace 与 `/api/attachments/{id}` 可预览。

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
