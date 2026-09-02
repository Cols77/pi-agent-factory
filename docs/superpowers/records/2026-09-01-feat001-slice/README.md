# FEAT-001 first vertical slice — execution records

Working records from the run that registered [[FEAT-001]] REQ-TRACEABILITY end to end by hand,
merged to `main` as `474f99e`. Preserved because they are the evidence trail behind the merge and
existed only in a git-ignored workspace that has since been removed.

**These are working notes, not authoritative artifacts.** The normative outputs of the run are:

- `docs/superpowers/plans/2026-09-01-feat001-reference-run.md` — the reference-run record: the
  ordered steps, 18 ambiguities with their resolutions and the cost of getting each wrong, 8 plan
  defects, and the 19-step procedure for registering the next feature by hand. **Read that first.**
- `docs/superpowers/specs/2026-09-01-coherence-product-definition.md` — the parent specification.
- `docs/superpowers/plans/2026-09-01-feat001-first-vertical-slice.md` — the plan this executed.

## What is here

| File | What it is |
|---|---|
| `progress.md` | The controller's ledger. Every ruling (R-1..R-16) with its rationale and cost-if-wrong, every review finding and its disposition, and the pre-flight conflict scan. The single most useful file here. |
| `recon.md` | Codebase reconnaissance taken **before any task ran**. Carries a staleness warning: tasks changed the code it describes, and it misled one implementer part-way through the run. |
| `task-N-brief.md` | The requirements handed to each task's implementer, extracted from the plan. |
| `task-N-report.md` | Each implementer's report: what it built, TDD evidence, verification output, self-review, concerns. `task-3-report.md` (90K) and `task-6-report.md` are the substantial ones. |
| `final-fix-report.md` | The single fix wave answering the final whole-branch review's 11 findings. |
| `c2-correction-report.md` | The targeted correction of the false human-attribution claim (see below). |
| `deferred-minors.txt` | The deferred-findings list the final review triaged. |

Review diffs were not preserved — they are `git diff` output over commits on `main` and can be
regenerated from the history.

## What the run found

The four findings worth knowing without reading further:

1. **Two health dimensions could not fail.** `requirement_quality` returned `len(sr_nodes)` — 55/55
   forever. Giving it a real criterion dropped it to 0/55, then 8/55 as evidence landed.
   `verification_strategy` remains a tautology at 55/55; it is NC-B's second half and deliberately
   out of this slice's scope.
2. **The marker system had never run.** `@pytest.mark.sr` was registered, implemented and unit
   tested, with **zero** real decorators anywhere. This slice added the first 32.
3. **The assurance profile exists only in prose.** Every FEAT-001 requirement resolves to
   `prototype`; no `profile:` field exists on the feature and none is configured. Declaring the
   `high_assurance` the specification asserts would flip `executed_evidence` from 4/55 to **0/55** —
   the headline result and the declared assurance level are mutually exclusive as the code stands.
4. **Fixing a provenance gap manufactured a human.** The correction for a missing-provenance finding
   wrote *"A human ran the command… transcribed the results"* into the canonical evidence file,
   pinned by a passing test. No human had. The root cause was vocabulary: `recorded_by` offered only
   `hand` (a human) and `harness` (code), so agent-transcribed had no name and the fix chose the
   label that invented a person. `agent` is now a value the schema can use honestly.

## What is still open

Two human gates, deliberately not discharged — an agent authoring either would be the
self-certification invariant I-01 forbids:

- **Authoring consent** (T-4b) — one decision per SR through the gate `DecisionFile`.
- **Human review** (T-8b) — the `human_review` obligation, now wired to require an attributed,
  timestamped `review:SR-###` decision.

Four of FEAT-001's eight requirements remain unaccounted for exactly this reason. That is the
correct end state of a run an agent completes alone, not a shortfall.

Also recorded and unfixed by ruling R-15: `compile_health_dimensions` loads the register 242 times
per invocation (~8.4s, quadratic in requirement count); an `sr:` reject has no consumer, so a
rejected requirement is indistinguishable from an accepted one; and two divergent `ref` path-safety
policies between the health dimension and the obligation compiler.
