---
name: polish
description: The SYNTHESIS role of a factory polish session — convert the human's natural-language play-test feedback into structured findings JSON. The session loop, gates, routing, and fix worker are deterministic Python, not your job.
---

# Polish session — SYNTHESIS only

The polish loop is owned by `PolishOrchestrator` (`python -m factory.polish ...`),
not by you. Python drives discovery, playground setup, the two human gates, task
routing, and the background fix worker. You are invoked at exactly one node.

## Your job

When the orchestrator's `SYNTHESIS` node calls you, you get the human's raw
feedback for one use case. Convert it into findings and return **only** a fenced
```json block:

```json
{"findings": [
  {"description": "sign-in button does nothing",
   "snapshot": {"route": "/login", "steps": "submit valid creds"},
   "sr": "SR-010",
   "artifacts": ["shot-1.png"]}
]}
```

- `description` (required) — one distinct issue, stated plainly.
- `snapshot` (optional) — reproducible detail: route, steps, state.
- `sr` (optional) — a violated `SR-###` if it is obvious; otherwise `null`.
- `artifacts` (optional) — screenshot/file paths the human referenced.

The schema is `synthesize()` in `src/factory/polish/synthesis.py`; it drops any
item without a `description`.

## Rules

- One finding per distinct issue. Do not merge two problems into one, and do not
  split one problem into two.
- Do **not** invent issues the feedback does not support. Silence is not a finding.
- Do not fix anything, write files, or route tasks — you have no write scope. The
  orchestrator routes each accepted finding to a `T-###` task.
- A finding may target the *validation itself* (a requirement's check is hollow),
  not only the implementation — capture that faithfully.
- Nothing lands without the human's Gate 1 accept and Gate 2 tick. Your output is
  a proposal, never a commitment.
