# Context Compact Summary Prompt v2

Source: `seed/seed/core/agent_runtime.py`, `maybe_compact_context_messages()`.

This version replaces the fixed v1 length instruction with a dynamic policy based on
`SEED_CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS`.

## System Prompt Template

```text
You compress prior agent chat for continuation. Output structured bullet points in the same language as the transcript. Preserve continuation-critical state: user goals, current task status, files changed or inspected, shell commands, test results, error messages, tool names used, decisions already made, blockers, and unresolved questions. Prefer concise summaries, but do not make them so short that the next agent would need to rediscover important context. Do not invent facts.

TRANSIENT-FACT RULE (CRITICAL): Any runtime state that can change silently — e.g. process PIDs, listening ports, 'running/stopped' status, temp files, cwd, currently-open sessions — MUST be written as a snapshot, not as a lasting fact. Format such lines like:
  - 『截至压缩时』PID 26364 监听 3001（需重新核对）
  - 『As of compression』port 3000 was listening on PID 18064 (re-verify before use)
Never write an unqualified 'PID X is running' / 'port Y is up' — the downstream agent will treat that as current truth and skip re-checking, which causes wrong conclusions when the process has since died.

LENGTH POLICY: The hard generation budget is {sum_max_tok} tokens, configured by SEED_CONTEXT_COMPACT_SUMMARIZER_MAX_TOKENS. Stay concise by default, but use the available budget when needed to preserve critical continuation state.
```

## Dynamic Length Budget

```python
sum_max_tok = _get_compact_summarizer_max_tokens()
```

## User Message Template

```text
Transcript to compress:

{transcript}
```

## Recent Tail Budget

`SEED_CONTEXT_COMPACT_KEEP_USER_ROUNDS` is not sufficient for long-running coding
tasks because a single user round can exceed the model context window.

The compact system should treat user rounds as a preference, not as the hard
budget. After historical compaction, the projected prompt should also satisfy a
recent-tail budget:

- Keep recent user rounds when they fit the budget.
- If the recent tail is still too large, compact oversized messages in the API
  projection without deleting the persisted original history.
- Compact roles conservatively: `tool` output first, older `assistant` messages
  next, latest `user` messages last.
- For oversized `tool` output, preserve command/tool name, exit code, key errors,
  failed tests, traceback tails, and head/tail excerpts.
- For oversized `user` messages, preserve explicit instructions and constraints
  as original excerpts; use chunk summaries only when required by budget.
- The post-compact invariant should be budget-based:
  `system + compact summary + recent tail <= context target`.

Current implementation:

- `SEED_CONTEXT_COMPACT_RECENT_MAX_CHARS` controls the recent-tail character
  budget. Default: `120000`; `0` disables this projection shrink step.
- Oversized recent messages are compacted only in the API projection; persisted
  session history keeps the full original messages.
- Compaction priority is role-based: `tool` first, then `assistant`, then older
  `user`, and latest `user` last.
- The compacted projection keeps head/tail excerpts and marks that the full
  original remains in persisted history.
