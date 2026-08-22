# Coherence: progressive assurance, obligations and lifecycle traceability

**Status:** design
**Date:** 2026-08-22
**Amends:** `2026-08-18-coherence-toolset-design.md` (§11 Increments, §3 Decisions) and
`2026-08-20-coherence-programme-execution-map.md`.
**Input:** `pi-coherence-progressive-assurance-planning-guide.md` (external planning guide, not
committed to this repo — its decisions are absorbed here where accepted, and this document
records the two places this repo's actual state overrode it).
**Supersedes:** nothing. Adds progressive assurance, compiled obligations, typed lifecycle
relationships, a nonconformance record type, a multidimensional health vector, and CI as an
obligation consumer.

## 1. Problem

Seven gaps, found while planning a session of work on `fix/kb-0004-run-recovery`:

1. `factory.validation.pipeline.validate_task_requirements` treats a requirement-validation
   **error** (harness missing, execution error) on a task's own `satisfies`/`justification` SR
   identically to a setup gap on an unrelated SR — both are non-blocking warnings. A task can
   report done while the one thing it claims to validate never ran.
2. Nothing links a task to the defect it corrects. `T-031` fixes the exact symptom filed as
   GitHub issue #1 (missing Catchup orientation causing an intermittent gate), but the task
   file has no field that can express "this corrects that," and the trace graph has no way to
   query it.
3. `substrate.schemas.context_manifest.schema.json` requires a `checks` array but not a
   non-empty one, and nothing cross-checks that a manifest's `task_id` matches the task it was
   actually gathered for. A context-gatherer can emit zero proof obligations and still pass
   schema validation.
4. No factory feature has been walked, as one exercise, through requirement → design →
   implementation → test → evidence using the coherence spine itself. Everything is proven
   piecemeal by unit tests over the machinery; nothing proves the machinery composes.
5. `factory.system.health.query_health` reports one scalar, `health.percent`, alongside
   separately-computed `vcycle_findings` and `freshness_findings` lists that the browser must
   reassemble itself. There is no single per-item, per-dimension picture.
6. No CI workflow exists (`.github/workflows` is empty). Every gate — unit, sim, integration,
   lint, typecheck, the extension suite — runs only when `/factory-run` or a developer runs it
   locally. Nothing verifies a change independently of the orchestrator.
7. A requirement, once bound, has no explicit human-approved baseline, and nothing marks a
   downstream link suspect when its upstream changes. `coherence.trace`'s existing staleness
   checks (`sr_stale` gaps) detect drift but do not distinguish "this was never reviewed" from
   "this was reviewed and is now suspect because something it depends on changed."

The external planning guide referenced above addresses all seven under one frame —
**progressive assurance**: obligations scale with a project's actual maturity and consequence
of failure, not with a fixed process. This document adopts that frame, adapts its increment
integration map to this repo's actual (not documented) landed state, and resolves the two
questions the guide left open: what CI runs, and how "dogfood one feature end-to-end" is
scoped.

## 2. Landed state (verified against `main`, not handoff docs)

Per the guide's own instruction (§2 item 1: "recompute, don't trust copied state"), the working
tree was checked directly:

| Increment | Package evidence | Status |
|---|---|---|
| 0, 1, 1B, 1C | `src/substrate/*` | shipped |
| 2 | `src/coherence/{trace,register}` | shipped |
| 3 | `src/coherence/{navigate,presentation,goals,simulation}` | shipped |
| 4 | `src/coherence/{audit,measurement}` | not built |
| 5 | `src/coherence/{status,focus}` | not built |
| 6 | `src/coherence/{gate,inbox}` | not built |
| 7, 8 | — | not built |

This matters because the guide's integration map (its §7.2) is written to preserve existing
increment numbers by amending each increment's plan in place. That is safe for an increment
that has not been built yet — its plan can still change. It is not safe for an increment
already merged: amending increment 0/1/2/3 "in place" would mean rewriting the record of what
was actually implemented and shipped, which this repo's plan files do not do (compare how the
agentic-io amendment was layered on top of the original toolset design rather than rewritten
into it). Decision D15 below resolves this.

## 3. Decisions (continuing the numbering in the toolset design)

| # | Decision | Rationale |
|---|---|---|
| D15 | Amend an increment's plan in place only if it has not yet been built; carry forward any delta assigned to an already-shipped increment as a new, separately-numbered increment | Preserves the historical record of what 0/1/1B/1C/2/3 actually shipped; matches how the agentic-io amendment (§15 of the toolset design) was layered rather than rewritten |
| D16 | Progressive assurance is scoped to the thin vertical slice (guide §11) first: `prototype` and `high_assurance` presets only, three obligation kinds only | `exploration`/`product`/`high_assurance`'s remaining obligation kinds are declared in the schema but not compiled or tested until a real use case needs them — matches the toolset design's own YAGNI instinct (§2 non-goals) |
| D17 | `NC-*` nonconformance records mirror `FR-*` failure records: their own directory, loader and schema, referenced by id, never a `trace.model.NodeKind` | `FR-*` already proves this pattern works — health surfaces `fr:<id>` findings and justification/relationship edges can cite an id without the trace graph needing to load or walk nonconformance content as a node |
| D18 | CI enforcement is itself a compiled obligation (`kind: ci_verification`, `requiredness: blocking` under every default preset), not a hand-maintained step list | A later increment that compiles a new blocking obligation extends what CI enforces without a workflow-file edit; keeps "coherence, status, gates and CI agree" true by construction rather than by discipline |
| D19 | The dogfood exercise (item 4 of the originating request) and the guide's §11 thin vertical slice are the same deliverable | The slice already walks a corrective task and a requirement-delivery task through justification, verification, staleness/suspect state, rerun and both projections — a second, separate "dogfood" pass would duplicate it for no new proof |

## 4. Progressive assurance model

Adopted from the guide with no material change (see guide §3–§5 for the full rationale):

- **Minimal invariant kernel** (guide §3.3, seven rules) is always active, never profile-
  disableable. Rule 1 — "an execution error, missing executable or invalid result cannot
  become pass" — is precisely the fix for gap 1 above, generalized: `validate_task_requirements`
  must distinguish `error`/`invalid`/`interrupted`/`unknown` from `passed`/`failed`, and any of
  the first four on a task's own justified SR blocks.
- **Profile vocabulary**: seven dimensions (`maturity`, `consequence`, `reversibility`,
  `volatility`, `verification_cost`, `exposure`, `collaboration`), each a fixed enum, compiled
  with explicit scope precedence (artifact/requirement > feature/bundle > path/component >
  project default), equal-specificity conflicts rejected rather than silently ordered.
- **Compiled `Obligation`**: `{id, scope_ref, kind, requiredness, reason, source_policy, state,
  resolve_cmd}`. `requiredness` is one of `not_applicable | advisory | required | blocking`.
  Status, health, inbox, navigator and gates consume this contract; none reinterpret the
  profile independently (this is the same discipline as D6 — inbox computed from disk, never a
  second source of truth — applied to obligations).
- **Typed task justification** replaces the bare `satisfies` list: `satisfies | corrects |
  mitigates | implements | maintains | explores`, each naming an id. Existing `satisfies:`
  frontmatter is read as shorthand for `justification: [{satisfies: ...}]` — no migration
  required, no existing task file needs editing.
- **Typed lifecycle relationships**: `derives/decomposes/refines` (intent), `allocates/
  satisfies/implements` (design), `verifies/validates/mitigates/evidences` (assurance),
  `corrects/impacts/supersedes` (change). An edge naming an unsupported kind is rejected at
  load, not stored as free-form text (guide §9.3).
- **Suspect relationships**: a governed edge carries source/target content fingerprints and a
  validity state `proposed | valid | suspect | invalid | waived`. Deterministic code may
  downgrade `valid → suspect` when an endpoint's fingerprint changes; only a policy-authorized
  operation restores `valid`. This extends the existing freshness/gap machinery — it is not a
  second dependency graph (guide §5.4; matches `authoritative_gate`'s existing "route to inbox
  or owning writer, never rewrite automatically" resolution class from the toolset design §15).
- **Baselines** are optional, `product`/`high_assurance`-only semantic snapshots (a Git-state
  reference over accepted needs/requirements/decisions/interfaces/risks/assumptions). Not
  required to run an experiment or ship a prototype (guide §5.5).

## 5. `NC-*` nonconformance records and the T-031 → issue #1 link

New record type at `docs/nonconformances/NC-*.md`, structurally parallel to `docs/failures/
FR-*.md`:

```yaml
id: NC-0001
title: Catchup tab has no orientation metadata
external_ref: gh-issue:1
detected_by: gate-flake-investigation
status: corrected
corrected_by: T-031
```

- Identity is the `id` in frontmatter, never the filename (same discipline as ADR/FR).
- `external_ref` is a free-form but pattern-checked string (`gh-issue:<n>` for now; the schema
  leaves room for other trackers without committing to one). It is a citation, not a live sync
  — coherence never calls the GitHub API. A stale external reference is a content-freshness
  question like any other, not a special case.
- A malformed record degrades to `scope_errors`, exactly like `FR-*` — one bad file never hides
  the rest.
- `T-031`'s frontmatter changes from `satisfies: []` to:

  ```yaml
  justification:
    - corrects: NC-0001
  ```

  This is the concrete, queryable answer to "link T-031 to issue #1": `trace next`/`register
  check` can now show T-031 as justified (not dangling), and `coherence explain NC-0001` (or
  the health `NONCONFORMANCE_OPEN`/`NONCONFORMANCE_CLOSED` finding) can show `T-031` and
  `gh-issue:1` from one record.

## 6. Health as a vector

`query_health` stops returning `health.percent` as the headline number. In its place, per guide
§6.4, eleven independently-applicable dimensions, each with its own satisfied/expected/exempt
counts and its own denominator built **only** from obligations compiled `required` or
`blocking` for that scope (`not_applicable` obligations are shown, never counted as satisfied):

1. requirement quality/source
2. decomposition and architecture allocation
3. implementation trace
4. verification strategy
5. executed evidence
6. validation against scenarios
7. evidence freshness
8. suspect relationships
9. nonconformance/change closure
10. deferrals/waivers
11. required human review

Dimensions 3, 7 and (partially) 8 are not new computation — they already exist as
`vcycle_findings` and `freshness_health` findings in `factory/system/health.py`; this
increment reclassifies existing finding codes into their owning dimension rather than
re-deriving them, and adds the remaining dimensions (1, 2, 4–6, 9–11) as new obligation-backed
queries. `coherence status`'s "one line" summary names the worst dimension, not an average —
averaging five greens and one red back into a number is exactly the scalar this item retires.

## 7. CI

`.github/workflows/ci.yml`, triggered on push and pull request, independent of any agent
dispatch:

- Reads the compiled obligation set for the repo's own profile (bootstrapped `prototype` in
  Increment 2B, since the profile compiler does not exist before then) and runs every check
  backing a `blocking` obligation.
- Under the default preset this resolves, on day one, to exactly what `/factory-run`'s gates
  already run: `pytest -m unit`, `pytest -m sim`, `pytest tests/integration/ -m integration`,
  `ruff check .`, `pyright`, `npm test --prefix pi-ext/factory-watch`, plus `coherence trace
  check` / `coherence register check`.
- No new step list to maintain by hand: a later increment that compiles a new `blocking`
  obligation (e.g. Increment 6's gate-requiredness work, or a `high_assurance`-scoped feature)
  extends what CI enforces automatically (D18).
- CI failure semantics follow the invariant kernel: an obligation whose check errors or cannot
  run is `blocking`-failing, never silently skipped.

## 8. The thin vertical slice (dogfood)

Exactly guide §11, unchanged, using `T-031` as the corrective task:

1. Add `prototype` and `high_assurance` presets (schema only — no other preset compiled yet).
2. Compile three obligation kinds: task justification, executable verification result, human
   review for one high-criticality requirement.
3. Apply a `high_assurance` override to one seeded feature; the repository default stays
   `prototype`.
4. Run `T-031` (`corrects: NC-0001`) and one requirement-delivery task through the full spine.
5. Make an implementation change that invalidates a verification fingerprint.
6. Confirm the resulting `suspect`/stale state renders in `coherence status`, the navigator and
   the inbox — three surfaces, one observation.
7. Rerun evidence per policy (`repeatable_policy` bounds) and restore closure.
8. Render both a compact agent projection and a human explanation from the same observation;
   confirm they agree on outcome.

Acceptance mirrors guide §11 exactly: the prototype feature incurs no high-assurance ceremony;
the high-assurance feature cannot close with missing/errored verification; `T-031` traces
through `corrects`, not a fabricated `satisfies`; every obligation explains itself and its
cost; RTK presence/absence changes token volume only, never outcome.

## 9. Explicitly deferred

Unchanged from the guide (§7.3): full SysML compatibility, ReqIF/OSLC import-export,
certification templates, a GSN/SACM assurance-case editor, traceability to every code symbol,
a background policy daemon, a graph database. Also deferred here specifically: compiling
`exploration`/`product` presets (schema-declared, untested until a real use case appears);
a `CR-*` artifact kind separate from `NC-*` (guide's `supersedes`/`impacts` edges plus the
existing gate protocol cover a requirement/spec change without a new record type).

## 10. Increment integration map

Supersedes the guide's §7.2 table for this repo, applying D15 (already-shipped increments are
never reopened; their delta becomes a new increment instead):

| Increment | Status before this doc | Disposition |
|---|---|---|
| 0, 1, 1B, 1C, 2, 3 | shipped | **untouched** |
| 2B *(new)* | — | evidence-correctness fix (§1 gap 1); `substrate` policy/obligation compiler; mandatory context-manifest checks + identity (§1 gap 3); typed justification/relationships; `NC-*` records; T-031 ↔ issue #1 link (§5) |
| 2C *(new)* | — | CI as an obligation consumer (§7) |
| 3B *(new)* | — | obligation-aware navigator/presentation/goals/simulation views, effective-profile + "why required" projections; guide's original increment-3 row, carried forward because 3 already shipped |
| 4 | not built | amend in place: profile-aware verification-contract validation, policy-bound auto-rerun (guide §7.2 row 4, unchanged) |
| 5 | not built | amend in place: health vector (§6), profile init UX, `coherence explain-obligation` |
| 6 | not built | amend in place: requiredness in gate protocol, suspect-edge review, expiring exceptions, milestone baselines |
| 6B *(new)* | — | thin vertical slice / dogfood (§8) |
| 7, 8 | not built | amend in place: guide §7.2 rows 7 and 8, unchanged |

### Scheduling

```
0 -> 1 -> 1B -> 1C -> 2 -> 3   (shipped)
                            |
                            v
                           2B -----> 2C   (CI; no further edges out -- extended in place
                            |               by every later increment that compiles a new
                            v               blocking obligation, never re-planned)
                           3B
                            |
                            v
                            4
                            |
                            v
                            5
                            |
                            v
                            6
                           / \
                         6B   7, 8   (6B needs 2B, 4, 5, 6 -- not 7 or 8, so 6B and 7/8
                                      are mutually cuttable, the same property the
                                      original execution map already grants 7 and 8)
```

2C needs only 2B's Obligation contract and then runs standing, gaining coverage as later
increments compile new blocking obligations — it has no downstream dependents in this map. 3B
needs 2B's Obligation contract plus already-shipped Increment 3, and gates 4 because 4's
verification-contract work consumes 3B's obligation-aware canonical paths. 6B needs 2B, 4, 5
and 6 but not 7 or 8, so it and increments 7/8 are mutually cuttable without stranding each
other, the same property the original execution map already grants increments 6–8.

## 11. Testing

Adds, on top of the toolset design's existing testing section (§12): profile-schema fixtures
(valid presets, invalid enums, ambiguous scope conflicts); policy-compiler determinism and
precedence tests; obligation applicability/requiredness tests; legacy-`satisfies` compatibility
tests; the ten minimum test families listed in the guide's §10 verbatim. `NC-*` gets the same
malformed-record-degrades-not-crashes test `FR-*` already has. CI's own workflow is tested by
running it against a seeded repo state in a dry-run job before it gates real PRs.

## 12. Risks

- **Guide/repo drift.** The guide was written against handoff docs, not `main`; §2 above is
  the corrected record. Future amendments to this design must re-verify landed state the same
  way, not trust this document's table as it ages.
- **Obligation model becomes a second policy engine next to freshness.** Mitigated the same way
  the original freshness design was: obligations compile from and route through the existing
  freshness/gap/inbox machinery (D-inherited from the toolset design's D14), never a parallel
  graph.
- **CI drifts from `/factory-run`'s gates.** Mitigated by D18: CI reads the compiled obligation
  set rather than maintaining its own list, so the two cannot silently diverge.
