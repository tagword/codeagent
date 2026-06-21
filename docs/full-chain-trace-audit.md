# Full-Chain Trace Audit

This document records the planned and current trace audit design for debugging
long-running CodeAgent sessions.

## Goal

Projection audit answers: "What messages/tools were sent to the LLM?"

Full-chain trace should answer: "How did one user turn move through the whole
system?"

Trace data should support later optimization of:

- system prompt size
- tool schema size
- context compaction decisions
- recent-tail growth
- tool output growth
- context usage discrepancies
- persistence and UI event timing

## Enablement

Trace writes JSONL when either flag is enabled:

```bash
SEED_LLM_TRACE_AUDIT=1
```

or, for convenience while debugging LLM projections:

```bash
SEED_LLM_PROJECTION_AUDIT=1
```

`CODEAGENT_*` aliases work through the existing CodeAgent-to-Seed env bridge.

## Location

Default path:

```text
<sessions>/_trace/<session_id>/trace.jsonl
```

For project-scoped Web UI sessions:

```text
~/.dev_codeagent/agents/default/projects-data/<project_id>/sessions/_trace/<session_id>/trace.jsonl
```

The root can be overridden with:

```bash
SEED_LLM_TRACE_AUDIT_DIR=/path/to/trace-root
```

## Current Events

Current minimal implementation writes:

- `llm_request`
  - `round`
  - `audit_file`
  - `message_count`
  - `tools_count`
  - `max_tool_rounds`

- `llm_response`
  - `round`
  - `audit_file`
  - `usage`
  - `tool_calls`
  - `finish_reason`

- `tool_start`
  - `round`
  - `event_id`
  - `tool_call_id`
  - `tool`
  - `arguments`

- `tool_end`
  - `round`
  - `event_id`
  - `tool_call_id`
  - `tool`
  - `result_chars`
  - `result_preview`
  - `cancelled`

## Relationship To Projection Audit

Projection audit remains the source of truth for the exact LLM request
projection:

```text
<sessions>/_audit/<session_id>/<seq>-chat-r<round>.json
```

Trace references that file through `audit_file`, and records what happened
before and after the LLM call.

Projection audit currently records:

- messages
- tools schema
- body/tools/request bytes
- post-call usage

Trace records the lifecycle events around those snapshots.

## Future Events

Recommended additions:

- `turn_start`
  - user chars, attachment count, model preset, project id
- `projection_built`
  - base message count, projected message count, skills suffix chars, episodic
    memory chars
- `compact_decision`
  - enabled, triggered, cur tokens, min tokens, keep rounds, recent max chars,
    old/recent message counts
- `compact_result`
  - summary chars, dropped messages, recent compacted messages
- `context_usage_persist`
  - context bar value, peak prompt tokens, source
- `session_persist`
  - message count, metadata keys, path
- `ui_event`
  - context usage / compact / tool events sent to Web UI
- `error`
  - LLMError, summarizer failure, persistence failure, tool exception

## Notes

- Trace is append-only and should not contain secrets.
- Tool arguments and previews can still be sensitive in some projects; enable
  trace only when debugging.
- Long-running sessions can produce large trace files, so `_trace` should be
  treated as debug artifacts and cleaned periodically.
