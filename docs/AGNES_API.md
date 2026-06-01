# Agnes AI API 参考（CodeAgent 集成）

本文档整理 [Agnes AI 官方 API 文档](https://agnes-ai.com/doc/overview) 的核心内容，便于在 CodeAgent 中配置 preset 与调用工具。官方文档为动态页面，以 [agnes-ai.com/doc](https://agnes-ai.com/doc) 为准。

---

## 1. 平台概览

**Agnes AI**（Sapiens AI 旗下）提供统一 AI Gateway，覆盖：

| 能力 | 说明 |
|------|------|
| 文本生成与推理 | 对话、逻辑推理、内容续写、Agent / 工具调用 |
| 图像生成与编辑 | 文生图、图生图、多图合成 |
| 视频生成 | 文生视频、图生视频、多图引导、关键帧过渡（异步任务） |

**控制台与文档**

| 资源 | URL |
|------|-----|
| API 文档首页 | https://agnes-ai.com/doc/overview |
| API 平台（Key / 计费） | https://platform.agnes-ai.com |
| 应用端 | https://app.agnes-ai.com |

---

## 2. Base URL 与认证

### Base URL

```text
https://apihub.agnes-ai.com/v1
```

各模型在 Base URL 后追加不同路径（见下文「端点总览」）。

### 认证

所有请求使用 **Bearer Token**：

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

API Key 在 [platform.agnes-ai.com](https://platform.agnes-ai.com) 创建。请勿将 Key 提交到公开仓库。

---

## 3. 快速开始

1. 在 [API 平台](https://platform.agnes-ai.com) 注册并创建 API Key。
2. 用任意 OpenAI 兼容客户端或 `curl` 调用，例如对话模型：

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

3. 视频生成为**异步**：先 `POST /v1/videos` 拿 `task_id`，再轮询 `GET /v1/videos/{task_id}` 直至 `status=completed`。

### OpenAI SDK 示例

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://apihub.agnes-ai.com/v1",
)

resp = client.chat.completions.create(
    model="agnes-2.0-flash",
    messages=[{"role": "user", "content": "Explain tool-using agents."}],
)
print(resp.choices[0].message.content)
```

---

## 4. 模型与端点总览

| 官方文档 | model 名称 | 端点 | 调用方式 |
|----------|------------|------|----------|
| [Agnes 1.5 Flash](https://agnes-ai.com/doc/agnes-15-flash) | `agnes-1.5-flash` | `POST /v1/chat/completions` | 同步 |
| [Agnes 2.0 Flash](https://agnes-ai.com/doc/agnes-20-flash) | `agnes-2.0-flash` | `POST /v1/chat/completions` | 同步（支持 stream / tools） |
| [Agnes Image 2.0 Flash](https://agnes-ai.com/doc/agnes-image-20-flash) | `agnes-image-2.0-flash` | `POST /v1/images/generations` | 同步 |
| [Agnes Image 2.1 Flash](https://agnes-ai.com/doc/agnes-image-21-flash) | `agnes-image-2.1-flash` | `POST /v1/images/generations` | 同步 |
| [Agnes Video V2.0](https://agnes-ai.com/doc/agnes-video-v20) | `agnes-video-v2.0` | `POST /v1/videos` + `GET /v1/videos/{task_id}` | **异步** |

文档导航中还列出 **Agnes 1.5 Pro（已弃用）**；新项目请优先使用 2.0 Flash。

---

## 5. 对话模型

### 5.1 Agnes-1.5-Flash

**定位**：低延迟、高吞吐、成本友好；支持**文本 + 图像**多模态输入。

**适用场景**：实时交互、高并发、成本敏感负载、轻量智能接口。

**主要参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定 `agnes-1.5-flash` |
| `messages` | array | 是 | OpenAI 格式消息列表 |
| `temperature` | number | 否 | 采样温度 |
| `max_tokens` | integer | 否 | 最大输出 token |
| `frequency_penalty` | number | 否 | 频率惩罚 |
| `presence_penalty` | number | 否 | 存在惩罚 |
| `repetition_penalty` | number | 否 | 重复惩罚 |
| `stop` | string / array | 否 | 停止序列 |
| `seed` | integer | 否 | 随机种子 |

**纯文本示例**

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-1.5-flash",
    "messages": [{"role": "user", "content": "what'\''s this?"}],
    "temperature": 0.5,
    "max_tokens": 1024
  }'
```

**多模态（文本 + 图像）示例**

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-1.5-flash",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe this image"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
      ]
    }]
  }'
```

**兼容性**：OpenAI Chat Completions API、OpenAI Responses API。

---

### 5.2 Agnes-2.0-Flash

**定位**：面向 Agent、工具调用、编码与推理；PinchBench 排名靠前，强调响应速度与任务完成能力。

**能力**：多轮对话、system 提示、**流式输出**、**工具调用**、JSON 风格输出、OpenAI 兼容请求结构。

**主要参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定 `agnes-2.0-flash` |
| `messages` | array | 是 | OpenAI 格式消息 |
| `temperature` | number | 否 | 低值更确定，高值更创意 |
| `max_tokens` | integer | 否 | 最大输出 token |
| `stream` | boolean | 否 | `true` 启用流式 |
| `tools` | array | 否 | 工具定义（function calling） |
| `tool_choice` | string / object | 否 | 工具选择策略 |

**基本对话**

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {"role": "system", "content": "You are a helpful AI assistant."},
      {"role": "user", "content": "Explain how autonomous agents use tools."}
    ],
    "temperature": 0.7,
    "max_tokens": 1024
  }'
```

**流式**：请求体设 `"stream": true`，按 SSE 读取增量内容。

**工具调用**：在请求中提供 `tools` 数组；可选 `tool_choice` 控制是否强制调用工具。

**参考定价（官方平台，以控制台为准）**：输入约 **$0.03 / 百万 token**，输出约 **$0.15 / 百万 token**。

---

## 6. 图像模型

两类模型共用端点 `POST https://apihub.agnes-ai.com/v1/images/generations`，OpenAI Images 风格请求体，扩展字段放在 `extra_body`。

### 6.1 Agnes-Image-2.0-Flash

**定位**：快速图生图 / 多图合成 / 图像编辑；兼容 OpenAI Images API 结构。

**主要参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | `agnes-image-2.0-flash` |
| `prompt` | string | 是 | 生成或编辑描述 |
| `size` | string | 否 | 如 `1024x768`、`1024x1024`、`768x1024` |
| `seed` | number | 否 | 可复现种子 |
| `tags` | array | 否 | 图生图时设 `["img2img"]` |
| `extra_body.image` | array | 否 | 输入图 URL 列表 |
| `extra_body.response_format` | string | 否 | 如 `url` |

**图生图**

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "tags": ["img2img"],
    "prompt": "Transform this image into a cinematic cyberpunk style while preserving the main subject",
    "size": "1024x768",
    "extra_body": {
      "image": ["https://example.com/input.png"],
      "response_format": "url"
    }
  }'
```

**响应示例**

```json
{
  "created": 1774432125,
  "data": [{"url": "https://..."}],
  "usage": {"generated_images": 1}
}
```

**参考定价**：约 **$0.003 / 张**（文档标注；以平台为准）。

**提示词结构**：`[主体] + [场景] + [风格] + [光照] + [构图] + [质量要求]`。

---

### 6.2 Agnes-Image-2.1-Flash

**定位**：在 2.0 基础上强化**高密度信息**图像（复杂构图、丰富细节）。

**能力**：文生图、图生图、构图保持、自定义尺寸、URL 返回结果。

**主要参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | `agnes-image-2.1-flash` |
| `prompt` | string | 是 | 生成或编辑描述 |
| `size` | string | 否 | 如 `1024x768` |
| `extra_body.image` | array | 否 | 图生图输入 URL |
| `extra_body.response_format` | string | 否 | 如 `url` |

**文生图**

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A luminous floating city above a misty canyon at sunrise, cinematic realism",
    "size": "1024x768"
  }'
```

**图生图**：在 `extra_body.image` 中传入参考图 URL，并在 prompt 中说明「保留什么 / 改变什么」。

**参考定价**：约 **$0.003 / 张**。

---

## 7. 视频模型：Agnes-Video-V2.0

**model**：`agnes-video-v2.0`

**能力**：文生视频、图生视频、多图引导、关键帧插值、运镜与场景控制、电影级输出。

### 7.1 异步工作流

```text
1. POST /v1/videos          → 返回 task id（status: queued）
2. GET  /v1/videos/{task_id} → 轮询 progress / status
3. status=completed 时读取 video_url 并下载
```

### 7.2 创建任务参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | `agnes-video-v2.0` |
| `prompt` | string | 是 | 视频描述 |
| `image` | string / array | 否 | 单图 URL（图生视频） |
| `mode` | string | 否 | 如 `ti2vid`、`keyframes` |
| `height` | integer | 否 | 默认 `768` |
| `width` | integer | 否 | 默认 `1152` |
| `num_frames` | integer | 否 | ≤441，且满足 **8n+1**（如 81、121、161、241、441） |
| `num_inference_steps` | integer | 否 | 推理步数 |
| `seed` | integer | 否 | 随机种子 |
| `frame_rate` | number | 否 | 1–60 FPS，推荐 24 |
| `negative_prompt` | string | 否 | 负向提示 |
| `extra_body.image` | array | 否 | 多图 / 关键帧 URL |
| `extra_body.mode` | string | 否 | 关键帧模式设 `keyframes` |

### 7.3 调用示例

**文生视频**

```bash
curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, warm golden lighting",
    "height": 768,
    "width": 1152,
    "num_frames": 121,
    "frame_rate": 24
  }'
```

**图生视频**：增加 `"image": "https://example.com/image.png"`。

**多图 / 关键帧**：使用 `extra_body.image` 数组；关键帧过渡设 `extra_body.mode: "keyframes"`。

**查询结果**

```bash
curl -X GET https://apihub.agnes-ai.com/v1/videos/{task_id} \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 7.4 任务状态

| status | 含义 |
|--------|------|
| `queued` | 排队中 |
| `in_progress` | 生成中 |
| `completed` | 完成（此时有 `video_url`） |
| `failed` | 失败 |

**完成响应字段**：`video_url`、`size`（如 `1152x768`）、`seconds`、`usage.duration_seconds`。

### 7.5 推荐参数

| 场景 | 建议 |
|------|------|
| 标准视频 | 1152×768，121 帧，24 FPS（约 5 秒） |
| 短视频 | 81 或 121 帧，24 FPS |
| 更顺滑 | 提高 `frame_rate`（24 或 30） |
| 可复现 | 固定 `seed` |
| 关键帧过渡 | `extra_body.mode: "keyframes"` |

**提示词结构（文生视频）**：`[主体] + [动作] + [场景] + [运镜] + [光照] + [风格]`。

**参考定价**：约 **$0.005 / 秒**（文档标注；部分页面写「即将公布」，以平台为准）。

---

## 8. 通用错误码

| HTTP | 说明 |
|------|------|
| 400 | 请求参数无效 |
| 401 | 未授权，检查 API Key |
| 404 | 资源不存在（如 task_id 无效） |
| 500 | 服务端错误 |
| 503 | 服务繁忙，稍后重试 |

视频任务失败时 `status=failed`，需根据响应排查 prompt / 图片 URL / 参数约束。

---

## 9. CodeAgent 集成

当前 CodeAgent **内置支持** Agnes **视频生成**（`video_generate` 工具 + `provider: agnes` preset）。

### 9.1 视频 preset 示例

```json
{
  "id": "agnes-video",
  "provider": "agnes",
  "base_url": "https://apihub.agnes-ai.com/v1",
  "model": "agnes-video-v2.0",
  "api_key": "YOUR_API_KEY",
  "use_type": "video_gen",
  "supports_video_gen": true
}
```

Web UI：**配置 → 多模型预设 → 视频生成 → Agnes AI**；聊天页 **模型栈 → 视频生成** 选用 preset。

### 9.2 相关环境变量

见 [`ENV_REFERENCE.md`](ENV_REFERENCE.md) 中 **视频生成（video_generate）** 一节：

| 变量 | 说明 |
|------|------|
| `CODEAGENT_VIDEO_GEN_PRESET_ID` | 默认视频 preset |
| `CODEAGENT_VIDEO_GEN_TIMEOUT_SEC` | 创建 + 轮询总超时（默认 600s） |
| `CODEAGENT_VIDEO_GEN_POLL_INTERVAL_SEC` | 轮询间隔（默认 5s） |
| `CODEAGENT_PUBLIC_BASE_URL` | 图生视频时 attachment 公网 URL 前缀 |

### 9.3 对话 / 图像模型

Agnes 对话与图像 API 为 OpenAI 兼容格式，可在 CodeAgent 中通过 **OpenAI 兼容 preset** 手动配置（`base_url` + `model` + `api_key`），例如：

- 对话：`use_type: chat`，`model: agnes-2.0-flash`
- 识图：`use_type: vision`，`model: agnes-1.5-flash`（多模态 messages）
- 生图：`use_type: image`，`model: agnes-image-2.1-flash`（需自行对接 `extra_body` 扩展；内置 `image_generate` 协议见 [`IMAGE_GEN_PROVIDERS.md`](IMAGE_GEN_PROVIDERS.md)）

### 9.4 Agent 工具

| 工具 | Agnes 模型 | 说明 |
|------|------------|------|
| `video_generate` | `agnes-video-v2.0` | 已集成；自动创建任务、轮询、保存 MP4 attachment |
| `image_generate` | 图像模型 | 尚未内置 `agnes_image` 协议，可用 OpenAI 兼容网关或后续扩展 |
| 主对话 / `vision_analyze` | 1.5 / 2.0 Flash | 按 OpenAI Chat Completions 配置 preset |

---

## 10. 其他文档页

| 页面 | URL | 说明 |
|------|-----|------|
| 概览 | https://agnes-ai.com/doc/overview | 平台能力、Base URL、认证 |
| 快速开始 | https://agnes-ai.com/doc/quickstart | 首次调用指引 |
| FAQs | https://agnes-ai.com/doc/faqs | 常见问题 |
| 接入编程工具 | https://agnes-ai.com/doc/connect-coding-tools | IDE / Agent 工具集成 |
| 条款与政策 | https://agnes-ai.com/doc/terms-policy | 使用条款 |

---

## 11. 官方链接索引

- 文档首页：https://agnes-ai.com/doc/overview  
- Agnes 1.5 Flash：https://agnes-ai.com/doc/agnes-15-flash  
- Agnes 2.0 Flash：https://agnes-ai.com/doc/agnes-20-flash  
- Agnes Image 2.0 Flash：https://agnes-ai.com/doc/agnes-image-20-flash  
- Agnes Image 2.1 Flash：https://agnes-ai.com/doc/agnes-image-21-flash  
- Agnes Video V2.0：https://agnes-ai.com/doc/agnes-video-v20  

定价与配额以 [platform.agnes-ai.com](https://platform.agnes-ai.com) 控制台为准。
