# Context Compact Summary Prompt v1

Source: `seed/seed/core/agent_runtime.py`, `maybe_compact_context_messages()`.

This records the current summarizer system prompt before rewriting it as v2.

## System Prompt

```text
You compress prior agent chat for continuation. Output concise bullet points in the same language as the transcript. Preserve: file paths, shell commands, error messages, user goals, tool names used, and unresolved questions. Do not invent facts.

TRANSIENT-FACT RULE (CRITICAL): Any runtime state that can change silently — e.g. process PIDs, listening ports, 'running/stopped' status, temp files, cwd, currently-open sessions — MUST be written as a snapshot, not as a lasting fact. Format such lines like:
  - 『截至压缩时』PID 26364 监听 3001（需重新核对）
  - 『As of compression』port 3000 was listening on PID 18064 (re-verify before use)
Never write an unqualified 'PID X is running' / 'port Y is up' — the downstream agent will treat that as current truth and skip re-checking, which causes wrong conclusions when the process has since died.

Max ~800 Chinese characters or ~500 English words.
```

## User Message Template

```text
Transcript to compress:

{transcript}
```
