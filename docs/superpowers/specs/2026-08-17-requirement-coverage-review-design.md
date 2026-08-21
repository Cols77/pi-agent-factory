# Design: Requirement Coverage Review workflow (feature-scoped audit)

**Date:** 2026-08-17
**Status:** Draft for review
**Case study:** pi-agent-factory itself, then `cool_physical_ai_project` (drone product).

## 1. Problem

The traceability-first system today verifies **presence**, not **truthfulness**:

- A `satisfies:` link is created by LLM judgment (trace-fix) and nothing ever checks
  that the task's actual code implements the requirement's claim. The gate detects
  *absence* (`task_no_sr`, `sr_unsatisfied`) but never *incorrectness* — a wrong link
  raises the health score.
- A bound requirement is measured by whatever pytest selection the binding names
  (`unit_pass_rate`), but nothing verifies that the test module exercises the code
  the satisfying task changed. A trivial test that passes `== 1.0` without touching
  the implementation is a fabricated pass.
- The one mechanism designed for semantic verification — the `REQ_REVIEW` role from
  the 2026-07-30 validation design (R2Code/TVR-style, read-only, per-requirement
  `implemented/validated/confidence/verify[]`) — was never implemented
  (`roles.py` still marks VALIDATION dormant).
- The register's `[proposed]` state and the closure gate (`PENDING` /
  `MEASURED_PASSING` / `MEASURED_FAILING` / `DECLINED`) decide *measurement*
  disposition, but there is no workflow that audits a feature as a whole: are its
  declared requirements actually governed, actually implemented, actually measured,
  actually fresh, and honestly represented?

This design adds a **coverage review workflow**: a feature-scoped audit that runs
like `factory-run` — deterministic phases for resolution and computation, one
independent subagent per requirement for judgment, a gate that fails on dishonest
coverage, and a report written for one-pass human review.

## 2. Non-goals

- **No auto-authored requirements.** The audit never writes an SR. New requirements
  are *proposed* and materialized only through the existing human-gated doctor flow.
- **No semantic documentation gate.** "Is this documentation truly representative"
  is a human judgment; the audit only machine-checks that docs exist and are linked.
- **No plan-writing by subagents.** Subagents return structured findings; the main
  session decides whether and how to plan fixes.
- **No new register format, no new trace model.** Reuses `requirements/SR-###.md`,
  the trace graph, run manifests, and the closure machinery as-is.

## 3. Invariants

1. **The auditor never authors the audited artifact.** The coverage workflow cannot
   create, bind, or reaffirm a requirement. Every write goes through the existing
   tool surface, and every new requirement goes through a human gate (doctor flow).
   Inventing an SR to close a feature gap would launder a design opinion into a
   verification artifact — the worst form of dishonest coverage.
2. **Subagents judge, never discover.** Phase 0 resolves the scope graph
   deterministically; each subagent receives a fixed packet and returns a fixed
   verdict. A subagent that must hunt for links will find different things than the
   last one did, and will spend its context on navigation instead of judgment.
3. **Machine-verifiable claims are machine-verified.** The import-graph overlap
   check is computed, not asserted. An LLM cannot waive it; it can only explain it.
4. **Every finding carries its reasoning.** Nothing in the report is a bare boolean:
   each verdict and each machine result includes a rationale and evidence anchors
   (file/line/command output), so a human reviews the report in one pass without
   reopening subagent sessions or files.
5. **Not audited is not passed.** An SR with no subagent verdict is pending, not
   green. The gate fails on it until audited or until a human records a deferral
   with a reason.
6. **Decisions are recorded.** Rejecting or deferring a proposed requirement is
   written down (house pattern: `trace_deferred:` on the SR file → closure `DECLINED`),
   so the next run does not re-propose it.
7. **The deterministic phases are the evidence layer, not the verdict.** Phase 0/1
   and the gate guarantee that the judgment's inputs are complete, honest, and
   reproducible; they never substitute for the semantic judgment of whether code
   implements a statement. That judgment is made by a subagent on injected context.

## 4. Workflow overview

```
/coverage-review <feat:FEAT-XXX>
│
├─ Phase 0  (machine) scope resolution
│     feat → declared SRs (feat `requirements:` + contains edges)
│     SR   → tasks (satisfies edges) → changed files (run manifests + git)
│     SR   → binding, measurement, staleness (register + manifests + freshness)
│     output: per-SR packet + feature completeness map
│
├─ Phase 1  (machine) import-graph overlap
│     for each SR with a pytest binding:
│       transitive imports of binding test ∩ changed files of satisfying tasks
│     output: import_overlap per SR (pass/warn), machine-computed
│
├─ Phase 2  (subagent) one independent audit per SR
│     input:  the fixed Phase 0/1 packet
│     output: fixed-format verdict {implemented, honest, confidence,
│             margin, reasoning, checked[], assumed[], verify[]}
│     parallel; one session per SR (never the DEV session)
│
├─ Phase 3  (machine) consolidation
│     classify each SR: pass / suspect / unmeasured / unlinked / unverified / declined
│     output: feature coverage report
│
├─ Phase 4  (machine) gate
│     FAIL: unlinked, implemented=false, honest=false, no verdict
│     WARN: import_overlap=false, stale binding/validation
│     output: pass/fail + failing list
│
└─ Phase 5  (report + disposition)
      findings → main session, written for one-pass human review
      proposed_requirements[] → human gate via doctor flow (accept/reject/defer)
      suggested_actions[] → main session decides what to plan, with which skill
```

## 5. Phase 0 — scope resolution (machine, deterministic)

Implemented as `factory coverage audit <feat:FEAT-XXX>` (new `src/factory/coverage/`
package). Reuses, does not re-derive:

1. **Feature → declared SRs.** Read the `feat:` file's `requirements:` frontmatter
   and the `contains` edges from the trace graph. Both must agree; a discrepancy is
   itself a finding.
2. **SR → tasks.** `satisfies` edges from the trace graph
   (equivalently `eng_trace_requirement <sr:ID>`: requirement → satisfying tasks →
   changed files).
3. **Task → changed files.** Run manifests (`list_run_manifests`) give
   `start_commit`/`result_commit` per run; implementing files = `git diff
   start_commit..result_commit --name-only`, unioned with the task's declared
   `deliverables` (reuses `parse_deliverables` and the review-diff.ts
   `computeImplementingFiles` semantics).
4. **SR → binding/measurement/staleness.** From the register: `binding` block,
   checksum staleness (`is_checksum_current`). From manifests: newest validation
   entry for the SR (`passed`, `value`, `assert`, `trials`, `declared_trials`,
   `artifacts`). From freshness/reconcile: `STALE_VALIDATION` findings. Goal-aware
   status (`requirement_validation`) when goals are bound.

**Output per SR** (the fixed packet, also passed to Phase 2 subagents):

```
sr_id, statement, binding {harness, experiment, metric, assert_expr, trials},
checksum_state {current|stale},
tasks [{task_id, run_manifests[], changed_files[]}],
measurement {passed|null, value, assert, trials, declared_trials, recorded_at} | null,
validation_state {VALIDATED|REGRESSED|VERIFICATION_PENDING|none},
freshness {stale_validation: bool, detail}
```

**Feature completeness map** (replaces the unverifiable "are requirements missing"
question with a machine check):

- `declared`: SRs in the feat `requirements:` list (and `contains` edges)
- `linked`: SRs with ≥1 satisfying task
- `register`: SRs that exist in `requirements/`
- findings: `declared_not_linked` (declared SR with no satisfying task),
  `declared_not_in_register` (declared SR with no register file),
  `task_satisfies_undeclared` (a task implementing a declared SR also satisfies
  an undeclared SR — a signal the feature's requirement list may be incomplete
  or the task misattributed).
  (an SR satisfies the feature via contains but is absent from the feat list).

**What this phase does NOT do:** guess that the feature *needs* a requirement about
topic X. Missing-requirement *suggestions* may be produced in Phase 5 as
`proposed_requirements` (human-gated), but they are never gated or counted as
coverage.

## 6. Phase 1 — import-graph overlap (machine, deterministic)

For every SR in scope whose binding uses the pytest trial source:

```
transitive_imports(binding.experiment) ∩ union(changed_files of satisfying tasks)
```

- Import extraction reuses the stdlib-`ast` approach of `factory.codeindex`
  (the tree-sitter consumer was shelved over the ABI mismatch; see the
  code-context worktree decision).
- `ok = True` when the intersection is non-empty. `ok = False` means: *the test
  that measures this requirement exercises no file any satisfying task changed* —
  the measurement cannot be demonstrating the implementation.
- Computed and recorded per SR with the exact sets (`reached_files`,
  `changed_files`, `overlap`), so the result is inspectable, not asserted.

**Boundary:** this is a necessary condition, not a proof. A test can import a module
and still assert nothing about the SR's claim. That is exactly what the Phase 2
subagent judges, with the overlap result handed to it as evidence.

## 7. Phase 2 — independent per-SR audit (subagent contract)

One subagent per SR, dispatched in parallel (reuses the dispatching pattern of the
factory run; the `subagent` tool is the transport). **Never the session that wrote
the code, and never the session running the workflow** — independence is the point.

**This is a semantic review, not a deterministic check.** The deterministic phases
(0, 1, 3, 4) assemble the evidence and enforce the gate; they never answer the
actual question — *does this code implement this requirement's claim?* That answer
is a semantic judgment: the subagent reads the statement, reads the real
implementation, reads the binding test, and reasons about whether the behavior the
statement requires is actually present in the code the task changed. Links
existing, metrics passing, and tests running are **inputs** to that judgment, never
substitutes for it.

**Judgment is grounded in injected context.** The subagent does not go find files.
The task packet *injects* the evidence, reusing the factory's context-packet
mechanism (`factory.orchestrator.context_packet`: `build_context_packet` /
`render_packet`, codeindex signatures): the SR statement and binding, the changed
files with verbatim code excerpts of the implementing paths, the binding test
source in full, the validation report, and the Phase 1 overlap result. Injected
context makes the judgment reproducible — two runs with the same packet should not
diverge because one subagent found a file the other missed — and it keeps the
subagent's whole context budget on reasoning, not navigation.

**The subagent follows a vendored skill.** `requirement-traceability-audit` (new,
vendored under `.pi/skills/`, per the 2026-07-30 validation design §8) — the
R2Code/TVR-style audit skill: judge `implemented` honestly, flag threshold-tight
passes (`margin`), separate "checked" from "assumed", emit `verify[]` items in the
`verification-before-completion` shape the REVIEW role already uses.

**Verdict schema (fixed, JSON):**

```
{
  "sr_id": "SR-001",
  "implemented": bool,      // the changed files implement the statement's claim
  "honest": bool,           // implemented AND the binding test exercises the
                            // claimed behavior AND import_overlap.ok
  "confidence": "high|medium|low",
  "margin": "0.90 vs >= 0.90 (tight)" | null,   // only when measured
  "reasoning": "why — what was checked, how the statement maps to code",
  "checked": ["test exercises preempt path in priority_filter.py", ...],
  "assumed": ["fixture frame stream represents the sim scenario", ...],
  "verify": [ { "item": "...", "file": "...", "line": N, "why": "..." } ]
}
```

- `reasoning`, `checked`, and `assumed` are **mandatory** (Invariant 4, and the
  requirement that the agent document why it did what it did): the human must be
  able to see the audit's own limits, not just its conclusions.
- `verify[]` items carry file/line anchors and a `why` — the same shape the
  existing REVIEW role emits, so review surfaces can reuse them.
- The subagent has **read-only** scope for this task: it reads the packet and the
  named files, it does not write, plan, or navigate the graph (Invariant 2).

## 8. Phase 3 — consolidation (machine)

Per-SR classification, in priority order:

| state | when | gate |
|---|---|---|
| `declined` | `trace_deferred` set on the SR | pass (recorded decision) |
| `pass` | linked + measured + `implemented=true` + `honest=true` | pass |
| `suspect` | pass but `import_overlap=false`, or stale binding/validation | warn |
| `unmeasured` | linked + `implemented=true`, no passing measurement | warn |
| `unlinked` | declared by feat, no satisfying task | **fail** |
| `unverified` | no subagent verdict (tool failure / not yet audited) | **fail** (or human deferral) |
| `implemented=false` / `honest=false` | subagent verdict | **fail** |

Feature rollup: declared vs linked vs measured vs audited counts, plus the
completeness findings from Phase 0.

## 9. Phase 4 — gate

`factory coverage gate <feat>` re-derives the report from disk (stateless, like
`trace check` and `requirements check` — no stored "we passed" flag). Gate outcome
is one of `pass | fail | degraded`:

- **`pass`** — every SR audited, no `implemented=false` / `honest=false`, no
  `unlinked`, warnings only.
- **`fail`** — at least one SR in `unlinked`, `implemented=false`, `honest=false`,
  or `unverified` for a non-tool cause.
- **`degraded`** — at least one SR is `unverified` **and** the cause is a recorded
  workflow/tool failure (`workflow_issues`). Degraded is visibly not-green: the
  report must list the unaudited SRs and the failure, and the summary must not
  read as covered. It does not force a human deferral prompt — the main session
  records the outcome, the human decides (re-run, defer, or accept), and the next
  run re-audits. This is the escape hatch for the known `subagent` tool flakiness:
  a failed dispatch must never look like an audited pass, but it must not brick
  the workflow on a transport hiccup.

Warns (never fails) on `suspect` and `unmeasured` — consistent with the register's
"staleness warns, it never hard-blocks".

## 10. Phase 5 — report to main session, and the human gate

### 10.1 Report artifact

`coverage-reviews/<feat-id>-<run-id>.json` (mirrors `validation-report.json`
style) + a rendered human summary. Structure:

```
{
  feature, run_id, generated_at, workflow_version,
  scope:   { declared_srs, linked_srs, register_srs, tasks: {...} },
  findings: { completeness: [...], per_sr: [ packet + overlap + verdict ],
              workflow_issues: [...], proposed_requirements: [...] },
  gate:    { result, failed: [], warned: [] },
  suggested_actions: [ { target, kind, why, skill } ]
}
```

- `workflow_issues` collects **workflow execution problems** (subagent tool
  failure, unreadable manifest, dangling reference that blocked resolution) so the
  workflow itself is improvable — the user-visible loop the audit depends on.
- `suggested_actions` are **not plans**: `{ target: "SR-001", kind:
  "reaffirm|rebind|relink|fix-test|audit-deeper|propose", why, skill:
  "binding-requirements|trace-fix|doctor" }`. The main session decides what to plan,
  with the human.
- Every finding in the report carries its reasoning + evidence (Invariant 4); the
  human summary is written so a reviewer needs no other window.

### 10.2 New-requirement disposition (the human gate)

When the audit surfaces a genuine feature gap (behavior ungoverned by any SR),
Phase 5 emits a `proposed_requirement` **finding**, never a write:

```
{ candidate_id, statement_draft (EARS), rationale,
  evidence_of_gap (what behavior is ungoverned, where), disposition: "pending" }
```

- The main session presents candidates to the human.
- **Accept** → materialize through the **doctor flow** (the human-gated authoring
  path): `doctor context` → `mint` → human read-through per requirement → the SR
  file is created in `[proposed]` state (no binding). The coverage workflow itself
  never calls `requirements new` or edits an SR.
- **Reject** → the doctor flow records the decision on the SR file
  (`trace_deferred: <reason>`), which the closure machinery already reads as
  `DECLINED` — the gap is decided, and the next audit run does not re-propose it.
- **Defer** → same mechanism with a reason; must state what must happen before it
  can be resolved.
- The gate **never counts proposals as coverage**: a feature whose only SRs are
  proposed is still uncovered and fails until a human decides.

### 10.3 Reaffirm / rebind are human-gated too

Phase 5 may suggest `reaffirm` (re-judge a stale binding) or `rebind`. These go to
the human, not to the subagents: re-legitimizing a stale artifact is a mini design
decision and must not be self-served by the audit.

## 11. Reuse inventory (confirmed against the codebase)

### Deterministic (Python) — reused as-is

| Capability | Source |
|---|---|
| Trace graph, edges, gaps | `factory.trace` (`model.py`, `graph.py`, `gaps.py`) |
| Requirement register, closure, staleness, `[proposed]`/`DECLINED` | `factory.requirements` (`register.py`, `closure.py`, `cli.py`) |
| Context injection for subagent packets (code signatures + excerpts) | `factory.orchestrator.context_packet` (`build_context_packet`, `render_packet`) |
| Run manifests (start/result commit, validation, reviews) | `factory.evidence.manifests` (`list_run_manifests`) |
| Task deliverables parsing | `factory.orchestrator.deliverables.parse_deliverables` |
| Implementing files per task | `git diff start_commit..result_commit` + per-deliverable `git log -1` (mirrors `pi-ext/.../review-diff.ts`) |
| Measurement provenance (`unit_pass_rate`, JUnit XML, refusal of unknown metrics) | `factory.validation.sim_harness` |
| Manifest schema validation | `factory.validation.schema_validator` + `schemas/*.json` |
| Staleness/freshness findings | `factory.evidence.reconcile`, `factory.freshness` |
| Goal-aware D5 status | `factory.trace.validation_status.requirement_validation` |
| V-cycle / validation / goal queries | `factory.system.queries` (`query_vcycle`, `query_validation`, `query_goal`) |
| Simulation run registry + goal evidence | `factory.simulation`, `factory.goals` |
| Import extraction (stdlib `ast`) | `factory.codeindex` precedent (tree-sitter shelved: ABI mismatch) |

### Agent surface (pi) — reused as-is

| Capability | Tool |
|---|---|
| Requirement → tasks → changed files chain | `eng_trace_requirement` |
| File → run → task → requirements walk | `system_reverse` |
| Task implementation story from manifests | `system_story`, `implementation_history` |
| Per-SR validation state / matrix | `validation_status`, `system_matrix` |
| Task reconciliation findings | `evidence_health` |
| Disposition + gate recording | `trace_link/exempt/defer`, `trace_check` |
| Per-SR independent audit transport | `subagent` (known-reliability caveat → `workflow_issues`) |
| Feature/goal/sim context | `eng_get_vcycle`, `eng_get_goal`, `eng_get_latest_simulation`, `eng_get_metric_history` |

### Skills — audit skills (Phase 2) and routing targets (Phase 5)

**Audit skills (define the semantic review itself):**
`requirement-traceability-audit` (new, vendored under `.pi/skills/`) +
`verification-before-completion` — the per-SR subagent follows these. The routing
skills below apply to *fixing* what the audit finds, and are never invoked by
subagents.

| Finding kind | Route to |
|---|---|
| New requirement accepted by human | `doctor` (mint/promote, human-gated) |
| Wrong/missing `satisfies` link | `trace-fix` (judge → `trace_link`/`trace_defer`) |
| Binding missing / test doesn't assert the claim | `binding-requirements` (iron-law recipe) |
| Parallel subagent dispatch | `dispatching-parallel-agents` / `subagent-driven-development` |
| Fix work landed | `finishing-a-development-branch` |

## 12. New pieces

- `src/factory/coverage/` — `scope.py` (Phase 0), `imports.py` (Phase 1),
  `audit.py` (verdict schema + Phase 3 consolidation), `gate.py` (Phase 4),
  `cli.py` (`factory coverage audit|report|gate`), `report.py`.
- `.pi/skills/coverage-review/SKILL.md` — the main-session orchestration skill:
  phase order, packet construction, subagent task packet, reasoning requirements,
  report format, human-gate handoff.
- `.pi/skills/requirement-traceability-audit/SKILL.md` — vendored per-SR audit
  skill: the semantic judgment protocol Phase 2 subagents follow (designed in the
  2026-07-30 validation design §8, never previously vendored).
- `coverage-reviews/` report artifact + rendered human summary.

## 13. Testing strategy

- **Python — scope.py:** feat file with declared/contains discrepancies; SR with
  multiple satisfying tasks and manifests; missing manifest → degraded, not crash.
- **Python — imports.py:** transitive import resolution on a synthetic tree
  (direct, nested, package-relative); overlap true/false fixtures; no-files case.
- **Python — audit.py:** classification table (each state from a fixture packet);
  verdict schema validation (missing `reasoning`/`checked` → rejected).
- **Python — gate.py:** fail/warn rules re-derived from disk; deferral clears
  `unverified`; proposal never counts as coverage.
- **Skill/report:** one golden run over a seeded fixture feature, asserting the
  human summary contains every finding's reasoning + evidence anchors.

## 14. Open items

1. Import extraction exact reuse point in `factory.codeindex` (verify the ast
   walker covers package-relative imports used by binding test modules).
2. ~~`unverified` gate behaviour~~ **Decided:** a third gate outcome, `degraded`,
   covers recorded tool failures (§9) — visible, not-green, no forced deferral
   prompt. Revisit if the `subagent` tool stabilizes and `degraded` becomes rare.
3. Report rendering surface: standalone markdown summary vs a tab in the SCC
   browser (Inc 6 substrate) — start with the summary file, browser tab later.
