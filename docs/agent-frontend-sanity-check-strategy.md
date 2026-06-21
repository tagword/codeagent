# Agent Frontend Sanity Check Strategy

CodeAgent is often used to edit other projects, so frontend checks must not be
hard-coded to CodeAgent's own `codeagent/web/static` directory.

## Where It Belongs

The reusable check belongs in `seed-tools`, starting with
`seed_tools/code_check.py`.

`code_check` is already exposed as a general agent tool, so improving it helps
any workspace the agent is editing.

## Rollout

1. Extend `seed_tools/code_check.py`.
   - For `.js` / `.jsx`, run `node --check` when Node is available.
   - Prefer project-local linters when available, but keep a lightweight syntax
     fallback.
   - Do not install dependencies automatically.

2. Add tests under `seed-tools/tests`.
   - Mock successful and failing `node --check` runs.
   - Verify syntax errors are returned in the tool report.

3. Add workflow-level automation later.
   - Track files changed during the current agent turn.
   - If frontend files changed, call `code_check` or project scripts before the
     final answer.
   - Project scripts should be selected from the nearest `package.json`:
     `typecheck`, `lint`, `test`, then `build` for stricter modes.

## Modes

- `auto`: lightweight checks after frontend edits.
- `strict`: prefer typecheck/lint/build when project scripts exist.
- `off`: skip automatic frontend checks.

Suggested env name: `CODEAGENT_FRONTEND_CHECK=auto|strict|off`.

## CodeAgent Web UI Self-Check

A separate test may check CodeAgent's own Web UI bundle, but that is a product
self-test, not the generic agent frontend check.
