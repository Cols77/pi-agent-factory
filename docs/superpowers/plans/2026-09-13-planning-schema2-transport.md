# FEAT-017 Planning Schema-2 Transport Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy schema-1 planning transport from the FEAT-017 host workflow and make schema 2 the only accepted external planning contract.

**Architecture:** Keep Coherence as the producer of lifecycle authority and use the existing schema-2 legal-actions projection as the single strict action contract. Migrate guided session/pipeline envelopes and host validation to the same outer schema without rewriting unrelated persisted artifact schemas. The Codex helper, Claude command, and Hermes plugin consume the same backend contract and fail closed on legacy or malformed responses.

**Tech Stack:** Python 3.12, argparse, strict JSON, SHA-256, pytest, Markdown skill/command contracts, Hermes plugin transport, and the repository's Coherence trace/measurement CLI.

---

### Task 1: Establish red schema-2-only contract tests

**Files:**
- Modify: `tests/unit/_legal_actions_json.py`
- Modify: `tests/unit/coherence/test_legal_actions_adapter.py`
- Modify: `tests/unit/codex/test_coherence_plan_helper.py`
- Modify: `tests/unit/coherence/test_planning_guided.py`
- Modify: `tests/unit/coherence/test_planning_manifest_transport.py`
- Modify: `tests/unit/hermes/test_coherence_plan_plugin.py`
- Modify: `tests/unit/codex/test_coherence_plan_contract.py`
- Modify: `tests/unit/coherence/test_coherence_plan_command_contract.py`

- [x] **Step 1: Change shared legal-actions fixtures to build complete schema-2 payloads.**

The fixture must include `state`, `run_identity` when ready, and an action
registry whose hash is computed from its `legal_ids`. Keep one explicit helper
for a schema-1 legacy payload so rejection is tested rather than silently
removed from coverage.

- [x] **Step 2: Add failing negative assertions for legacy and malformed transport.**

Cover schema-1 legal-actions rejection, schema-1 helper rejection, schema-1
guided session rejection, schema-1 pipeline rejection, Hermes schema-1
workflow rejection, wrong/missing run IDs, malformed per-verb payloads,
abbreviated project-root options, and blocked/ready contradictions.

- [x] **Step 3: Run the focused tests and verify the new assertions fail against the current implementation.**

Run:

```text
uv run pytest tests/unit/coherence/test_legal_actions_adapter.py tests/unit/codex/test_coherence_plan_helper.py tests/unit/coherence/test_planning_guided.py tests/unit/coherence/test_planning_manifest_transport.py tests/unit/hermes/test_coherence_plan_plugin.py tests/unit/codex/test_coherence_plan_contract.py tests/unit/coherence/test_coherence_plan_command_contract.py -q
```

Expected: failures show the current adapters and guided transports still accept or emit schema 1.

### Task 2: Make Coherence guided transport emit schema 2

**Files:**
- Modify: `src/coherence/planning/adapter_backend.py`
- Modify: `src/coherence/planning/guided_entrypoint.py`
- Modify: `src/coherence/planning/guided_pipeline.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/coherence/planning/session.py`

- [x] **Step 1: Add one shared external transport-schema constant.**

Define `PLANNING_TRANSPORT_SCHEMA = 2` in `adapter_backend.py`; import it in
the guided host adapters and CLI output paths. Do not change unrelated
persisted report, manifest, consent, journal, or handoff schemas.

- [x] **Step 2: Emit schema 2 from capture-session transport responses.**

Keep `PlanningSession.to_dict()` as the persisted state representation used by
`_write_state` and `status_session`. In `_session_command`, build the host
response with `PLANNING_TRANSPORT_SCHEMA` and the existing session fields,
including `ok` and challenge data. Emit the same schema-2 envelope on
`SessionError` and read-back failures.

- [x] **Step 3: Emit schema 2 from every guided pipeline CLI response.**

Change only the printed outer response for check/bootstrap/error,
manifest/review/consent/gate/handoff operations and preserve the internal
schema-1 report/manifest records consumed by their validators. The printed
response must retain the exact requested `run_id`; add it to any successful
verb response that does not currently expose it. Keep `suggest_downstream`
outside this guided transport allowlist as the explicitly legacy helper.

- [x] **Step 4: Make the guided adapters accept only schema 2.**

`parse_session_response` and `run_pipeline_command` must reject schema 1 and
must continue to reject wrong run IDs, malformed success/error payloads, and
untrusted exit codes. Add per-verb checks only for fields the adapter already
needs to interpret; do not duplicate backend planning logic in the host.

- [x] **Step 5: Run the focused red/green tests.**

Run the Task 1 command and verify the guided response tests pass while any
remaining host/helper failures identify the next migration boundary.

### Task 3: Make legal-actions and the Codex helper schema-2-only

**Files:**
- Modify: `src/coherence/planning/legal_actions_adapter.py`
- Modify: `.agents/skills/coherence-plan/scripts/coherence_plan.py`
- Modify: `tests/unit/_legal_actions_json.py`
- Modify: `tests/unit/coherence/test_legal_actions_adapter.py`
- Modify: `tests/unit/codex/test_coherence_plan_helper.py`

- [x] **Step 1: Remove the adapter's schema-1 branch.**

Require `payload["schema"] == 2` and always validate the schema-2 lifecycle,
identity, registry, one-action-or-block, and automatic-start invariants. A
schema-1 payload must raise the existing invalid-projection error.

- [x] **Step 2: Update the skill helper to validate the same schema-2 fields.**

Preserve its safe argv, exit-code, project-root, and run-ID behavior. Its
invalid-backend projection must use schema 2 and must never manufacture a
schema-1 fallback.

- [x] **Step 3: Run adapter/helper tests and verify legacy responses fail closed.**

Run:

```text
uv run pytest tests/unit/coherence/test_legal_actions_adapter.py tests/unit/codex/test_coherence_plan_helper.py -q
```

Expected: all schema-2 valid cases pass and all schema-1 cases fail before
rendering or action selection.

### Task 4: Align every supported host surface and documentation

**Files:**
- Modify: `.agents/skills/coherence-plan/SKILL.md`
- Modify: `.claude/commands/coherence-plan.md`
- Modify: `.hermes/plugins/coherence-plan/README.md`
- Modify: `.hermes/plugins/coherence-plan/plugin.py`
- Modify: `tests/unit/hermes/test_coherence_plan_plugin.py`
- Modify: `tests/unit/codex/test_coherence_plan_contract.py`
- Modify: `tests/unit/coherence/test_coherence_plan_command_contract.py`

- [x] **Step 1: State schema 2 as the only planning host transport contract.**

Document the exact legal-actions fields, the nested registry-version
exception, one-action-or-block rule, and fail-closed legacy behavior. Remove
schema-1 examples and claims that schema 1 is accepted.

- [x] **Step 2: Require schema 2 in Hermes workflow transport.**

Keep the existing allowlisted verb set and explicit run-ID/project-root
controls. `_run_workflow` must reject a schema-1 response, malformed common
envelopes, and run-ID mismatches before returning data to Hermes.

- [x] **Step 3: Update host contract tests.**

Assert that Codex, Claude, and Hermes surfaces advertise/use schema 2, keep
the exact Coherence command path, reject abbreviated project-root options,
and preserve the non-executing handoff boundary.

- [x] **Step 4: Run the complete focused host contract suite.**

Run:

```text
uv run pytest tests/unit/coherence/test_legal_actions_adapter.py tests/unit/coherence/test_planning_guided.py tests/unit/coherence/test_planning_manifest_transport.py tests/unit/coherence/test_planning_lifecycle.py tests/unit/codex/test_coherence_plan_helper.py tests/unit/codex/test_coherence_plan_contract.py tests/unit/coherence/test_coherence_plan_command_contract.py tests/unit/hermes/test_coherence_plan_plugin.py -q
```

### Task 5: Record Coherence traceability and verify the migration

**Files:**
- Create: `docs/superpowers/specs/2026-09-13-planning-schema2-transport-design.md`
- Create: `docs/superpowers/plans/2026-09-13-planning-schema2-transport.md`
- Modify: focused tests with `@pytest.mark.sr("SR-065")` and/or `@pytest.mark.sr("SR-071")` markers where the existing test file is the real binding point

- [x] **Step 1: Run focused Coherence measurement for the bound SRs.**

Run:

```text
uv run coherence measurement run --project-root . --satisfies SR-065
uv run coherence measurement run --project-root . --satisfies SR-071
```

Use the real focused test files and report the resulting evidence; do not
claim a requirement is bound without a deterministic test marker and passing
measurement.

- [x] **Step 2: Run repository trace and register checks for baseline comparison.**

Run:

```text
uv run coherence trace check --project-root .
uv run coherence register check --project-root .
```

Record any pre-existing failures separately from migration regressions.

- [x] **Step 3: Run the full test suite, lint, and type checks.**

Run the repository's configured `unit`, `integration`, and `full` commands
from `.factory/factory.yaml`; the full gate must include the configured
extension scripts. A live Hermes smoke test must exercise legal-actions and
one guided transport verb against the isolated checkout.

- [x] **Step 4: Perform an independent review of the diff and changed-path scope.**

Confirm that no unrelated schema-1 persistence contract changed, no host can
accept a schema-1 external response, and no host starts or selects work from a
malformed response.

- [x] **Step 5: Commit only the scoped migration.**

Use a commit message with an SR trailer, for example:

```text
fix(coherence): make planning hosts schema-2 only

Satisfies: SR-065, SR-071
```

Before integration, compare the changed paths against the dirty main worktree
and fast-forward local `main` only after the user selects that integration
step. Do not push or merge automatically.

## Self-review

- The plan covers legal-actions, guided session/pipeline envelopes, Codex,
  Claude, Hermes, docs, fixtures, negative tests, and Coherence evidence.
- Schema-1 persisted records remain explicitly outside the migration boundary.
- The only intentionally retained nested version is
  `action_registry.schema: 1`.
- No step invents a new planning run ID or starts a mutating Coherence run.

## Verification record

- Focused migration suite: 243 passed; focused CLI/integration boundary: 21
  passed, 1 skipped; final host subset: 134 passed, 1 skipped.
- Full unit gate: 3,937 passed, 19 skipped, 137 deselected. Integration gate:
  49 passed, 6 skipped.
- Ruff passes on all migration paths. Repository-wide Ruff has one unrelated
  pre-existing unused import; Pyright has 81 unrelated baseline errors, and
  the extension gates lack the local `tsc` executable.
- `coherence mirrors check` passes. Trace/register checks and SR-065/SR-071
  measurements were run and remain blocked by the repository's pre-existing
  traceability/measurement baseline; no false binding or generated report was
  claimed.
- Live Hermes and Coherence legal-actions smoke tests returned schema-2
  envelopes and rejected stale/missing state without starting work.
