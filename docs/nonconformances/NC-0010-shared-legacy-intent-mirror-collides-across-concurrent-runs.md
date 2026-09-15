---
id: NC-0010
title: The unnamespaced legacy intent mirror (.intent/intent.json) lets any two concurrent planning sessions in the same checkout stomp each other's captured intent
external_ref: null
detected_by: FEAT-018 planning run, legal_actions_adapter FEAT-018 unexpectedly returning STALE_SESSION_STATE after FEAT-019 capture began concurrently in the same checkout
status: open
---

## Symptom

`uv run python -m coherence.planning.legal_actions_adapter FEAT-018` returned:

```
Planning blocked: STALE_SESSION_STATE
Legal actions: none
Starts automatically: no
```

with zero prior indication anything about FEAT-018's own run had changed. FEAT-018's `check` and
`review` had both already passed cleanly against `.factory/planning/FEAT-018/intent.json` (the
canonical, run-scoped copy) earlier in the same session.

Root cause, confirmed directly from source (`src/coherence/planning/session.py`):

- `_intent_path(root, run_id)` (line 88) returns the canonical, run-namespaced path:
  `.factory/planning/<run_id>/intent.json`.
- `_legacy_intent_path(root)` (line 92) returns a single, **unnamespaced** path shared by every
  run in the checkout: `.intent/intent.json`.
- `_materialize` (line 117) writes **both** paths on every capture mutation for **every** run —
  there is no run-id check before overwriting the legacy path.
- `read_session_intent` (line 96) reads whichever path exists, replays the canonical journal, and
  — when both paths exist — compares the legacy copy against the freshly-read canonical copy
  (lines 106-109): `if legacy != intent: raise SessionError("legacy intent mirror is stale")`.
- `legal_actions_session` (line 360) calls `status_session`, which reaches `read_session_intent`
  transitively; it catches any `SessionError` generically and reports
  `{"blocked": True, "reason": "STALE_SESSION_STATE"}` (line 376), with no distinction between
  "this run's own journal is corrupt" and "a *different* run's capture overwrote the shared
  mirror."

Reproduced concretely this session: a concurrent session capturing FEAT-019 in the **same**
working-directory checkout (not an isolated worktree) triggered `_materialize` for FEAT-019, which
overwrote `.intent/intent.json` with FEAT-019's data. FEAT-018's own next `read_session_intent`
call found `legacy != intent` (legacy now holds FEAT-019's snapshot, canonical still holds
FEAT-018's) and raised, surfacing as FEAT-018's own run being "stale" even though nothing about
FEAT-018's actual capture had changed.

**Not a source-code-collision problem.** This is unrelated to two features legitimately touching
overlapping source files later in implementation — it is specifically about one single shared
capture-state mirror file with no per-run namespacing or locking across concurrent sessions in one
checkout.

**Not new build-scope creep.** The Claude Code compat-route commands used for FEAT-018's own
`check`/`review`/`bootstrap` all pass `--intent .factory/planning/FEAT-018/intent.json` (the
canonical path) explicitly, so this NC did not affect FEAT-018's actual planning correctness — only
the separate guided-route's `legal_actions_adapter` snapshot, which reads through
`read_session_intent`/the legacy mirror. Still a real defect: any host relying on the guided route
(the sanctioned `/plan <run-id>` entrypoint, not just this compat route) is exposed to it.

## Correction

Not yet corrected. Two independent angles, either of which resolves the symptom on its own:

1. **Operational (no code change, available immediately):** never run two coherence-plan captures
   concurrently against the same checkout — always capture from an isolated git worktree per run
   (already this repo's own established rule for feature work; extend it explicitly to planning
   captures too, which this session did not follow). Worktrees do not share a working directory, so
   `.intent/intent.json` would no longer be a cross-run shared file.
2. **Code hardening (larger, needs its own design pass, not a same-session bugfix):** either (a)
   namespace or lock the legacy mirror per run so a second run's materialize cannot silently
   overwrite the first's, (b) have `read_session_intent`'s staleness check distinguish "the legacy
   mirror belongs to a different run_id" (recoverable — just re-materialize from the canonical
   snapshot) from "this run's own canonical/legacy pair genuinely disagree" (a real corruption), or
   (c) deprecate the legacy mirror outright now that the canonical run-scoped path is what every
   backend command actually reads/writes — determine first whether any current consumer still
   depends on the shared `.intent/intent.json` location before removing it (`gates.py`'s
   `_required_planning_sources`, ~line 297/305, deliberately reads it, but only for FEAT-017's own
   closure evidence — see NC-0009 — so may not need it once/if NC-0009 is resolved).

Whoever picks up (2) should scope it as its own planning run, not an ad hoc fix — it changes a
concurrency/durability contract, not a single hardcoded literal.
