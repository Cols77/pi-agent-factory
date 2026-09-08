# T-038 — Holistic Integration Review of FEAT-017 (PLANNING-BOOTSTRAP)

Reviewed at `C:/coding/pi-agent-factory-wt/feat17-closure-bookkeeping` (worktree of `main`; only task-frontmatter/register-index bookkeeping commits — `228a6eb`, `ac27006`, `c1c4c31` — differ from `main`; no source code differs). Fresh, independent reviewer, no prior session context, dispatched 2026-09-07 as part of the FEAT-017 closure bookkeeping plan's Task 5.

## Verification evidence (this session, before dispatch)

- `uv run pytest tests/unit/coherence/test_planning_*.py -q -o addopts=''` → **430 passed, 0 failed, 8 skipped**
- `uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_*.py` → **clean, zero findings**
- `uv run pyright src/coherence/planning` → **0 errors, 0 warnings, 0 informations**
- `uv run pytest tests/unit/substrate/test_verification_record_schema.py -q -o addopts=''` → 0 tests collected. `tests/unit/substrate/test_verification_record_schema.py` and `src/substrate/schemas/verification_record.schema.json` **do not exist** in this checkout — confirmed by direct `ls`. This artifact only ever existed in a rejected candidate worktree from an earlier session (see this plan's Task 0 audit) and was never merged. Stated as fact, not a failure.

## A. What actually exists and is reachable

**Reachable from the real CLI** (`src/coherence/cli.py:75` maps `"plan"` → `coherence.planning.cli:main`):

| Command | Backing code |
|---|---|
| `check` | `src/coherence/planning/cli.py:475`, `check.py:487` |
| `bootstrap [--decompose]` | `cli.py:499`, `bootstrap.py:33`, `substrate/ledger/plans.py:144` |
| `review` | `cli.py:483`, `run.py:124` |
| `suggest` | `cli.py:488`, `run.py:686` |
| `handoff` | `cli.py:493`, `handoff.py:86` |
| `start/resume/status/append/resolve/finalize` | `cli.py:508`, `session.py:164–343` |
| `legal-actions` | `cli.py:508`, `session.py:206` |

**Present but unreachable from any entrypoint** (library/test-only — confirmed by repo-wide grep for callers under `src/`):

- `PlanningWorkflow` — the three-checkpoint semantic reviewer (`workflow.py:71`). `bootstrap_planning` accepts `workflow: PlanningWorkflow | None = None` (`bootstrap.py:38`) and only runs stages when it is non-`None` (`bootstrap.py:112`), but `cli.py:240` calls `bootstrap_planning(root, planning_input, decompose=args.decompose)` — never passing one.
- `PlanningRunner` — the 10-stage hash-bound state machine with gate attestations (`runner.py:880`, `PlanningStage` at `runner.py:40–50`). No `src/` caller.
- `execute_planning_workflow` / `execute_parent_stage` (`run.py:40`, `run.py:70`). No `src/` caller.
- `validate_sr_consent` — the exact-consent-phrase validator (`gates.py:177`, phrase at `gates.py:22`). No `src/` caller; only tests.

This split is the single most important finding: the strongest FEAT-017 machinery (staged runner, gate attestations, semantic checkpoints, consent phrase) is **built and tested but not composed into the shipped pipeline**.

## B. Per-SR analysis

### SR-043 — Planning bootstrap pipeline
A named, host-neutral pipeline exists (`coherence plan`) and genuinely reuses substrate machinery (`bootstrap.py:12` imports `substrate.ledger.plans.run`; `check.py:16` imports `parse_plan_tasks`). Intent capture (`session.py`), task decomposition (`bootstrap.py:87`), derived SR/feature/bundle closure checking (`check.py:406–484`), consent gating (`cli.py:323`), and a separately-started handoff (`handoff.py:135` `starts_automatically: False`; `cli.py:391`) are all present and wired.

Two clauses are not composed into the named pipeline: **semantic review** (`PlanningWorkflow` unreachable, see §A) and **authority-spec / implementation-plan authoring**, which `guided_pipeline.py:9–12` explicitly declares to be model work that "no backend command writes … and none can." Sequencing of those stages lives only as prose in `.claude/commands/coherence-plan.md` §6–§7.

### SR-044 — SR human-approval consent gate
The negative half is enforced unusually well. `ReviewDecision` cannot be constructed by a caller (`run.py:163–164` raises on `__init__`; `__setattr__`/`__delattr__` raise at `run.py:166–170`), and `build_downstream_suggestion` refuses anything that is not a capability minted by `read_review_decision` (`run.py:693–694`). A clean report alone is never consent — `requirement_consent_status` is checked independently (`cli.py:323–331`, `run.py:717–719`), the reviewer field must be literally `"human"` (`run.py:403`, `gates.py:168`), and the consent record's `requirements` must equal the exact owned set (`gates.py:172`). Planning writes no requirement/bundle files; it emits `requirement_consent: required` and `health_resolution_registration: delegated` as next actions instead (`bootstrap.py:94–104`).

Two real gaps:
1. **`coherence plan handoff` never checks consent.** `_handoff` (`cli.py:360–392`) validates the report and re-hashes artifacts but calls neither `requirement_consent_status` nor `validate_requirement_consent`. Only `suggest` gates on consent. A host can run `bootstrap → handoff` and obtain a persisted hash-bound `handoff.json` with zero consent record.
2. The SR body's **"explicit consent phrase … after the derivation review is clean"** is implemented (`gates.py:177–221`, phrase at `gates.py:22`) but has no caller. The path that *is* enforced (`validate_requirement_consent`, `gates.py:93`) uses the legacy schema-1 record with no phrase.

### SR-051 — Planning/implementation gate boundary
The prohibition holds. Nothing under `src/coherence/planning/` executes an implementation validation gate: `bootstrap_planning` only runs `check_planning_input` plus optional decomposition (`bootstrap.py:92`, `bootstrap.py:87`); the only `subprocess.run` calls are the adapters re-invoking `coherence plan` itself (`adapter_backend.py:58`, `legal_actions_adapter.py:139`) with `shell=False`. Every downstream projection is inert: `run.py:745`, `handoff.py:135`, `session.py:221`, and `validate_handoff` hard-rejects any payload where `starts_automatically is not False` (`handoff.py:194`).

One wording caveat, not a violation: `handoff.md` is written with the literal line `Current status: validated` (`handoff.py:169`) and the summary renders `Gates: {"status": "pass"}` from the default at `handoff.py:122`/`handoff.py:133`. These are planning-side claims, not implementation evidence, but they read stronger than the evidence behind them (see SR-055).

### SR-052 — Durable progressive intent capture
Solid. Append-only journal at `.factory/planning/<run>/capture/events.jsonl` (`session.py:76–77`), with strict contiguity/ordering enforcement (`session.py:120–122`) and run-id binding (`session.py:112`). Provenance is carried per answer (`id`/`question`/`text`/`source` at `session.py:287–288`). The initial request is preserved verbatim as event 1 (`session.py:176`). Resume rebuilds the projection purely from the journal (`session.py:183–189`), and materialization failure preserves the last good snapshot rather than truncating it (`session.py:88–93`). Review decisions, consent, and execution state live in distinct files (`review-decision.json`, `requirement-consent.json`, `sr-consent.json`) — never inside the intent artifact. Tests pin all of this (`test_planning_session.py:22,41,55,67,105`).

Two caveats worth recording, neither fatal to the statement:
- The `open_questions` brief field is only populated by `question_deferred` events (`intent.py:355`), and no CLI/adapter verb emits that kind — `_EVENT_KINDS` includes it (`intent.py:19`) but `session.py` only appends `capture_started`, `answer_captured`, `challenge_raised`, `challenge_resolved`, `capture_status`. Unresolved *questions* are in practice preserved as unresolved *challenges*, which are journaled, projected, and surfaced (`cli.py:458–464`) — so the SR's substance holds via a different field than the schema advertises.
- The materialized snapshot path is project-global (`.intent/intent.json`, `session.py:85`), not per-run, so two concurrent runs overwrite each other's snapshot. The per-run journal is unaffected and `resume` re-materializes, so single-run interruption/resume is safe. **(Addressed separately in this session's second plan, `2026-09-07-legal-actions-lifecycle-projection.md` Task 2.)**

### SR-053 — Cross-artifact coherence review
A blocking cross-artifact review exists and is genuinely blocking before handoff: `check_planning_input` sets `ok = not findings` (`check.py:551`), and `build_handoff` raises `HandoffError("only a clean planning report can be handed off")` unless `report.ok` (`handoff.py:96–97`), reached from `cli.py:375`.

Coverage against the SR's enumerated list:

| Required | Status |
|---|---|
| captured intent | ✅ `check.py:513` (`_valid_intent`) |
| specification | ✅ `check.py:514–518` |
| system requirements | ✅ `check.py:456–484` (canonical fields + authority-anchor resolution) |
| feature and bundle registration | ✅ `check.py:425–455` (exact-closure membership) |
| implementation plan | ✅ `check.py:519–526` (`spec_ref` resolution) |
| generated tasks | ✅ `check.py:285–373` (`PLAN_TASK_PARITY`, `TASK_METADATA_INVALID`) |
| source **and validation artifact relations** | ❌ nothing in `check.py` reads `implemented_by`/`verified_by` or any trace relation |
| selected **workflow/gate proposal** | ❌ no workflow or gate contract is inspected anywhere in `check.py` |

Finding taxonomy: missing (`INTENT_UNCOVERED`, `check.py:539`), duplicate (`check.py:322`, `check.py:271`), overstated (`SPEC_UNSUPPORTED_CLAIM`, `check.py:545`), contradictory (`PLAN_TASK_PARITY`, `check.py:358`) are covered with cited subjects. **Dangling** and **weak** link classes have no counterpart.

### SR-054 — Plan-task trace-maintenance obligation
The SR has two halves. The second half is delivered by the shared SR-050 machinery this SR explicitly consumes: `factory.preflight.checks.run_completion_preflight` compiles the `relation_maintenance` obligation and raises a `BLOCKING` `relation_uncovered` issue when it is `open` (`checks.py:172–192`), so completion is blocked until declarations reconcile.

The **first half is not enforced anywhere**. Generated task files are written with frontmatter `id, title, status, dod, source_plan, source_task` and no affected-SR field at all (`substrate/ledger/plans.py:121–129`). The planning checker's per-task field validation lists exactly `("id", "title", "status", "source_plan", "source_task")` — no `satisfies` (`check.py:346`). And the relation-maintenance obligation self-disables when the field is absent: `if not satisfies: return Obligation(..., state="not_applicable")` (`compiler.py:229–234`). So a FEAT-017 task that changes production code, carries no `satisfies`, and passes both the planning gate and completion preflight is exactly the case the SR is written to prevent. The only statement of the obligation is prose in `.claude/commands/coherence-plan.md` §7 ("each generated task must carry its affected SRs (SR-054)") — model instruction, not enforcement.

### SR-055 — Versioned planning gate pack enforcement
`src/coherence/planning/gates.py` (225 lines) contains exactly two public functions — `validate_requirement_consent` (`gates.py:93`) and `validate_sr_consent` (`gates.py:177`) — and its `__all__` confirms this (`gates.py:224`). There is **no gate pack compiler**: nothing anywhere declares stage, requiredness, resolver, dependencies, expected evidence, or failure behavior for planning gates. A repo-wide grep for `gate_pack|planning-gates|requiredness` inside `src/coherence/planning/` returns only `policy_version: str = "planning-gates-v1"` as a per-attestation default string (`runner.py:140`, `runner.py:237`, `runner.py:831`) — a version label on an individual attestation, not a compiled versioned pack.

The block clause is also inverted in practice: `cli.py:375` calls `build_handoff(root, report, workflow=args.workflow)` with no `gate_summary`, so the persisted handoff records `gate_summary: {"status": "pass"}` unconditionally (`handoff.py:133`, default also applied to the rendered summary at `handoff.py:122`). The handoff therefore asserts a gate pass with no gate having been compiled, executed, or evidenced — the precise failure mode SR-055 exists to block.

Two documents overclaim this as done, and should be corrected:
- `.pi/skills/writing-plans/SKILL.md:177` — "`coherence.planning.gates` compiles the planning gate pack ([[SR-055]])". This is an active skill instructing hosts; it is false.
- `docs/superpowers/plans/2026-09-04-commit-claim-traceability-plan.md:129` — "`gates.py` (planning gate pack, [[SR-055]])".

### SR-065 — Guided planning workflow entrypoint
What exists: `guided_entrypoint.py` exposes six capture verbs (`SESSION_VERBS`, line 28), `guided_pipeline.py` four compile/handoff verbs (`PIPELINE_VERBS`, line 33), both routed through a shared fail-closed backend call path (`adapter_backend.py:47`, argv-only, `shell=False`, trusted exit codes `(0, 1)` at line 34). Interruption survival is real and tested: `status_session` recomputes the projection from the journal and rejects a disagreeing `state.json` (`session.py:196–203`), driven end-to-end through the adapter in `test_planning_guided.py:628`. The non-executing boundary is pinned (`test_planning_guided.py:609`).

Where it falls short of the literal statement:
1. **"one host-guided planning entrypoint"** — there are two Python entrypoints (`python -m coherence.planning.guided_entrypoint`, `python -m coherence.planning.guided_pipeline`) plus `legal_actions_adapter`, sequenced by a third artifact, the prose command file `.claude/commands/coherence-plan.md`.
2. **"rather than requiring manual subcommand sequencing"** — this is what the implementation actually does. `.claude/commands/coherence-plan.md` §2–§9 is a hand-written ten-step ordering the model must follow; no code derives "what is legal next" for the capture, spec, plan, or review stages.
3. **"renders only actions legal under current hash-bound Coherence run state and gate attestations"** — `legal_actions_session` is the only legal-action projection, and it consults session state plus `handoff.json` validation only; it reads **no gate attestations** (`session.py:206–257`). It emits at most `["inspect-handoff", "revalidate-handoff"]` (`session.py:256`), while the declared registry advertises five ids including `select-downstream-workflow`, `create-downstream-session`, and `resolve-blocking-input` (`session.py:24–30`) that are never emitted. Before a handoff exists it returns `blocked: SESSION_NOT_READY` (`session.py:236`) — i.e. for the entire planning run up to handoff, no legal-action projection is produced at all. **(Addressed separately in this session's second plan, `2026-09-07-legal-actions-lifecycle-projection.md` Task 3 — the capture/author-review legal-actions fix directly targets this exact gap.)**

The blocking/fail-closed and interruption-survival clauses are met; the "one entrypoint" and "no manual sequencing" clauses are not.

## 1. Per-SR verdicts

- **SR-043: PARTIAL** — pipeline composes intent/decomposition/closure/consent/handoff correctly; semantic review (`PlanningWorkflow`) is optional and never supplied (`bootstrap.py:38`, `cli.py:240`); spec/plan authoring is prose-only.
- **SR-044: PARTIAL** — consent enforcement on `suggest` is strong and unforgeable; `handoff` performs zero consent check (`cli.py:360–392`); the SR's required consent-phrase path (`gates.py:177`) has no caller.
- **SR-051: SATISFIED** — no implementation gate execution anywhere in the module; every downstream projection is inert and validated as non-auto-starting.
- **SR-052: SATISFIED** — append-only, provenance-bearing, contiguity-enforced journal; resume rebuilds purely from it; failure preserves last-good snapshot. Minor: `open_questions` field unused (challenges cover the substance); snapshot path is global not per-run (separately fixed).
- **SR-053: PARTIAL** — blocking cross-artifact review covers 6 of 8 enumerated relation classes; validation-artifact relations and workflow/gate proposal are not inspected; no "weak"/"dangling" finding class.
- **SR-054: PARTIAL** — completion-blocking half delivered via SR-050's `relation_maintenance` obligation; the obligation to *declare* affected SRs on generated tasks is unenforced and self-disables when absent (`compiler.py:229–234`).
- **SR-055: NOT SATISFIED** — no gate pack compiler exists; `gates.py` is two consent validators; handoff unconditionally records `gate_summary: {"status": "pass"}` with no gate ever executed.
- **SR-065: PARTIAL** — start/resume/interruption-survival/fail-closed blocking are real and tested; "one entrypoint" is actually three artifacts sequenced by prose; legal-actions reads no gate attestations and is blocked for the entire run until handoff exists (separately fixed this session).

## 2. T-038 DoD assessment

- **"verified CLI help/output"** — ✅ `coherence plan --help` and per-subcommand `--help` verified directly against the parser (`cli.py:475–526`); coherent and working. Two cosmetic defects: no `help=` text on any argument; `--json` is accepted everywhere but read nowhere (output is unconditionally JSON).
- **"test/lint/type reports"** — ✅ 430 passed/0 failed/8 skipped; ruff clean; pyright clean (cited above). The two verification-record artifacts independently confirmed absent as fact.
- **"reviewer-confirmed statement of deferred human browsing/visualization"** — ✅ Explicit and machine-pinned: authority spec (`...bootstrap-design.md:274–275`), dossier's `deferred-browser` token (`docs/features/FEAT-017.md`), and `test_planning_trace_contract.py:161–162,195` all assert it. No code claims an interactive browsing UI exists.

## 3. Additional task-status drift found

- **`tasks/T-037-...md` is `status: todo` despite being satisfied.** All of its DoD items check out against the live repo: `satisfies`/`source_plan` links present, FEAT-017 membership correct (`bundles/FEAT-017.json` = feature + all 8 owned SRs), `test_planning_trace_contract.py:31` proves the trace-contract assertion its DoD requires, and `requirements/index.json` now carries `SR-065` (via this plan's Task 3, commit `ac27006`).
- **Documentation drift (not a task file):** `.pi/skills/writing-plans/SKILL.md:177` and `docs/superpowers/plans/2026-09-04-commit-claim-traceability-plan.md:129` both assert `coherence.planning.gates` compiles the SR-055 planning gate pack — it does not (see SR-055 above). The skill file is the more urgent of the two since it actively instructs hosts.
- T-032 through T-036's `status: done` was independently re-verified against live source and confirmed correct.

## 4. Overall verdict

**T-038's own three-bullet DoD is MET** — CLI surface verified, test/lint/type evidence cited and the absent verification-record artifacts confirmed as fact rather than failure, and the browsing/visualization deferral is explicit and test-pinned.

This is **not** a statement that FEAT-017 is complete. Three of eight owned SRs are PARTIAL, one (SR-055) is NOT SATISFIED, and the strongest machinery in the package — `PlanningRunner`, `PlanningWorkflow`, and the exact-phrase `validate_sr_consent` — is built, tested, and entirely unreachable from any shipped entrypoint. Per this plan's own Task 5 rule, T-038 stays `status: todo` with these findings recorded on the task file rather than being marked done — see `## Findings pending resolution` on `tasks/T-038-holistic-integration-review-and-available-gate-deployment.md`.

Highest-value follow-ups, in order: compile and enforce a real planning gate pack instead of defaulting `gate_summary` to `pass` (SR-055); require and check an affected-SR declaration on generated tasks (SR-054); gate `coherence plan handoff` on consent the way `suggest` already is (SR-044); correct the two documents that assert the gate pack already exists; and correct T-037's stale `status: todo`. This review grants no SR consent, no adoption, and marks nothing as merged or released.
