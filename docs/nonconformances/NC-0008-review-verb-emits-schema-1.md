---
id: NC-0008
title: coherence.planning.cli's review handler emits schema 1, so guided_pipeline review always fails transport validation
external_ref: null
detected_by: FEAT-018 guided_pipeline review attempt
status: open
---

## Symptom

`guided_pipeline review --run-id <any-run>` fails with `{"schema": 2, "run_id": "<run>", "ok":
false, "error": "invalid planning pipeline response"}` for every run, unconditionally — not
specific to FEAT-018 or to any content in its spec/plan.

Root cause, confirmed directly from source:

- `PLANNING_TRANSPORT_SCHEMA = 2` (`src/coherence/planning/legal_actions_adapter.py:56`) is the
  schema-2 transport envelope this whole guided-planning surface has been migrated to.
- `src/coherence/planning/cli.py`'s `_review` handler (~line 415-441) builds its payload via
  `build_escalation(...)` (`src/coherence/planning/run.py:124-149`) and prints it directly with
  two fields (`ok`, `hashes`) merged in afterward — it never overwrites the `schema` field.
  `build_escalation` itself hardcodes `"schema": 1` (`run.py:145`).
- Every OTHER handler in `cli.py` that emits a transport payload explicitly sets
  `payload["schema"] = PLANNING_TRANSPORT_SCHEMA` (or constructs the dict with that key directly)
  before printing — confirmed at `cli.py` lines 97, 119, 237, 273, 406, 467, 494, 522, 541, 586,
  589, 593. `_review` is the one handler that omits this.
- `src/coherence/planning/guided_pipeline.py`'s `run_pipeline_command` (~line 88-118), the
  sanctioned adapter every host (Codex, Claude Code, Pi) is required to use instead of calling
  `coherence plan` directly (enforced by this repo's own commit-time/session hook), parses the
  backend's stdout as JSON and rejects it via `_malformed()` whenever `payload["schema"] !=
  PLANNING_TRANSPORT_SCHEMA` — which is always true for `review`'s output, since it is always `1`.

Reproduced on FEAT-018's own run, after `bootstrap`/`check` both passed cleanly (`ok: true`, zero
findings): `guided_pipeline review --run-id FEAT-018 --project-root .` returned the generic
`"invalid planning pipeline response"` error with empty backend stderr (the JSON parsed fine, so
`invoke_backend` never raised — the failure is purely the schema-field mismatch inside
`run_pipeline_command`'s own payload-shape check).

Not fixed here: `_review`/`build_escalation` are backend code, out of scope for a planning session
(which authors spec/plan/intent content, not backend code) to fix as a side effect.

## Correction

Not yet corrected. Needs its own scoped change, same as NC-0004/NC-0005/NC-0007:

1. Either set `escalation["schema"] = PLANNING_TRANSPORT_SCHEMA` in `_review` (`cli.py`) before
   printing, mirroring every sibling handler, or change `build_escalation`'s own hardcoded
   `"schema": 1` to accept/default to the current transport schema — pick whichever keeps
   `build_escalation`'s other callers (if any exist beyond `_review`) correct too; check for other
   call sites before choosing.
2. Add a regression test asserting `guided_pipeline review`'s returned payload has
   `schema == PLANNING_TRANSPORT_SCHEMA` for a run with a valid, already-produced
   `.factory/planning/<run-id>/report.json` (clean and with findings, both cases), so the adapter's
   own transport-shape check accepts it end-to-end rather than only unit-testing `build_escalation`
   or `_review` in isolation.
3. Confirm no other consumer of `build_escalation`'s literal `schema: 1` value depends on that
   specific number (grep before changing the default).
