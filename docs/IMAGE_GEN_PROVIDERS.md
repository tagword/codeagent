# 图片生成 Provider 规则

`image_generate` 工具通过 preset 的 `provider` 字段选择协议。配置写在 `config/seed.models.json`，需 `"supports_image_gen": true`。

## 统一工具参数 → 各平台映射

| 工具参数 | 含义 | OpenAI | MiniMax | 火山方舟 Seedream |
|----------|------|--------|---------|-------------------|
| `prompt` | 画面描述 | `prompt` | `prompt` | `prompt` |
| `size` | 尺寸 | `1024x1024` 等 | `aspect_ratio`（`16:9` 或 WxH 映射） | `2K`/`3K`/`4K` 或 `2048x2048` |
| `n` | 张数 | `n`（≤4） | `n`（≤9） | `sequential_image_generation=auto` + `max_images`（≤15） |
| `quality` | 质量 | `standard`/`hd` | 忽略 | `hd` → `optimize_prompt_options.mode=standard` |
| `negative_prompt` | 避免内容 | 拼进 prompt | 拼进 prompt | 拼进 prompt |
| `reference_image_urls` | 参考图 URL | 暂不支持 | `subject_reference[].image_file` | `image`（单张或数组，≤10） |
| `attachment_ids` | 会话附件 | 暂不支持 | 同上（转 data URL） | 同上（转 data URL） |

## 端点

| provider | 生图协议 | HTTP |
|----------|----------|------|
| `openai` / `openai_compatible` | `openai_images` | `POST {base_url}/images/generations` |
| `minimax` | `minimax_image` | `POST {host}/v1/image_generation` |
| `volcengine` | `volcengine_images` | `POST {base_url}/images/generations`（默认 `https://ark.cn-beijing.volces.com/api/v3`） |

文生图 / 图生图：**MiniMax、火山方舟均为同一 URL**，图生图通过是否传参考图字段区分。

## 预设示例

### 火山方舟 Seedream 5.0 lite

```json
{
  "id": "ark-seedream",
  "name": "volcengine/doubao-seedream-5-0-lite-260128",
  "provider": "volcengine",
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "model": "doubao-seedream-5-0-lite-260128",
  "api_key": "ARK_API_KEY",
  "use_type": "image",
  "supports_image_gen": true
}
```

`model` 必须使用[模型列表](https://www.volcengine.com/docs/82379/1330310?lang=zh)中的 **Model ID**（带日期后缀），例如：

| 展示名 | Model ID |
|--------|----------|
| Seedream 5.0 lite | `doubao-seedream-5-0-lite-260128` |
| Seedream 5.0 | `doubao-seedream-5-0-260128` |
| Seedream 4.5 | `doubao-seedream-4-5-251128` |
| Seedream 4.0 | `doubao-seedream-4-0-250828` |

勿使用 `doubao-seedream-5-0-lite` 等无后缀简称（会 404）。若使用自定义推理接入点，可填 `ep-xxxxxxxx`。

### MiniMax

```json
{
  "id": "minimax-image",
  "provider": "minimax",
  "base_url": "https://api.minimaxi.com/v1",
  "model": "image-01",
  "supports_image_gen": true
}
```

## 环境变量

见 `ENV_REFERENCE.md` 中 `CODEAGENT_IMAGE_GEN_*`。
