---
id: SPEC-FEAT-013-GOVERNED-EXECUTION-DRIVER
title: "FEAT-013 Governed Execution Driver"
status: accepted
feature: FEAT-013
requirements:
  - SR-034
  - SR-049
---

# FEAT-013 — Governed Execution Driver: capture-to-spec design

_Date: 2026-09-08. Run: `FEAT-013`. Source: `.intent/intent.json` (capture_status:
provisional), answers a2–a11, all raised challenges dispositioned. This spec exists to
carry forward everything captured, including the gaps an intent-review pass flagged before
its findings were lost to a permission error (see Open questions)._ 

## Captured intent coverage

The authority spec carries the captured decisions explicitly: `a2` active trace
completeness is checked inside the driver loop; `a3` keeps DEV, reviewers, and
fixer in fresh contexts; `a4` requires baseline and campaign pass-rate evidence;
`a5` and `a6` retain the existing backend and human authority boundaries; `a7`
uses one execution-owned worktree; `a8` requires a human decision on budget
exhaustion; `a9` forbids blind retry and bounds only fixer iterations; `a10`
surfaces worker, flaky, regression, and infrastructure failures; and `a11`
uses the known-flaky-first, one-confirmation-rerun classification policy.

## 1. Requirement served

**SR-034** (proposed, unconsented): "The system shall drive governed execution by plugging
free and Hermes subagents and worktrees into the factory node pipeline as worker nodes, with
parallel spec-compliance and code-quality reviewers and a fixer-until-silent loop,
MCP-exposed and backend-gated, without rebuilding the enforcement it composes."

**SR-049** (implemented, verified) already gates commit-time trace completeness — a
commit's `SR:` trailer must match real `implements`/`verified_by` relations, checked by the
register/obligation/structural-trace/test-marker gates. Capture (a2) decided SR-034 must
**not** rely on that happening passively at commit time — the driver's own loop gates on it
too, before a task can report done (AC-4).

## 2. Boundary

**In scope for SR-034:**
- A host-side implementation of the existing `AgentBackend` protocol
  (`src/factory/orchestrator/backends.py`) that speaks to Hermes/free subagents.
- An orchestration driver that boots the existing node pipeline
  (`src/factory/orchestrator/nodes.py`, `runner.py`) with that backend, runs the review
  swarm in parallel, runs the fixer-until-silent loop, and surfaces human-review gates.
- The driver's own MCP tool surface, exposed through the FEAT-9 MCP adapter.
- Thin Codex and Claude Code entrypoints that invoke the same Python-owned execution
  command surface: a project-local Codex skill under `.agents/skills/` and a Claude
  Code command under `.claude/commands/`. These are host adapters only; they do not
  own lifecycle state, gate interpretation, retries, consent, or transport state.

**Out of scope** (per `docs/features/FEAT-013.md`'s design boundary, restated here since
capture didn't re-derive it): a second scheduler, worker supervisor, retry engine, or
worktree allocator; the MCP server itself (FEAT-9/SR-028/SR-047 own that — this driver only
adds verbs to it); the general workflow interpreter and gate taxonomy (FEAT-16/FEAT-14); the
deterministic multi-task orchestration-graph validation FEAT-18 will eventually own — this
driver executes one already-selected task, it does not validate a whole generated plan graph.

**Enforcement is not built here.** Every gate, obligation check, and traceability rule this
driver relies on already exists in the Python backend. SR-034 adds exactly two things: a
backend implementation and an orchestration driver around it — never a parallel enforcement
path.

## 3. Worker roles — mapping to the existing model

Capture used informal labels ("dev," "spec-compliance reviewer," "code-quality reviewer,"
"fixer"). The backend's actual `AgentRole` enum (`factory/orchestrator/types.py`) has `DEV`
and one `REVIEW` role, not two distinct reviewer roles. Per the "without rebuilding the
enforcement it composes" constraint, this spec resolves the mapping as:

| Captured label | Backend role | Notes |
|---|---|---|
| dev | `AgentRole.DEV` | writes the change |
| spec-compliance reviewer | `AgentRole.REVIEW` (invocation 1) | prompted to check the change against the task's declared spec/AC scope only |
| code-quality reviewer | `AgentRole.REVIEW` (invocation 2) | prompted to check code quality, reuse, simplification |
| fixer | `AgentRole.DEV` (fresh session) | a new `DEV` invocation, never the same session as the dev pass it is fixing (AC-2) |

Two `REVIEW` invocations run in parallel, each a distinct session per AC-2 — this is a
policy the driver enforces (distinct sessions, distinct prompts), not a new enum value. If
a future gate needs to distinguish the two review outcomes structurally, that is a follow-up
requirement, not part of SR-034's first cut.

## 4. Driver contract (I/O)

The driver's unit of work is one task. It consumes and produces the backend's existing
shapes — no new result type:

- **Input:** a task id resolvable to a `TaskResult`-producing unit of work (matching the
  existing `runner.py` contract), plus the task's declared SR(s)/plan/spec references.
- **Output:** a `TaskResult` (`task_id`, `title`, `outcome` ∈ {completed, rejected,
  escalated}, `iterations`, `events: list[NodeEvent]`, `dod_met`, `manifest`,
  `start_commit`, `result_commit`) — unchanged shape. `NodeEvent.result` maps onto the
  existing `NodeOutcome` enum (`pass`/`fail`/`reject`/`changes-requested`/`escalate`/
  `already-done`); AC-7's budget exhaustion is a `NodeOutcome.ESCALATE` event, not a new
  outcome kind.

## 5. Acceptance criteria and explicitly marked proposals

**AC-1 — Backend seam + host exposure.** Any host implementing the existing `AgentBackend`
protocol can drive a task through dev→review→fix without the backend's enforcement (gates,
trace, human-review) changing shape. The driver's own verbs (dispatch task, report worker
result, stream progress) are exposed through the existing FEAT-9 MCP adapter (SR-028/SR-047)
and are the only backend invoked by the Codex skill and Claude Code command. This feature
does not stand up a second MCP server or give either command/skill a local execution state
machine.

**AC-2 — Fresh-context, ordered review/fixer.** The two `REVIEW` invocations (§3) run
independently in parallel, each in a session distinct from the `DEV` session that produced
the code — hard requirement, enforced by the orchestration, no shared context permitted. The
fixer (`DEV`, fresh session) is not spawned until *every* reviewer has completed. The loop
does not terminate until a fixer pass produces a revision on which every reviewer, re-run
fresh, reports clean.

**AC-3 — No bypassing required gates.** The driver never advances a task past a required
gate or human-review interrupt without the backend's own resolution; no host-side override.

**AC-4 — Trace-completeness gated inside the loop.** The driver's own loop checks SR-049's
register/obligation/structural-trace/test-marker relations before a task can report
`completed`; a task carrying a commit that would fail SR-049's checks does not reach done.

**AC-5 — Test-campaign pass rate and regression handling, no blind retry.** Before the first
`DEV` pass, the driver records the passing baseline for every test in the task's required test
campaign. After each `DEV` pass, it runs the complete required campaign, verifies its required
pass-rate gate, and compares the result with that baseline. A regression (a test that passed at
task start, now fails) is injected back to `DEV` as a new fix task; a pre-existing unrelated
failure is not a regression, and the failing test itself is never re-run unchanged hoping for a
different result. The only bound on how many times this cycle repeats is AC-7's fixer-iteration
budget — `repeatable_policy`/`max_reruns` does not apply to this cycle (that machinery governs
re-running non-deterministic `verification_result` obligations, e.g. measurement trials, a
different concern).

**AC-6 — One worktree per execution.** The driver allocates exactly one worktree per
workflow execution, through the existing execution/workspace owner, and passes that same
worktree to every worker role (`DEV`, both `REVIEW` invocations, the fixer) assigned to that
execution. The driver does not allocate a separate worktree per role.

**AC-7 — Bounded fixer-iteration budget.** The dev→review→fixer loop is bounded by a
configured **project-wide default** maximum fixer-iteration count (not per-workflow, for
now). Exhausting it without a clean revision blocks the task (`NodeOutcome.ESCALATE`) and
requires an explicit human decision: retry (reset the budget), defer the remaining finding
via the existing `Deferral` primitive (`coherence.deferrals`; `reason`/`review_after`/
`decided_at`/`decided_by`), or block outright. The driver never auto-defers or auto-accepts
a finding itself.

**Proposed AC-8 — Narrow preflight (unconfirmed).** This is a plan-stage proposal, not a
captured SR-034 acceptance criterion; it must not be treated as adopted until the human confirms
it. Before dispatching any worker for a task, the driver checks the
task's declared SR(s)/plan/spec against the backend's existing obligation/health queries
(`policy.compiler.compile_obligations`, `coherence navigate health`) and refuses to start if
a required obligation is unsatisfied/failing or the artifact is stale. This check is binary
(pass/refuse), invents no new health metric, and is explicitly scoped to be **superseded,
not duplicated,** by FEAT-18's validated `ExecutionProposal` if/when that feature is built.

**AC-9 — Flaky vs. regression classification.** When a required test fails, the driver
checks the test id against a maintained known-flaky registry first (§6). A listed id is
surfaced to the human without touching the fixer-iteration budget or injecting a fix task.
An unlisted id gets exactly one bounded confirmation re-run via `repeatable_policy`/
`max_reruns`, purely for classification, not as a fix attempt: a pass is surfaced to the
human as a registry candidate (added only by human curation, never automatically) and does
not consume fixer-iteration budget; a repeated failure is a real regression and follows AC-5.

## 6. Known-flaky registry — concrete shape

Not specified during capture; resolved here as the minimal shape consistent with this
codebase's existing patterns (a versioned JSON record under project state, mirroring how
`gate-decisions/` and `review-findings/` are structured):

- **Location:** `flaky-tests/<test-id-safe-slug>.json` (one file per registered test, same
  one-fact-per-file convention as `requirements/` and `gate-decisions/`).
- **Shape:** `{"schema": 1, "test_id": "<pytest node id>", "reason": "<human text>",
  "decided_by": "<human>", "decided_at": "<ISO instant>", "review_after": "<ISO instant |
  null>"}` — same fields as `coherence.deferrals.Deferral`, reused rather than inventing a
  second record shape.
- **Write path:** human-only, via a CLI verb this feature adds (`coherence execution
  flaky-register <test-id> --reason ...`); the driver only *reads* this store, never writes
  to it — AC-9 explicitly requires a human to curate additions.

This is a design proposal for the plan stage to decompose into tasks, not something capture
decided explicitly — flagged for the review subagent and for your confirmation before the
plan is written.

## 7. Authority preservation

Restating explicitly (the review flagged this as underspecified): Coherence's authority is
preserved because every guarantee above is either (a) reading an existing canonical source
(obligations, register, gate results, `Deferral` records) rather than the driver deciding
health itself, or (b) blocking on a human decision (AC-7, AC-9's registry curation) rather
than the driver resolving ambiguity on its own. The driver orchestrates; it never becomes a
second acceptance authority. No AC in §5 grants the driver a judgment call the backend does
not already make deterministically, except the two points explicitly named as new project
state this feature introduces: the fixer-iteration budget default (a human-set config value)
and the flaky-test registry (human-curated).

## 8. Failure modes

- **Backend/worker unavailable** (Hermes gateway down, free-model pool exhausted): out of
  scope for SR-034 to solve — per FEAT-013's dossier, this feature does not build a second
  scheduler or retry engine. The driver surfaces the failure and stops; Hermes-side recovery
  is Hermes's job.
- **Gate/obligation query fails at preflight (AC-8):** refuse to start, surface the specific
  failing check — never start a doomed run.
- **Fixer budget exhausted (AC-7):** block, escalate to human; never silently downgrade.
- **A worker writes outside its assigned worktree (AC-6):** candidate handling is a task failure
  (`NodeOutcome.REJECT`), not a warning. Capture did not resolve hard-fail vs. soft-flag
  explicitly; this candidate is not adopted until the human confirms it.
- **Contract/gate tampering mid-run:** per FEAT-013's dossier, this pauses the run and
  creates a control-plane finding — inherited unchanged from the existing backend behavior,
  not new to this driver.

## 9. Definition of done (first tracer bullet)

One representative task executes end-to-end through: `AgentBackend` seam confirmed → candidate
preflight (if AC-8 is confirmed) passes → `DEV` pass → parallel fresh-context `REVIEW` × 2 (AC-2) → test
gate run with AC-5/AC-9 regression/flaky handling → trace-completeness check (AC-4) →
`TaskResult` with `dod_met: true`, all within one worktree (AC-6) and the fixer-iteration
budget (AC-7), with every driver verb reachable through the FEAT-9 MCP adapter (AC-1). No
required gate was bypassed; every human-decision point that fired produced a real decision
record, not a synthetic one.

## 10. Open questions carried to the plan stage

1. The known-flaky registry's CLI verb name, storage path, and write-path ownership (§6) is
   this spec's proposal, not a captured decision — confirm before tasks are generated.
2. Hard-fail vs. soft-flag for out-of-scope worktree writes (§8) is resolved here by
   inference from house style, not captured explicitly — confirm.
3. The fixer-iteration budget's actual default value was never numerically decided (only
   that it's project-wide) — needs a number before implementation.
4. Whether `AgentRole.REVIEW`'s two parallel invocations need a machine-distinguishable
   sub-role (e.g. a prompt-only distinction is invisible to any future gate that wants to
   check "did both reviewer *kinds* run," not just "did two reviews run") is unresolved.
5. Whether the proposed narrow preflight in AC-8 belongs in SR-034 scope, or should be
   supplied by FEAT-18's validated `ExecutionProposal`, was not decided during capture.
6. Whether an out-of-worktree write is a hard failure (`NodeOutcome.REJECT`) or a soft flag
   was not decided during capture.

## 11. Addendum (2026-09-13): Hermes host entrypoint

Raised during implementation: §2 and AC-1 gave Codex and Claude Code thin command/skill
entrypoints onto the Python-owned execution command surface, but named no equivalent for
Hermes — despite Hermes already being in scope as a worker backend (§1, §2) and as the
`hermes-kanban` transport (Task 8). Those two roles cover Hermes *running* dispatched work
and *displaying* stage state on a board; neither gives a human working from a Hermes session
a way to ask "what's the status of T-013" or issue a `retry`/`defer`/`block` decision without
switching hosts. This addendum closes that gap the same way AC-1 closed it for Codex and
Claude Code, extending — not replacing — the original boundary.

**In scope, added to §2:** A project-local Hermes plugin (`.hermes/plugins/governed-execution/`,
mirroring the existing `.hermes/plugins/coherence-plan/` pattern) that invokes the same
Python-owned execution command surface as the Codex skill and Claude Code command. It is a
host adapter only: no local execution state, no lifecycle interpretation, no second journal.

**AC-10 — Hermes host exposure.** The Hermes plugin calls `coherence execution legal-actions`
before `dispatch-task`, exactly as AC-1 requires of the Codex skill and Claude Code command; it
renders `needs_input` unchanged and calls `coherence execution resolve-human` only after a human
selects `retry`/`defer`/`block`; it never infers a transition from Hermes's own Kanban `done`
card or a model response. For one fixture run, the Hermes plugin, Codex skill, Claude Code
command, Pi tools, and direct CLI produce equivalent legal-action and event projections
(extending Task 7's existing cross-host parity assertion to include this fourth surface).
`starts_automatically: false` applies here exactly as it does everywhere else in this spec.

This does not change AC-1's original text or the already-recorded SR-034 consent
(`gate-decisions/sr-SR-034.json`); it is new scope added after that consent, carried forward
into the plan as a new task (Task 9) rather than folded into the already-implemented Task 6.
