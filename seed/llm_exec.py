from __future__ import annotations

import os
from typing import Optional


class LLMAPIExecutor:
    """
    Executes LLM calls via OpenAI-compatible API.
    """
    
    def __init__(
        self,
        baseURL: str,
        model: str,
        maxOutputTokens: int = 8192,
        temperature: float = 0.7,
        topP: float = 0.95,
        topK: int = 40,
        api_key: Optional[str] = None,
        auth_scheme: Optional[str] = None,
    ):
        """
        Initialize LLM API executor.
        
        Args:
            baseURL: API base URL (OpenAI-compatible, e.g., https://api.openai.com/v1)
            model: Model name to use
            maxOutputTokens: Maximum output tokens
            temperature: Temperature for sampling
            topP: Top-p sampling parameter
            topK: Top-k sampling parameter
        """
        self.baseURL = baseURL
        self.model = model
        self.temperature = temperature
        self.topP = topP
        self.topK = topK
        self.api_key = (
            api_key
            if api_key is not None
            else os.environ.get("CODEAGENT_LLM_API_KEY", "").strip()
        )
        self.auth_scheme = (
            auth_scheme
            if auth_scheme is not None
            else os.environ.get("CODEAGENT_LLM_AUTH_SCHEME", "Bearer").strip() or "Bearer"
        )
        self.maxOutputTokens = int(
            os.environ.get("CODEAGENT_LLM_MAX_TOKENS", str(maxOutputTokens))
        )
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"{self.auth_scheme} {self.api_key}"

    def _ensure_base_url(self) -> None:

        if not (self.baseURL or "").strip():
            raise LLMError(
                "未配置 LLM API 地址：请在 config/codeagent.env 中设置 CODEAGENT_LLM_BASEURL，"
                "或在 config/codeagent.models.json 中至少保存一条含 Base URL 与模型的预设"
                "（未点「设为默认」时将自动使用列表中的第一条）。"
            )

    def _get_completion_url(self) -> str:
        """Get the completion endpoint URL"""
        return f"{self.baseURL}/chat/completions"
    



import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests


logger = logging.getLogger(__name__)


def generate(
    self,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    max_turns: int = 1,
    temperature: Optional[float] = None,
    temperature_reset: bool = False,
    max_tokens: Optional[int] = None,
    enable_thinking: Optional[bool] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate response from LLM.
    
    Args:
        messages: List of messages in OpenAI format
        tools: Optional list of tool definitions
        max_turns: Number of completion turns
        temperature: Override temperature for this call
        temperature_reset: Whether to reset temperature after first turn
        max_tokens: If set, cap completion tokens for this call only
    
    Returns:
        Tuple of (content, metadata including tool_calls)
    """
    self._ensure_base_url()
    eff_max = self.maxOutputTokens if max_tokens is None else int(max_tokens)
    api_messages = _openai_chat_messages(messages, base_url=self.baseURL)
    params: Dict[str, Any] = {
        "model": self.model,
        "messages": copy.deepcopy(api_messages),
        "max_tokens": eff_max,
        "temperature": temperature or self.temperature,
        "top_p": self.topP,
    }
    if not os.environ.get("CODEAGENT_LLM_NO_TOPK"):
        params["top_k"] = self.topK

    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"

    # --- Reasoning separation (sglang / DeepSeek-style contract) -----
    extra_body: Dict[str, Any] = {}
    # Resolve enable_thinking from caller arg or env.
    if enable_thinking is None:
        env_val = os.environ.get("CODEAGENT_LLM_ENABLE_THINKING", "1")
        resolved_thinking = env_val.lower() not in ("0", "false", "no", "")
    else:
        resolved_thinking = bool(enable_thinking)

    if _is_deepseek_url(self.baseURL):
        # DeepSeek official API: use native thinking.type, NOT sglang-specific params.
        extra_body["thinking"] = {"type": "enabled" if resolved_thinking else "disabled"}
        if resolved_thinking:
            effort = os.environ.get("CODEAGENT_LLM_REASONING_EFFORT", "").strip().lower()
            if effort in ("low", "medium", "high", "max"):
                params["reasoning_effort"] = effort
    else:
        # SGLang / Qwen3: separate_reasoning + chat_template_kwargs.enable_thinking
        if os.environ.get("CODEAGENT_LLM_SEPARATE_REASONING", "1") != "0":
            extra_body["separate_reasoning"] = True
        if os.environ.get("CODEAGENT_LLM_CHAT_TEMPLATE_KWARGS", "1") != "0":
            extra_body.setdefault("chat_template_kwargs", {})
            extra_body["chat_template_kwargs"]["enable_thinking"] = resolved_thinking
    # User-supplied JSON via CODEAGENT_LLM_EXTRA_BODY merges last (wins).
    user_extra = os.environ.get("CODEAGENT_LLM_EXTRA_BODY", "").strip()
    if user_extra:
        try:
            parsed = json.loads(user_extra)
            if isinstance(parsed, dict):
                # Deep-merge chat_template_kwargs so user can add/override keys.
                ctk = parsed.pop("chat_template_kwargs", None)
                extra_body.update(parsed)
                if isinstance(ctk, dict):
                    extra_body.setdefault("chat_template_kwargs", {}).update(ctk)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("CODEAGENT_LLM_EXTRA_BODY invalid JSON, ignored: %s", e)
    # Merge into top-level params (sglang accepts them at the request root).
    for k, v in extra_body.items():
        params.setdefault(k, v)

    max_body = max_llm_request_body_bytes(self.baseURL)
    if max_body > 0:
        maybe_shrink_llm_request_params(params, max_bytes=max_body, base_url=self.baseURL)

    # Clamp completion max_tokens using an estimated input budget. Prefer setting
    # CODEAGENT_LLM_CONTEXT_SIZE to the inference server's *effective* KV token pool
    # (e.g. SGLang ``max_total_num_tokens`` minus headroom), not always the model's
    # configured ``context_len`` when VRAM limits the cache.
    ctx = int(os.environ.get("CODEAGENT_LLM_CONTEXT_SIZE", "262144"))
    if ctx > 0:
        body = json.dumps(
            {"messages": params["messages"], "tools": tools or []},
            ensure_ascii=False,
        )
        div = int(os.environ.get("CODEAGENT_LLM_INPUT_TOKEN_EST_DIVISOR", "3"))
        est_in = max(1, len(body.encode("utf-8")) // max(div, 1))
        margin = int(os.environ.get("CODEAGENT_LLM_CONTEXT_MARGIN", "8192"))
        cap = ctx - est_in - margin
        req = int(params.get("max_tokens") or 0)
        if req > 0:
            allowance = max(1, cap) if cap > 0 else 1
            safe = max(1, min(req, allowance))
            if safe < req:
                logger.warning(
                    "Lowering max_tokens %s -> %s (est_input≈%s, ctx=%s, margin=%s)",
                    req,
                    safe,
                    est_in,
                    ctx,
                    margin,
                )
                params["max_tokens"] = safe
    
    try:
        response = requests.post(
            self._get_completion_url(),
            headers=self.headers,
            json=params,
            timeout=120
        )
        if not response.ok:
            snippet = (response.text or "")[:2000]
            raise LLMError(
                f"LLM HTTP {response.status_code} for {self._get_completion_url()}: {snippet}"
            )
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"LLM returned no choices: {json.dumps(data)[:1200]}")

        msg = choices[0].get("message")
        if not isinstance(msg, dict):
            raise LLMError(f"LLM message missing or invalid: {choices[0]!r}")

        content = _msg_text_to_str(msg.get("content"))
        # sglang separate_reasoning populates `reasoning_content` (DeepSeek
        # API contract); some older/alt backends use `reasoning` or
        # `thinking`. Read all three and keep them OUT of `content`.
        reasoning_content = _msg_text_to_str(msg.get("reasoning_content") or "")
        reasoning_alt = _msg_text_to_str(msg.get("reasoning") or "")
        thinking = _msg_text_to_str(msg.get("thinking") or "")
        reasoning_parts = [s for s in (reasoning_content, reasoning_alt, thinking) if s.strip()]
        reasoning = "\n\n".join(reasoning_parts)
        # IMPORTANT: do NOT fall back to copying `reasoning` into `content`.
        # That fallback historically caused raw CoT to leak into visible
        # chat output and pollute session history. If the server emits
        # reasoning-only (empty content), that's a server/model config
        # issue; we prefer an empty assistant turn + upstream rescue over
        # silent CoT leakage.
        reasoning_for_meta = reasoning
        if not content.strip() and reasoning.strip():
            # Keep content empty; surface the anomaly in logs so operators
            # notice missing `enable_thinking` / parser config.
            logger.warning(
                "LLM returned reasoning (%d chars) but empty content; "
                "check --reasoning-parser and chat_template enable_thinking.",
                len(reasoning),
            )

        tool_calls = _extract_tool_calls(msg)
        if tool_calls and not (content or "").strip():
            ph = assistant_toolcall_content_placeholder()
            if ph is not None:
                content = ph

        if temperature_reset:
            self.temperature = self.temperature

        # `reasoning_content` metadata: prefer API `reasoning_content`, else any
        # CoT-bearing field so persist/echo never drops DeepSeek's chain.
        reasoning_echo = (reasoning_content.strip() or reasoning.strip())
        metadata = {
            "model": self.model,
            "usage": data.get("usage", {}),
            "tool_calls": tool_calls,
            "reasoning": reasoning_for_meta,
            "reasoning_content": reasoning_echo,
        }

        return content, metadata

    except LLMError:
        raise
    except requests.exceptions.RequestException as e:
        raise LLMError(f"Failed to call LLM API: {e}", original_error=e)
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected API response format: {e}", original_error=e)




import copy
import json
import logging
import os
from typing import Any, Dict, Generator, List, Optional

import requests


logger = logging.getLogger(__name__)


def generate_stream(
    self,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    enable_thinking: Optional[bool] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Stream response from LLM, yielding SSE chunks as they arrive.

    Each yielded dict has ``type``:
      - ``"delta"``: ``{"type": "delta", "text": "..."}``
      - ``"reasoning_delta"``: ``{"type": "reasoning_delta", "text": "..."}``
      - ``"tool_calls"``: ``{"type": "tool_calls", "tool_calls": [...]}``
      - ``"done"``: ``{"type": "done", "content": "...", "metadata": {...}}``
    """
    self._ensure_base_url()
    eff_max = self.maxOutputTokens if max_tokens is None else int(max_tokens)
    api_messages = _openai_chat_messages(messages, base_url=self.baseURL)
    params: Dict[str, Any] = {
        "model": self.model,
        "messages": copy.deepcopy(api_messages),
        "max_tokens": eff_max,
        "temperature": temperature or self.temperature,
        "top_p": self.topP,
        "stream": True,
    }
    if not os.environ.get("CODEAGENT_LLM_NO_TOPK"):
        params["top_k"] = self.topK

    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"

    # Reasoning / thinking params (same logic as generate())
    extra_body: Dict[str, Any] = {}
    if enable_thinking is None:
        env_val = os.environ.get("CODEAGENT_LLM_ENABLE_THINKING", "1")
        resolved_thinking = env_val.lower() not in ("0", "false", "no", "")
    else:
        resolved_thinking = bool(enable_thinking)

    if _is_deepseek_url(self.baseURL):
        extra_body["thinking"] = {"type": "enabled" if resolved_thinking else "disabled"}
        if resolved_thinking:
            effort = os.environ.get("CODEAGENT_LLM_REASONING_EFFORT", "").strip().lower()
            if effort in ("low", "medium", "high", "max"):
                params["reasoning_effort"] = effort
    else:
        if os.environ.get("CODEAGENT_LLM_SEPARATE_REASONING", "1") != "0":
            extra_body["separate_reasoning"] = True
        if os.environ.get("CODEAGENT_LLM_CHAT_TEMPLATE_KWARGS", "1") != "0":
            extra_body.setdefault("chat_template_kwargs", {})
            extra_body["chat_template_kwargs"]["enable_thinking"] = resolved_thinking
    user_extra = os.environ.get("CODEAGENT_LLM_EXTRA_BODY", "").strip()
    if user_extra:
        try:
            parsed = json.loads(user_extra)
            if isinstance(parsed, dict):
                ctk = parsed.pop("chat_template_kwargs", None)
                extra_body.update(parsed)
                if isinstance(ctk, dict):
                    extra_body.setdefault("chat_template_kwargs", {}).update(ctk)
        except (json.JSONDecodeError, TypeError):
            pass
    for k, v in extra_body.items():
        params.setdefault(k, v)

    max_body = max_llm_request_body_bytes(self.baseURL)
    if max_body > 0:
        maybe_shrink_llm_request_params(params, max_bytes=max_body, base_url=self.baseURL)

    try:
        resp = requests.post(
            self._get_completion_url(),
            headers=self.headers,
            json=params,
            stream=True,
            timeout=120,
        )
        if not resp.ok:
            snippet = (resp.text or "")[:2000]
            raise LLMError(
                f"LLM HTTP {resp.status_code} for {self._get_completion_url()}: {snippet}"
            )

        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls_accum: List[Dict[str, Any]] = []
        finish_reason: Optional[str] = None
        usage: Dict[str, Any] = {}

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[len("data: "):].strip()
            if payload in ("[DONE]", ""):
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            # finish_reason at the choice level
            fr = choices[0].get("finish_reason")
            if fr:
                finish_reason = fr
            # usage may appear in final chunk (sglang-style) or separate key
            raw_usage = chunk.get("usage")
            if raw_usage:
                usage = raw_usage

            # Content delta
            text = _msg_text_to_str(delta.get("content"))
            if text:
                content_parts.append(text)
                yield {"type": "delta", "text": text}

            # Reasoning content (sglang separate_reasoning / DeepSeek)
            rc = _msg_text_to_str(delta.get("reasoning_content"))
            if rc:
                reasoning_parts.append(rc)
                yield {"type": "reasoning_delta", "text": rc}

            # Tool calls (typically only in the final choice chunk)
            tc_raw = delta.get("tool_calls")
            if tc_raw:
                for i, tc in enumerate(tc_raw):
                    idx = tc.get("index", i)
                    while len(tool_calls_accum) <= idx:
                        tool_calls_accum.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    slot = tool_calls_accum[idx]
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    if tc.get("type"):
                        slot["type"] = tc["type"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]

        full_content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        built_tool_calls = _extract_tool_calls({"tool_calls": tool_calls_accum}) if tool_calls_accum else []

        if built_tool_calls and not full_content.strip():
            ph = assistant_toolcall_content_placeholder()
            if ph is not None:
                full_content = ph

        reasoning_echo = reasoning.strip()
        metadata = {
            "model": self.model,
            "usage": usage,
            "tool_calls": built_tool_calls,
            "reasoning": reasoning,
            "reasoning_content": reasoning_echo,
        }

        yield {
            "type": "done",
            "content": full_content,
            "reasoning": reasoning,
            "tool_calls": built_tool_calls,
            "metadata": metadata,
        }

    except LLMError:
        raise
    except requests.exceptions.RequestException as e:
        raise LLMError(f"Failed to call LLM API (stream): {e}", original_error=e)
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected API stream response: {e}", original_error=e)

def count_tokens(self, text: str) -> int:
    """
    Estimate token count (simple approximation).
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Approximate token count
    """
    return len(text.encode('utf-8')) // 4



"""LLM API executor for CodeAgent - Connect to external LLM API"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _is_deepseek_url(base_url: Optional[str] = None) -> bool:
    """
    Detect DeepSeek official API.

    Prefer ``base_url`` from :class:`LLMAPIExecutor` (Web UI presets may point at
    DeepSeek while ``CODEAGENT_LLM_BASEURL`` still holds a default / other host).
    Without a URL, fall back to ``CODEAGENT_LLM_BASEURL``.
    """
    raw = (base_url or "").strip() or (os.environ.get("CODEAGENT_LLM_BASEURL", "") or "")
    return "api.deepseek.com" in raw.lower()


def _openai_chat_messages(
    messages: List[Dict[str, Any]],
    *,
    base_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Strip non-API keys (e.g. ``ts``) before POSTing to OpenAI-compatible endpoints.
    """
    def _should_send_reasoning_content() -> bool:
        """
        DeepSeek thinking-mode contract: assistant `reasoning_content` must be
        echoed on every subsequent request (often including non-tool replies),
        otherwise the API returns HTTP 400. Tool-call chains remain the strictest
        case; plain multi-turn chat in thinking mode also requires the field.

        Some strict OpenAI-compatible gateways reject unknown keys, so this is
        gated behind an env flag, with a safe auto-enable for DeepSeek's
        official endpoint.
        """
        env = os.environ.get("CODEAGENT_LLM_SEND_REASONING_CONTENT", "").strip().lower()
        if env in ("1", "true", "yes", "on"):
            return True
        if env in ("0", "false", "no", "off"):
            return False
        return _is_deepseek_url(base_url)

    include_rc = _should_send_reasoning_content()
    out: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "tool":
            row: Dict[str, Any] = {"role": "tool"}
            if "content" in m:
                row["content"] = m["content"]
            if m.get("tool_call_id") is not None:
                row["tool_call_id"] = m["tool_call_id"]
            if m.get("name"):
                row["name"] = m["name"]
            out.append(row)
            continue
        if role not in ("system", "user", "assistant"):
            continue
        row = {"role": role}
        if "content" in m:
            row["content"] = m["content"]
        if m.get("name"):
            row["name"] = m["name"]
        if m.get("tool_calls"):
            row["tool_calls"] = m["tool_calls"]
            if "content" not in row:
                row["content"] = None
        # DeepSeek: echo reasoning_content for every assistant turn when enabled
        # (not only tool chains); missing key → invalid_request_error.
        # Other backends: only send when we have tool_calls or a stored key, so
        # strict OpenAI-compatible proxies are not spammed with unknown fields.
        if include_rc and role == "assistant":
            if _is_deepseek_url(base_url):
                rc = m.get("reasoning_content")
                row["reasoning_content"] = "" if rc is None else _msg_text_to_str(rc)
            elif m.get("tool_calls") or ("reasoning_content" in m):
                row["reasoning_content"] = (
                    m["reasoning_content"] if m.get("reasoning_content") is not None else ""
                )
        out.append(row)

    # After the last `user` in this request, if the tail contains any `tool`
    # message, DeepSeek requires every `assistant` in that tail to carry
    # `reasoning_content` (possibly ""). Legacy rows may omit the key — patch.
    if include_rc and out:
        last_user_i = -1
        for i, x in enumerate(out):
            if isinstance(x, dict) and x.get("role") == "user":
                last_user_i = i
        if last_user_i >= 0:
            tail = out[last_user_i + 1 :]
            if any(isinstance(x, dict) and x.get("role") == "tool" for x in tail):
                for row in tail:
                    if not isinstance(row, dict) or row.get("role") != "assistant":
                        continue
                    val = row.get("reasoning_content")
                    if val is None:
                        row["reasoning_content"] = ""
                    elif not isinstance(val, str):
                        row["reasoning_content"] = _msg_text_to_str(val)
    return out


def assistant_toolcall_content_placeholder() -> Optional[str]:
    """
    当模型在返回 ``tool_calls`` 时把 ``content`` 置空，部分 OpenAI 兼容栈或下游
    会把「空正文 + 工具」误判为异常并中断工具链。用非空占位符可稳定多轮。

    环境变量：
    - ``CODEAGENT_ASSISTANT_TOOLCALL_PLACEHOLDER_DISABLE=1``：不替换（保持空 / null 行为）
    - ``CODEAGENT_ASSISTANT_TOOLCALL_PLACEHOLDER=...``：显式指定占位正文（可为空字符串）
    - 未设置 PLACEHOLDER 时：默认一个 ASCII 空格（对模型干扰最小）
    """
    if os.environ.get("CODEAGENT_ASSISTANT_TOOLCALL_PLACEHOLDER_DISABLE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    key = "CODEAGENT_ASSISTANT_TOOLCALL_PLACEHOLDER"
    if key in os.environ:
        return os.environ[key]
    return " "


def _msg_text_to_str(raw: Any) -> str:
    """Normalize `message.content` (string, null, or multimodal list) to str."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: List[str] = []
        for item in raw:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(raw)


def _extract_tool_calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse tool_calls; tolerate missing ids or oddly-shaped function payloads."""
    raw = msg.get("tool_calls")
    if not raw:
        return []
    out: List[Dict[str, Any]] = []
    for i, tc in enumerate(raw):
        if not isinstance(tc, dict):
            continue
        tid = tc.get("id") or f"call_{i}"
        fn = tc.get("function")
        if isinstance(fn, str):
            try:
                fn = json.loads(fn)
            except (json.JSONDecodeError, TypeError):
                fn = {"name": "", "arguments": "{}"}
        if not isinstance(fn, dict):
            fn = {"name": "", "arguments": "{}"}
        out.append(
            {
                "id": tid,
                "type": tc.get("type") or "function",
                "function": {
                    "name": fn.get("name") or "",
                    "arguments": fn.get("arguments")
                    if isinstance(fn.get("arguments"), str)
                    else json.dumps(fn.get("arguments") or {}),
                },
            }
        )
    return out


class LLMError(Exception):
    """Exception raised for LLM API errors"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)





import os
from typing import Optional, Tuple


_default_executor: Optional[LLMAPIExecutor] = None
_executor_env_key: Optional[Tuple[str, str, str, str, str]] = None


def get_llm_executor(
    baseURL: Optional[str] = None,
    model: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    auth_scheme: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> LLMAPIExecutor:
    """
    Get or create default LLM executor.

    Args:
        baseURL: Override baseURL from environment (``None`` = read env)
        model: Override model name from environment
        api_key: Override API key from environment (non-empty only)
        auth_scheme: Override auth scheme from environment (non-empty only)
        max_tokens: Override ``CODEAGENT_LLM_MAX_TOKENS`` when set

    Returns:
        LLMAPIExecutor instance
    """
    global _default_executor, _executor_env_key

    resolved_url = (
        (baseURL if baseURL is not None else os.environ.get("CODEAGENT_LLM_BASEURL") or "")
        .strip()
        .rstrip("/")
    )
    if model is not None and str(model).strip():
        resolved_model = str(model).strip()
    else:
        resolved_model = os.environ.get(
            "CODEAGENT_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4"
        )

    max_tok = (
        str(int(max_tokens))
        if max_tokens is not None
        else os.environ.get("CODEAGENT_LLM_MAX_TOKENS", "8192")
    )

    resolved_api = os.environ.get("CODEAGENT_LLM_API_KEY", "").strip()
    if api_key is not None and api_key.strip():
        resolved_api = api_key.strip()

    resolved_scheme = os.environ.get("CODEAGENT_LLM_AUTH_SCHEME", "Bearer").strip() or "Bearer"
    if auth_scheme is not None and auth_scheme.strip():
        resolved_scheme = auth_scheme.strip()

    key = (resolved_url, resolved_model, max_tok, resolved_api, resolved_scheme)

    if _default_executor is None or _executor_env_key != key:
        _default_executor = LLMAPIExecutor(
            baseURL=resolved_url,
            model=resolved_model,
            api_key=resolved_api,
            auth_scheme=resolved_scheme,
            maxOutputTokens=int(max_tok),
        )
        _executor_env_key = key

    return _default_executor


def reset_llm_executor() -> None:
    """Reset the default executor"""
    global _default_executor, _executor_env_key
    _default_executor = None
    _executor_env_key = None


"""Shrink chat-completions JSON before HTTP POST to avoid gateway 413 (body too large)."""


import json
import logging
import os
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def request_json_size(params: Dict[str, Any]) -> int:
    return len(json.dumps(params, ensure_ascii=False).encode("utf-8"))


def max_llm_request_body_bytes(base_url: Optional[str]) -> int:
    """0 = disabled. Official DeepSeek API often sits behind a ~1MiB reverse-proxy limit."""
    raw = os.environ.get("CODEAGENT_LLM_MAX_REQUEST_BODY_BYTES", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning("Invalid CODEAGENT_LLM_MAX_REQUEST_BODY_BYTES=%r", raw)
    if _is_deepseek_url(base_url or ""):
        return 786432  # 768 KiB — leave headroom below common 1MiB nginx limits
    return 0


def maybe_shrink_llm_request_params(
    params: Dict[str, Any],
    *,
    max_bytes: int,
    base_url: Optional[str],
) -> None:
    """Mutates ``params`` (especially ``messages``) in place."""
    if max_bytes <= 0:
        return
    try:
        before = request_json_size(params)
    except (TypeError, ValueError):
        return
    if before <= max_bytes:
        return

    msgs = params.get("messages")
    if not isinstance(msgs, list):
        return

    last_ai = -1
    for i in range(len(msgs) - 1, -1, -1):
        if isinstance(msgs[i], dict) and msgs[i].get("role") == "assistant":
            last_ai = i
            break

    base_cap = int(os.environ.get("CODEAGENT_TOOL_OUTPUT_MAX_CHARS", "48000"))
    base_cap = max(500, min(base_cap, 200_000))
    tool_caps: List[int] = []
    x = base_cap
    while x >= 500:
        tool_caps.append(x)
        x //= 2
    if not tool_caps or tool_caps[-1] != 500:
        tool_caps.append(500)

    def sz() -> int:
        return request_json_size(params)

    def trunc_tools(cap: int) -> None:
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "tool":
                content = m.get("content")
                if isinstance(content, str) and len(content) > cap:
                    drop = len(content) - cap
                    m["content"] = (
                        content[:cap]
                        + f"\n...[truncated {drop} chars for HTTP request body limit]"
                    )

    def trunc_rc(cap: int) -> None:
        if not _is_deepseek_url(base_url or ""):
            return
        for i, m in enumerate(msgs):
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            if i == last_ai:
                continue
            rc = m.get("reasoning_content")
            if not isinstance(rc, str) or not rc:
                continue
            if cap <= 0:
                m["reasoning_content"] = ""
            elif len(rc) > cap:
                drop = len(rc) - cap
                m["reasoning_content"] = (
                    rc[:cap] + f"\n...[truncated reasoning {drop} chars for HTTP body limit]"
                )

    def trunc_asst_content(cap: int) -> None:
        for i, m in enumerate(msgs):
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            if i == last_ai:
                continue
            ctn = m.get("content")
            if isinstance(ctn, str) and len(ctn) > cap:
                drop = len(ctn) - cap
                m["content"] = ctn[:cap] + f"\n...[truncated {drop} chars for HTTP body limit]"

    def trunc_system(cap: int) -> None:
        if not msgs or not isinstance(msgs[0], dict) or msgs[0].get("role") != "system":
            return
        ctn = msgs[0].get("content")
        if isinstance(ctn, str) and len(ctn) > cap:
            drop = len(ctn) - cap
            msgs[0]["content"] = ctn[:cap] + f"\n...[truncated system prompt {drop} chars]"

    for cap in tool_caps:
        trunc_tools(cap)
        if sz() <= max_bytes:
            break
    else:
        for cap in (16000, 8000, 4000, 2000, 800, 0):
            trunc_rc(cap)
            if sz() <= max_bytes:
                break
        else:
            for cap in (50000, 20000, 8000, 2000):
                trunc_asst_content(cap)
                if sz() <= max_bytes:
                    break
            else:
                for cap in (40000, 20000, 10000, 5000):
                    trunc_system(cap)
                    if sz() <= max_bytes:
                        break

    after = sz()
    if after <= max_bytes:
        logger.warning(
            "Shrunk LLM JSON request body %s -> %s bytes (limit %s) to reduce HTTP 413 risk",
            before,
            after,
            max_bytes,
        )
    else:
        logger.warning(
            "LLM JSON request body still ~%s bytes (limit %s). "
            "Enable CODEAGENT_CONTEXT_COMPACT=1, lower CODEAGENT_CHAT_USER_ROUNDS / "
            "CODEAGENT_TOOL_OUTPUT_MAX_CHARS, or set CODEAGENT_LLM_MAX_REQUEST_BODY_BYTES=0 "
            "only if your gateway allows larger uploads.",
            after,
            max_bytes,
        )
