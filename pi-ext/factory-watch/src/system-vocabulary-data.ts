// Generated from the Python source of truth -- copied verbatim, not summarised.
// Source: src/factory/system/vocabulary.py (build_vocabulary) and
// src/factory/system/remediation.py (build_remediation).
// Task 13 adds a drift test that fails if this diverges from the Python output.
// To regenerate:
//   uv run python -m factory.system vocabulary --json
//   uv run python -m factory.system remediation --json
// and paste each JSON payload in verbatim below.

export const VOCABULARY_DATA = {
  "version": 1,
  "terms": {
    "recorded": {
      "term": "recorded",
      "group": "claim-kind",
      "label": "recorded",
      "gloss": "copied straight out of a file, nothing computed",
      "definition": "The claim text was copied verbatim out of an artifact file (a requirement, task, ADR, or bundle declaration). Nothing was computed, aggregated, or written by a model to produce it.",
      "siblings": [
        "derived",
        "synthesized",
        "missing"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/models.py"
      ]
    },
    "derived": {
      "term": "derived",
      "group": "claim-kind",
      "label": "derived",
      "gloss": "computed by rolling up several recorded facts",
      "definition": "The claim is a computation over one or more recorded facts -- for example a bundle's implementation summary (run count, latest outcome) rolled up from several evidence-manifest runs, or a guide section's bullet list rolled up from several claims, some of which may themselves be missing. Never a language-model output; always a deterministic aggregation.",
      "siblings": [
        "recorded",
        "synthesized",
        "missing"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/guide.py"
      ]
    },
    "synthesized": {
      "term": "synthesized",
      "group": "claim-kind",
      "label": "synthesized",
      "gloss": "scaffold prose wrapped around a verified verbatim quote",
      "definition": "Fixed scaffolding text plus one or more verbatim spans copied character-for-character from a cited source file. No language model is invoked and no text is reworded: `guide.py`'s `_verbatim_span` independently re-reads the cited file and confirms the exact substring is present before this kind is ever assigned -- it only fires when every fact backing the section is fresh; otherwise the section collapses to `derived` or `recorded` bullets instead.",
      "siblings": [
        "recorded",
        "derived",
        "missing"
      ],
      "computed_by": [
        "src/factory/system/guide.py"
      ]
    },
    "missing": {
      "term": "missing",
      "group": "claim-kind",
      "label": "missing",
      "gloss": "no artifact exists to back this claim",
      "definition": "There is no recorded basis for the claim at all -- a bundle member that does not resolve to a real file, a requirement with no validation report entry, or a scope that no longer exists. By the SS3.2 coupling rule, `kind == missing` if and only if `freshness.state == n/a`; the two always travel together.",
      "siblings": [
        "recorded",
        "derived",
        "synthesized"
      ],
      "computed_by": [
        "src/factory/system/_claims.py",
        "src/factory/system/models.py"
      ]
    },
    "fresh": {
      "term": "fresh",
      "group": "freshness",
      "label": "fresh",
      "gloss": "cited inputs still match what is recorded now",
      "definition": "Every dependency the claim was built from still matches its recorded current state -- a requirement's own declaration file is always fresh the moment it resolves; a validation result is fresh only while the report entry has not gone stale against a later edit to the requirement's statement or binding.",
      "siblings": [
        "stale",
        "degraded",
        "n/a"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "src/factory/system/_claims.py"
      ]
    },
    "stale": {
      "term": "stale",
      "group": "freshness",
      "label": "stale",
      "gloss": "the requirement changed since this result was recorded",
      "definition": "The cited evidence exists and was once valid, but the requirement's statement or binding changed after that result was recorded -- `trace.validation_status.SrStatus.stale` -- so the old outcome can no longer be trusted as current. Set for both a brief's validation claim and the matrix row for the same requirement.",
      "siblings": [
        "fresh",
        "degraded",
        "n/a"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/queries.py"
      ]
    },
    "degraded": {
      "term": "degraded",
      "group": "freshness",
      "label": "degraded",
      "gloss": "a cited file exists but could not read",
      "definition": "Something recorded should back the claim, but the specific file could not be read or parsed -- a corrupt validation report, an evidence manifest whose sha256 came back null, or a rollup with at least one missing contributor. Distinct from `missing`: a degraded claim still has a citation, it just could not be verified.",
      "siblings": [
        "fresh",
        "stale",
        "n/a"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/guide.py"
      ]
    },
    "n/a": {
      "term": "n/a",
      "group": "freshness",
      "label": "not applicable",
      "gloss": "no recorded basis to judge freshness at all",
      "definition": "There is nothing recorded to be fresh or stale against -- a proposed requirement with no binding yet, or any claim of kind `missing`. By the SS3.2 coupling rule this state only ever pairs with claim kind `missing`; it is never used for a claim that resolved to real content.",
      "siblings": [
        "fresh",
        "stale",
        "degraded"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "src/factory/system/queries.py"
      ]
    },
    "passed": {
      "term": "passed",
      "group": "matrix-status",
      "label": "passed",
      "gloss": "the validation report recorded this requirement passing",
      "definition": "`validation/validation-report.json` recorded an entry for this requirement with `passed: true` and no error. The requirement may still show freshness `stale` if its statement or binding changed afterward -- `passed` on its own only means the last recorded run succeeded, not that it is current.",
      "siblings": [
        "failed",
        "error",
        "blocked",
        "never-run",
        "unknown"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/queries.py"
      ]
    },
    "failed": {
      "term": "failed",
      "group": "matrix-status",
      "label": "failed",
      "gloss": "the validation report recorded this requirement failing",
      "definition": "`validation/validation-report.json` recorded an entry for this requirement with `passed: false`. For a bundle's run-level verdict, any requirement recorded `passed: false` makes the whole run `failed`, taking priority over any stale result (`queries._validation_verdict`).",
      "siblings": [
        "passed",
        "error",
        "blocked",
        "never-run",
        "unknown"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/queries.py"
      ]
    },
    "error": {
      "term": "error",
      "group": "matrix-status",
      "label": "error",
      "gloss": "the validation attempt itself could not complete",
      "definition": "The recorded report entry carries an `error` field: the validation harness itself could not run to a pass/fail verdict (a crashed experiment, a missing metric), as distinct from `failed`, where validation ran and the assertion did not hold.",
      "siblings": [
        "passed",
        "failed",
        "blocked",
        "never-run",
        "unknown"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/queries.py"
      ]
    },
    "blocked": {
      "term": "blocked",
      "group": "matrix-status",
      "label": "blocked",
      "gloss": "the requirement has no binding to validate against",
      "definition": "The requirement is `proposed` -- its register entry has no binding yet -- so there is nothing recorded to run a validation against. `queries._sr_matrix_row` sets this before ever consulting the validation report; freshness is `n/a`, never `fresh`, since there is no basis to be current about.",
      "siblings": [
        "passed",
        "failed",
        "error",
        "never-run",
        "unknown"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "never-run": {
      "term": "never-run",
      "group": "matrix-status",
      "label": "never run",
      "gloss": "bound and validatable, but no report entry yet",
      "definition": "The requirement has a decided binding, but `validation/validation-report.json` carries no entry for it -- validation has simply not been run yet, distinct from `blocked` (no binding to run) and `error` (ran and could not complete). Note the hyphen: the underlying validation-status enum spells this same state `never_validated` with an underscore -- `queries._sr_matrix_row`'s `status_map` translates one into the other; they are the same recorded absence, spelled two ways for two different consumers.",
      "siblings": [
        "passed",
        "failed",
        "error",
        "blocked",
        "unknown"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/queries.py"
      ]
    },
    "unknown": {
      "term": "unknown",
      "group": "matrix-status",
      "label": "unknown",
      "gloss": "outcome cannot be determined at all",
      "definition": "Two distinct \"cannot determine\" cases share this value. As a matrix status, it means either the referenced SR does not exist (`_sr_missing_matrix_row`) or the validation report file exists but is corrupt/unparseable (`_sr_matrix_row`'s `report_corrupt` branch) -- deliberately not `never-run`, which would assert a recorded fact the evidence does not support. As a timeline actor (design SS7.4, `TimelineActor.UNKNOWN`), it is a reserved closed-vocabulary value for an actor string that does not match a recognized case; `query_timeline` in this repo never actually emits it today -- it always emits `not-recorded` instead, because the review-decision artifact this repo reads carries no actor field at all.",
      "siblings": [
        "passed",
        "failed",
        "error",
        "blocked",
        "never-run"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/models.py"
      ]
    },
    "never_validated": {
      "term": "never_validated",
      "group": "validation-state",
      "label": "never validated",
      "gloss": "no report entry recorded; underscore spelling of never-run",
      "definition": "`trace.validation_status.SrState`'s own spelling (with an underscore) of the state the matrix renders as `never-run` (with a hyphen). The literal is not where you would expect: `validation_status._entry_state`, the actual report parser, only ever returns `error`/`passed`/`failed` -- an SR absent from the report is simply absent from `load_validation`'s returned dict, never assigned this string there. The literal `\"never_validated\"` is written directly by `system/feature.py`'s `_verification` (a separate, ad hoc summary, used when a status lookup came back `None`), and is independently, defensively checked by `trace/gaps.py`'s `sr_unvalidated` branch (`status is None or status.state == \"never_validated\"`) against a value `load_validation` itself never actually produces.",
      "siblings": [
        "passed",
        "failed",
        "error"
      ],
      "computed_by": [
        "src/factory/trace/validation_status.py",
        "src/factory/system/feature.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "weak": {
      "term": "weak",
      "group": "readiness",
      "label": "weak",
      "gloss": "fallback: not every SR is bound and covered",
      "definition": "The bundle's member SRs fail the `medium` bar -- at least one member SR has no decided binding, or has no non-exempt task satisfying it. Also the readiness of any bundle that declares no SR members at all. Computed by `health.bundle_readiness`; the browser never computes this itself.",
      "siblings": [
        "medium",
        "strong"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "medium": {
      "term": "medium",
      "group": "readiness",
      "label": "medium",
      "gloss": "every SR is bound and covered by task",
      "definition": "Every member SR has a decided binding (`bound`) and at least one non-exempt task declaring `satisfies` for it (`covered`) -- but not necessarily `validated`. `bound` (`health.py:83`: `req.binding is not None and not proposed`) is strictly stronger than `current` (`health.py:91`: `req.binding is not None`), so every member SR of a medium bundle is already current too; only `strong` additionally requires a fresh passing validation.",
      "siblings": [
        "weak",
        "strong"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "strong": {
      "term": "strong",
      "group": "readiness",
      "label": "strong",
      "gloss": "every SR is covered, current, and passing validation",
      "definition": "Every member SR is `covered` (a satisfying task), `current` (a decided binding, not a proposed placeholder), and `validated` (the validation report records a fresh pass for it). The highest of the three grades; `health.bundle_readiness` checks this condition first.",
      "siblings": [
        "weak",
        "medium"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "sr_total": {
      "term": "sr_total",
      "group": "readiness-count",
      "label": "SR total",
      "gloss": "how many SRs this bundle declares as members",
      "definition": "The count of `sr:` refs the bundle declares as members -- `len(flags)` in `health.bundle_readiness`. This is a per-bundle denominator, scoped to one bundle's declared membership; it is not the repo-wide SR count the `SR satisfied`/`SR validated` health classes use, which counts every SR node in the whole trace graph regardless of bundle membership.",
      "siblings": [
        "bound",
        "covered",
        "current",
        "deferred",
        "validated"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "bound": {
      "term": "bound",
      "group": "readiness-count",
      "label": "bound",
      "gloss": "has a decided binding, not flagged proposed",
      "definition": "How many of the bundle's member SRs have a decided binding in the requirements register *and* are not flagged `sr_proposed` in the trace graph -- `health._sr_flags`'s `bound` predicate. An SR can have a register binding yet still be excluded here if the trace independently marks it proposed.",
      "siblings": [
        "sr_total",
        "covered",
        "current",
        "deferred",
        "validated"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "covered": {
      "term": "covered",
      "group": "readiness-count",
      "label": "covered",
      "gloss": "at least one non-exempt task satisfies this SR",
      "definition": "How many of the bundle's member SRs have no `sr_unsatisfied` gap recorded against them -- i.e. at least one task declares `satisfies` for the SR (`health._sr_flags`'s `covered` predicate). The predicate's source also excludes an exempt `sr_unsatisfied` gap, but that branch is unreachable in practice: `gaps._disposition_of` forbids `trace_exempt` for `sr`/`br` node kinds, so an SR's own gaps can never actually be `exempt`.",
      "siblings": [
        "sr_total",
        "bound",
        "current",
        "deferred",
        "validated"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "current": {
      "term": "current",
      "group": "readiness-count",
      "label": "current",
      "gloss": "has a decided binding, not a placeholder",
      "definition": "How many of the bundle's member SRs have a decided binding in the requirements register -- i.e. are not an auto-declined placeholder still waiting on a measurement decision. Unlike `bound`, this predicate checks the register alone and does not additionally consult the trace graph's `sr_proposed` gap.",
      "siblings": [
        "sr_total",
        "bound",
        "covered",
        "deferred",
        "validated"
      ],
      "computed_by": [
        "src/factory/system/health.py"
      ]
    },
    "deferred": {
      "term": "deferred",
      "group": "readiness-count",
      "label": "deferred",
      "gloss": "postponed by a human note or auto-deferred proposal",
      "definition": "This word means two different, non-interchangeable counts. As a readiness count: how many of the bundle's member SRs carry at least one gap whose disposition is `deferred` (`health._sr_flags`'s `deferred` predicate, checked over ALL of that SR's gaps). Two independent triggers set that disposition (`gaps._disposition_of`, `gaps.find_gaps`): a human recorded `trace_deferred: <reason>` on the node's frontmatter, OR the SR is `proposed` (no binding yet) -- `find_gaps` force-sets `disposition=\"deferred\"` on every `sr_proposed` gap regardless of whether any reason was recorded (`trace/gaps.py:96`), so a proposed SR with no human note still counts here. As a health COUNTER (`trace.health.compute_health`), the same word names a repo-wide tally of gaps with disposition `deferred` that EXCLUDES `sr_proposed` gaps specifically -- `compute_health`'s loop `continue`s on `sr_proposed` before ever checking disposition (`trace/health.py:69-77`), routing a proposed SR's automatic deferral into the repo-wide `proposed` counter instead. The two `deferred` numbers can disagree even for the same repo state.",
      "siblings": [
        "sr_total",
        "bound",
        "covered",
        "current",
        "validated",
        "dangling",
        "proposed"
      ],
      "computed_by": [
        "src/factory/system/health.py",
        "src/factory/trace/gaps.py",
        "src/factory/trace/health.py"
      ]
    },
    "validated": {
      "term": "validated",
      "group": "readiness-count",
      "label": "validated",
      "gloss": "validation report shows a fresh pass for SR",
      "definition": "As a readiness count: how many of the bundle's member SRs have a validation-report entry with `state == passed` and `stale == False` -- `health._validation_passing`. As a timeline action (design SS7.4, `TimelineAction.VALIDATED`), the same word names a decision-timeline event recording that a requirement was validated; `query_timeline` in this repo does not currently emit that action (its only real source, review decisions, maps to `approved`/`rejected`/`not-recorded`).",
      "siblings": [
        "sr_total",
        "bound",
        "covered",
        "current",
        "deferred"
      ],
      "computed_by": [
        "src/factory/system/health.py",
        "src/factory/trace/validation_status.py"
      ]
    },
    "task->plan": {
      "term": "task->plan",
      "group": "health-class",
      "label": "Tasks linked to a plan",
      "gloss": "share of tasks with a resolving source_plan",
      "definition": "Denominator: every `task` node in the trace graph, one slot each. Satisfied: the task declares a `source_plan` edge at all -- `task_no_plan` is the only gap kind that unfills this slot. A `source_plan` edge whose target does not resolve to a real node (`task_plan_missing`) does NOT unfill the slot: `compute_health`'s gap loop counts it straight into the separate `dangling` counter and `continue`s before ever reaching `_SLOT_OF_GAP` (`trace/health.py:65-68`), which has no `task_plan_missing` key at all -- so a task with a broken `source_plan` link is reported as `dangling`, not as an unfilled `task->plan` slot, and counts toward this class's percentage as satisfied. A task marked `trace_exempt` removes its slot from the denominator instead of counting it unfilled.",
      "siblings": [
        "task->SR",
        "plan->spec",
        "SR satisfied",
        "SR validated"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "task->SR": {
      "term": "task->SR",
      "group": "health-class",
      "label": "Tasks linked to a requirement",
      "gloss": "share of tasks that declare a satisfies edge",
      "definition": "Denominator: every `task` node in the trace graph, one slot each (the same task also has a `task->plan` slot; they are counted independently). Satisfied: the task declares at least one `satisfies` edge (`task_no_sr` is the gap when it declares none). Exempt tasks remove their slot from the denominator.",
      "siblings": [
        "task->plan",
        "plan->spec",
        "SR satisfied",
        "SR validated"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "plan->spec": {
      "term": "plan->spec",
      "group": "health-class",
      "label": "Plans linked to a spec",
      "gloss": "share of plans that cite a spec_ref",
      "definition": "Denominator: every `plan` node in the trace graph, one slot each. Satisfied: the plan declares at least one `spec_ref` edge (`plan_no_spec` is the gap when it declares none). Exempt plans remove their slot from the denominator rather than counting as unfilled.",
      "siblings": [
        "task->plan",
        "task->SR",
        "SR satisfied",
        "SR validated"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "SR satisfied": {
      "term": "SR satisfied",
      "group": "health-class",
      "label": "Requirements with a satisfying task",
      "gloss": "share of all SRs with a satisfying task",
      "definition": "Denominator: every `sr` node in the trace graph -- the full repo-wide count, including proposed SRs with no decided binding yet, which is why this denominator (e.g. 181) is much larger than `SR validated`'s (e.g. 43): proposed SRs keep their `SR satisfied` slot (a requirement with no task is a gap whether or not it is bound) but lose their `SR validated` slot entirely (there is nothing to validate yet). Satisfied: at least one task declares `satisfies` for the SR (`sr_unsatisfied` is the gap when none does).",
      "siblings": [
        "task->plan",
        "task->SR",
        "plan->spec",
        "SR validated"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "SR validated": {
      "term": "SR validated",
      "group": "health-class",
      "label": "Requirements with a passing validation",
      "gloss": "share of non-proposed SRs with a fresh pass",
      "definition": "Denominator: every `sr` node in the trace graph MINUS every SR flagged `sr_proposed` (no decided binding yet) -- `compute_health` subtracts one expected slot per proposed SR, which is the entire reason this denominator (e.g. 43) is far smaller than `SR satisfied`'s (e.g. 181): a requirement cannot be validated before someone has decided what to measure. Satisfied: the requirement has a validation-report entry with state `passed` that is not stale (`sr_unvalidatable`, `sr_unvalidated`, and `sr_stale` are the gaps that leave this slot unfilled -- `compute_health` also excludes an exempt `sr_stale`, but that branch is unreachable in practice since SR gaps can never be `exempt`).",
      "siblings": [
        "task->plan",
        "task->SR",
        "plan->spec",
        "SR satisfied"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "dangling": {
      "term": "dangling",
      "group": "health-counter",
      "label": "dangling",
      "gloss": "an edge points at a missing node",
      "definition": "A count of structural defects, not unfilled slots: a `source_plan`/`upstream` edge whose target does not resolve to any real node (`dangling_upstream`, `task_plan_missing`), or a V-cycle edge (`parent_of`/`verified_by`/`demonstrates`/`evaluates`/`contains`/`illustrates`) whose source or target is missing (`dangling_reference`). This is a health COUNTER, not a trace disposition -- it never appears as a gap's `disposition` field, only as this repo-wide tally.",
      "siblings": [
        "proposed"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/gaps.py"
      ]
    },
    "proposed": {
      "term": "proposed",
      "group": "health-counter",
      "label": "proposed",
      "gloss": "an SR with no decided binding yet",
      "definition": "A count of SRs whose frontmatter carries no `binding` key -- nobody has yet decided what measurement would satisfy them (`trace.model._id_node`'s `proposed` field). Reported on its own line rather than folded into `deferred`, because counting it as an unfilled validation slot would punish recording a real, honest state. Like `dangling`, this is a health COUNTER, not a trace disposition.",
      "siblings": [
        "dangling"
      ],
      "computed_by": [
        "src/factory/trace/health.py",
        "src/factory/trace/model.py"
      ]
    },
    "human": {
      "term": "human",
      "group": "timeline-actor",
      "label": "human",
      "gloss": "reserved actor value: a human decision-maker",
      "definition": "A reserved value in the `TimelineActor` closed vocabulary (design SS7.4) for a decision event whose recorded artifact names a human as the actor. `query_timeline`'s only real source today -- a run manifest's `reviews` array -- carries no actor field at all, so this repo's timeline never actually emits `human`; every real event's actor is `not-recorded`.",
      "siblings": [
        "dev",
        "review",
        "validation",
        "orchestrator",
        "unknown",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "dev": {
      "term": "dev",
      "group": "timeline-actor",
      "label": "dev",
      "gloss": "reserved actor value: the orchestrator's dev step",
      "definition": "A reserved value in the `TimelineActor` closed vocabulary (design SS7.4) for a decision event attributed to the orchestrator's automated dev step. Not currently emitted by `query_timeline` for the same reason as `human`: the recorded review artifact carries no actor field.",
      "siblings": [
        "human",
        "review",
        "validation",
        "orchestrator",
        "unknown",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "review": {
      "term": "review",
      "group": "timeline-actor",
      "label": "review",
      "gloss": "reserved value: a review step or artifact",
      "definition": "As a timeline actor, a reserved value (design SS7.4) for a decision attributed to a review step; not currently emitted (see `human`). As a citation kind (`CitationKind.REVIEW`), a reserved value for citing a review artifact directly; this repo's own review-decision citations are built with kind `decision` instead (`queries._iter_decision_records`), pointing at the owning evidence manifest's `reviews[i]` entry -- `review` is declared in the schema but not constructed by any query in this repo today.",
      "siblings": [
        "human",
        "dev",
        "validation",
        "orchestrator",
        "unknown",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "orchestrator": {
      "term": "orchestrator",
      "group": "timeline-actor",
      "label": "orchestrator",
      "gloss": "the pipeline controller itself, per the closed vocabulary",
      "definition": "A reserved value in the `TimelineActor` closed vocabulary (design SS7.4) for a decision event attributed to `factory.orchestrator`'s own control flow rather than a person or a specific node. Not currently emitted by `query_timeline` for the same reason as `human`.",
      "siblings": [
        "human",
        "dev",
        "review",
        "validation",
        "unknown",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "not-recorded": {
      "term": "not-recorded",
      "group": "timeline-actor",
      "label": "not recorded",
      "gloss": "the source artifact records no such field",
      "definition": "The honest recorded absence, not a guess -- and it does double duty across two groups. As a timeline actor, the run manifest's `reviews[i]` record this repo reads has no field for an actor identity at all, so `queries._decision_event_from_record` always sets `actor = TimelineActor.NOT_RECORDED` for every real timeline event -- every review-decision actor in this repo actually carries this value today. As a timeline action (`TimelineAction.NOT_RECORDED`), the same spelling is set when `reviews[i].decision` is anything other than `\"approve\"`/`\"reject\"` -- an unrecognized or absent decision value, not merely \"nobody decided yet\".",
      "siblings": [
        "human",
        "dev",
        "review",
        "validation",
        "orchestrator",
        "unknown"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "approved": {
      "term": "approved",
      "group": "timeline-action",
      "label": "approved",
      "gloss": "a run manifest recorded decision: \"approve\"",
      "definition": "The owning evidence manifest's `reviews[i].decision` field is exactly the string `\"approve\"` -- `queries._DECISION_ACTION_MAP`. This is one of the two actions this repo's timeline actually emits today, from the same recorded `reviews` array documented under `citation-kind`'s `decision` entry.",
      "siblings": [
        "rejected",
        "validated",
        "repaired",
        "published",
        "stopped",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "rejected": {
      "term": "rejected",
      "group": "timeline-action",
      "label": "rejected",
      "gloss": "a run manifest recorded decision: \"reject\"",
      "definition": "The owning evidence manifest's `reviews[i].decision` field is exactly the string `\"reject\"` -- `queries._DECISION_ACTION_MAP`. The other action this repo's timeline actually emits today.",
      "siblings": [
        "approved",
        "validated",
        "repaired",
        "published",
        "stopped",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "repaired": {
      "term": "repaired",
      "group": "timeline-action",
      "label": "repaired",
      "gloss": "reserved action value: an automated fix",
      "definition": "A reserved value in the `TimelineAction` closed vocabulary (design SS7.4) for an event recording that something was repaired. Not currently emitted by `query_timeline`: its only recorded source (`reviews[i].decision`) only ever carries `approve` or `reject`, mapped to `approved`/`rejected`; anything else maps to `not-recorded`.",
      "siblings": [
        "approved",
        "rejected",
        "validated",
        "published",
        "stopped",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "published": {
      "term": "published",
      "group": "timeline-action",
      "label": "published",
      "gloss": "reserved action value: a publish step",
      "definition": "A reserved value in the `TimelineAction` closed vocabulary (design SS7.4) for an event recording a publish action. Not currently emitted by `query_timeline` for the same reason as `repaired`.",
      "siblings": [
        "approved",
        "rejected",
        "validated",
        "repaired",
        "stopped",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "stopped": {
      "term": "stopped",
      "group": "timeline-action",
      "label": "stopped",
      "gloss": "reserved action value: a stop event",
      "definition": "A reserved value in the `TimelineAction` closed vocabulary (design SS7.4) for an event recording that a run or pipeline was stopped. Not currently emitted by `query_timeline` for the same reason as `repaired`.",
      "siblings": [
        "approved",
        "rejected",
        "validated",
        "repaired",
        "published",
        "not-recorded"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "manifest": {
      "term": "manifest",
      "group": "citation-kind",
      "label": "evidence manifest",
      "gloss": "cites a durable evidence/runs/<run_id>.json file",
      "definition": "As a citation kind, the cited path is a durable per-run evidence manifest, `evidence/runs/<run_id>.json` -- always a file, never a directory (`_claims.manifest_path`). As a scope kind for a timeline/citation subject (`kind: \"run\" | \"manifest\"`), it identifies the subject as the manifest record itself rather than the run's outcome.",
      "siblings": [
        "task",
        "requirement",
        "review",
        "decision",
        "trace",
        "bundle",
        "session"
      ],
      "computed_by": [
        "src/factory/system/_claims.py",
        "src/factory/system/story.py"
      ]
    },
    "task": {
      "term": "task",
      "group": "citation-kind",
      "label": "task",
      "gloss": "cites the task's own T-*.md file",
      "definition": "This word does three jobs. As a citation kind, the cited path is the task's own file under `tasks/` -- the same file `factory.orchestrator.ledger` loads task status from; used for both a bundle's `task:` member claim and its companion implementation-status claim. As a scope/subject kind (`SystemScopeRef.kind`/`TimelineSubjectRef.kind`, system-cli.ts:106), it identifies a subject as a task rather than an SR, run, or manifest -- e.g. `query_story`'s own scope. As a `stops_at` value (`system.reverse`), `stops_at: \"task\"` means the walked run's own `task_id` did not resolve in the ledger at all -- the earliest possible stop in the file -> run -> task -> requirements chain, one step before the `satisfies` stop.",
      "siblings": [
        "manifest",
        "requirement",
        "validation",
        "review",
        "decision",
        "trace",
        "bundle",
        "session",
        "sr",
        "run",
        "satisfies",
        "chain-complete"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/reverse.py",
        "src/factory/system/models.py"
      ]
    },
    "validation": {
      "term": "validation",
      "group": "citation-kind",
      "label": "validation",
      "gloss": "cites the validation-report.json file itself",
      "definition": "As a citation kind (`CitationKind.VALIDATION`), the cited path is `validation/validation-report.json` itself -- built by `queries._validation_report_citation` and attached to every SR's brief validation claim (`queries.py:734`); covered directly by `test_models.py`. This is an ACTIVELY constructed kind, unlike most of this table's reserved values. As a timeline actor (`TimelineActor.VALIDATION`, design SS7.4), the same spelling is a reserved closed-vocabulary value for a decision attributed to the validation pipeline running automatically -- `query_timeline` never emits it; see `not-recorded` for what it emits instead.",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "review",
        "decision",
        "trace",
        "bundle",
        "session"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/system/models.py"
      ]
    },
    "requirement": {
      "term": "requirement",
      "group": "citation-kind",
      "label": "requirement",
      "gloss": "cites the SR/BR's own file under requirements/",
      "definition": "The cited path is the requirement's own `SR-*.md` (or `BR-*.md`) file under `requirements/`, loaded through `factory.requirements.register`. Used for a requirement's statement, upstream, binding, and validation claims alike.",
      "siblings": [
        "manifest",
        "task",
        "review",
        "decision",
        "trace",
        "bundle",
        "session"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "decision": {
      "term": "decision",
      "group": "citation-kind",
      "label": "decision",
      "gloss": "cites an ADR file or a review entry",
      "definition": "The cited path is either an ADR document under `docs/adr/`, or an evidence manifest with an `anchor` naming the specific `reviews[i]` array entry it points at -- the array documented under `_iter_decision_records`, the sole source of signed review decisions. This is the kind actually used for every review-decision timeline event in this repo (not `review`).",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "review",
        "trace",
        "bundle",
        "session",
        "failure",
        "goal"
      ],
      "computed_by": [
        "src/factory/system/queries.py"
      ]
    },
    "failure": {
      "term": "failure",
      "group": "citation-kind",
      "label": "failure record",
      "gloss": "cites a failure record under docs/failures/",
      "definition": "The cited path is a failure record, `docs/failures/FR-*.md`, loaded through `factory.memory.failure_record` -- the durable artifact that captures reproduction ref -> root cause -> rejected hypotheses -> fix -> regression guard. Introduced by Inc 8's durable-memory projection: a decision entry cites its ADR, a failure record and each of its rejected hypotheses cite the FR file itself (`factory.memory.durable`).",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "validation",
        "review",
        "decision",
        "trace",
        "bundle",
        "session",
        "goal"
      ],
      "computed_by": [
        "src/factory/memory/durable.py"
      ]
    },
    "goal": {
      "term": "goal",
      "group": "citation-kind",
      "label": "goal",
      "gloss": "cites a goal file under goals/",
      "definition": "The cited path is a goal file under `goals/`, loaded through `factory.goals.registry` -- the measurable engineering contract (brief §5.3). Used by the durable-memory projection's open-goal entries (`factory.memory.durable`) so an open goal's entry carries a citation to the goal file that declares it.",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "validation",
        "review",
        "decision",
        "trace",
        "bundle",
        "session",
        "failure"
      ],
      "computed_by": [
        "src/factory/memory/durable.py"
      ]
    },
    "trace": {
      "term": "trace",
      "group": "citation-kind",
      "label": "trace",
      "gloss": "cites a spec, plan, feature, metric, or goal",
      "definition": "The cited path is one of the trace graph's other document kinds -- a spec or plan (`_resolve_spec_or_plan_member`) or a feat/metric/goal node (`_resolve_trace_member`) -- resolved through `trace.model.load_nodes`, the same loader `factory.trace` itself uses, never a second parser.",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "review",
        "decision",
        "bundle",
        "session"
      ],
      "computed_by": [
        "src/factory/system/queries.py",
        "src/factory/trace/model.py"
      ]
    },
    "bundle": {
      "term": "bundle",
      "group": "citation-kind",
      "label": "bundle",
      "gloss": "cites the bundle's own declaration file under bundles/",
      "definition": "As a citation kind, the cited path is the bundle's own declaration file under `bundles/` (`bundles.py`'s loader). As a scope kind (`SystemScopeKind`, system-cli.ts:9), `\"bundle\"` is the `kind` value for `--scope bundle:<id>`. As the noun (design SS3.3), a bundle is a declared feature-scope grouping of spec/plan/task/SR/feat/metric/goal members with a label and exact member refs -- no status or rationale of its own; readiness and health are always computed over its members.",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "review",
        "decision",
        "trace",
        "session",
        "sr"
      ],
      "computed_by": [
        "src/factory/system/bundles.py",
        "src/factory/system/models.py"
      ]
    },
    "session": {
      "term": "session",
      "group": "citation-kind",
      "label": "session record",
      "gloss": "cites a fallback sessions/*.session.json when no manifest",
      "definition": "As a citation kind, the cited path is a `sessions/*.session.json` record -- thinner than an evidence manifest by nature: no commit range, no changed files, no patch, because none was recorded. As a run source (`StoryRun.source`), `\"session\"` means this particular run was reconstructed from that fallback record because no durable evidence manifest exists for it; `\"manifest\"` is the other, preferred source.",
      "siblings": [
        "manifest",
        "task",
        "requirement",
        "review",
        "decision",
        "trace",
        "bundle"
      ],
      "computed_by": [
        "src/factory/system/sessions.py",
        "src/factory/system/story.py"
      ]
    },
    "run": {
      "term": "run",
      "group": "scope-kind",
      "label": "run",
      "gloss": "a timeline/citation subject naming one evidence run",
      "definition": "One legal value of a timeline or citation subject's `kind` (`\"task\" | \"sr\" | \"run\" | \"manifest\"`, design SS7.4) -- identifies the subject as a specific evidence run (a `run_id`), as distinct from `manifest`, which names the file that recorded it.",
      "siblings": [
        "manifest",
        "bundle",
        "sr",
        "task"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "sr": {
      "term": "sr",
      "group": "scope-kind",
      "label": "SR (scope/subject kind)",
      "gloss": "lowercase kind tag for an SR-scoped subject",
      "definition": "The lowercase `kind` value used wherever a scope or subject ref names a requirement: `SystemScopeRef.kind == \"sr\"` for `--scope sr:<id>` (`SystemScopeKind`, system-cli.ts:9), `MatrixSubjectRef`'s only legal kind, and one of `TimelineSubjectRef`'s four legal kinds (system-cli.ts:106). Distinct from the noun `SR`, which names the requirement itself -- its file, statement, and binding -- not this kind tag.",
      "siblings": [
        "bundle",
        "task",
        "run",
        "manifest"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "pi-ext/factory-watch/src/system-cli.ts"
      ]
    },
    "pending": {
      "term": "pending",
      "group": "disposition",
      "label": "pending",
      "gloss": "the default: a real, unaddressed gap",
      "definition": "The default disposition a gap gets when the node it belongs to carries neither `trace_exempt: true` nor a `trace_deferred` reason (`gaps._disposition_of`). A pending gap is a live defect -- it counts as unfilled in its health-class slot, and never reduces the class denominator the way `exempt` does.",
      "siblings": [
        "exempt",
        "deferred"
      ],
      "computed_by": [
        "src/factory/trace/gaps.py"
      ]
    },
    "exempt": {
      "term": "exempt",
      "group": "disposition",
      "label": "exempt",
      "gloss": "waived by a recorded trace_exempt flag",
      "definition": "The node's frontmatter declares `trace_exempt: true`. This removes the slot from the health-class denominator entirely (`expected[slot] -= 1`) rather than counting it unfilled -- an exempt gap does not drag the percentage down. SRs and BRs can never carry this disposition (`gaps._disposition_of`'s explicit guard, design 4.4): a requirement's gap can be deferred, never waived outright.",
      "siblings": [
        "pending",
        "deferred"
      ],
      "computed_by": [
        "src/factory/trace/gaps.py"
      ]
    },
    "satisfies": {
      "term": "satisfies",
      "group": "stops-at",
      "label": "satisfies",
      "gloss": "reverse walk stopped: task resolved, no satisfies",
      "definition": "In `system reverse`'s file -> run -> task -> requirements walk, `stops_at: \"satisfies\"` means the task itself resolved in the ledger but declares no `satisfies` list, so the walk cannot continue to a requirement. The other named stop, `\"task\"`, means the run's own `task_id` did not resolve in the ledger at all -- one step earlier in the same chain.",
      "siblings": [
        "chain-complete"
      ],
      "computed_by": [
        "src/factory/system/reverse.py"
      ]
    },
    "chain-complete": {
      "term": "chain-complete",
      "group": "stops-at",
      "label": "chain complete",
      "gloss": "display label for a null stops_at",
      "definition": "The browser's rendering of `stops_at: null` -- `system-renderers.ts:441` prints `'null (chain complete)'` -- meaning the walk reached at least one requirement with no unresolved hop in between. Never a value `reverse.py` itself writes into the JSON; `null` is the recorded value, `chain-complete` is only ever a rendered label for it.",
      "siblings": [
        "satisfies"
      ],
      "computed_by": [
        "src/factory/system/reverse.py",
        "pi-ext/factory-watch/src/system-renderers.ts"
      ]
    },
    "scope": {
      "term": "scope",
      "group": "noun",
      "label": "scope",
      "gloss": "what a page is about: bundle or SR",
      "definition": "A `{kind, ref}` pointer naming what a page's brief/matrix/timeline/guide is about -- today always `bundle:<id>` or `sr:<id>` for `--scope`-driven commands (`SystemScopeKind`), though the underlying `SystemScopeRef` shape is reused more broadly for declared bundle members and timeline/matrix subjects, which allow a wider set of kinds.",
      "siblings": [
        "citation",
        "claim"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "src/factory/system/queries.py"
      ]
    },
    "SR": {
      "term": "SR",
      "group": "noun",
      "label": "SR (requirement)",
      "gloss": "a satisfaction requirement file under requirements/SR-*.md",
      "definition": "A requirement declared in `requirements/SR-*.md`, loaded by `factory.requirements.register`. Carries a statement, optional upstream requirements, and an optional binding (a harness/experiment/metric/assertion) that validation runs against. An SR with no binding is `proposed`; SRs and BRs are the only node kinds that can never be marked `trace_exempt` (design 4.4).",
      "siblings": [
        "BR",
        "bundle"
      ],
      "computed_by": [
        "src/factory/requirements/register.py",
        "src/factory/trace/model.py"
      ]
    },
    "BR": {
      "term": "BR",
      "group": "noun",
      "label": "BR (business requirement)",
      "gloss": "same file convention as SR, requirements/BR-*.md",
      "definition": "A requirement declared in `requirements/BR-*.md` -- the same id/title/frontmatter shape `trace.model._id_node` gives an SR, loaded as trace node kind `\"br\"`. Like an SR, a BR can never be marked `trace_exempt` (`gaps._disposition_of`'s explicit guard checks both kinds), but unlike an SR it has no health-class slot of its own -- `trace.health._SLOTS_PER_NODE` only assigns slots to `task`/`plan`/`sr` node kinds.",
      "siblings": [
        "SR"
      ],
      "computed_by": [
        "src/factory/trace/model.py"
      ]
    },
    "ADR": {
      "term": "ADR",
      "group": "noun",
      "label": "ADR (architecture decision record)",
      "gloss": "a recorded decision doc, brief only",
      "definition": "A decision document under `docs/adr/`, loaded by `factory.system.adr`. An ADR scope renders Brief only -- design and gaps but no validation matrix, no runs, and no reverse walk -- because those tabs would be permanently degraded for a document that is a decision record, not an implementation unit.",
      "siblings": [
        "SR",
        "BR"
      ],
      "computed_by": [
        "src/factory/system/adr.py",
        "src/factory/system/queries.py"
      ]
    },
    "evidence run": {
      "term": "evidence run",
      "group": "noun",
      "label": "evidence run",
      "gloss": "one run_id in a task's story",
      "definition": "One entry in a task's story (`StoryRun`): a `run_id`, its outcome, timestamps, optional commit range, and an implementation claim -- sourced either from a durable evidence manifest (`source: \"manifest\"`) or, when no manifest exists for that run, from a session record (`source: \"session\"`, which never carries changed files or a commit range).",
      "siblings": [
        "evidence manifest",
        "session record"
      ],
      "computed_by": [
        "src/factory/system/story.py"
      ]
    },
    "evidence manifest": {
      "term": "evidence manifest",
      "group": "noun",
      "label": "evidence manifest",
      "gloss": "the durable evidence/runs/<run_id>.json file for a run",
      "definition": "The durable, schema-validated record of one run, `evidence/runs/<run_id>.json`, written by `factory.evidence.manifests` and read through `list_run_manifests` everywhere this package consumes it -- never a second parser. Carries the run's `implementation` (changed files, commit range), its `validation` array, and its `reviews` array (the sole source of signed review decisions).",
      "siblings": [
        "evidence run",
        "session record"
      ],
      "computed_by": [
        "src/factory/evidence/manifests.py",
        "src/factory/system/_claims.py"
      ]
    },
    "session record": {
      "term": "session record",
      "group": "noun",
      "label": "session record",
      "gloss": "a thinner sessions/*.session.json fallback, no changed files",
      "definition": "A `sessions/*.session.json` file, loaded by `factory.system.sessions.load_session_runs`, used as a fallback for a task run when no durable evidence manifest exists for it. Thinner by nature -- no commit range, no changed files, no patch -- because a session record never captures those; where both exist for the same `run_id`, the manifest always wins and the session record is never read into the story.",
      "siblings": [
        "evidence run",
        "evidence manifest"
      ],
      "computed_by": [
        "src/factory/system/sessions.py",
        "src/factory/system/story.py"
      ]
    },
    "claim": {
      "term": "claim",
      "group": "noun",
      "label": "claim",
      "gloss": "the shared record shape: kind, text, citations, freshness",
      "definition": "The shared record shape (design SS7.2) every fact the navigator renders is packaged as: a `kind` (recorded/derived/synthesized/missing), `text`, a `freshness` verdict, and the `citations` it is traceable back to. A `SystemClaim` also carries `spans` -- but only when `kind` is `synthesized`.",
      "siblings": [
        "span",
        "citation"
      ],
      "computed_by": [
        "src/factory/system/models.py"
      ]
    },
    "span": {
      "term": "span",
      "group": "noun",
      "label": "span",
      "gloss": "a verbatim quoted excerpt, verified against its citation",
      "definition": "A verbatim quoted excerpt of source text (`text`) plus the index of the citation it was pulled from (`citation_index`), present only on `synthesized` claims. `guide._verbatim_span` independently re-reads the cited file and confirms the candidate text is a literal substring of it before a span is ever emitted -- never a paraphrase, never a best-effort quote.",
      "siblings": [
        "claim",
        "citation"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "src/factory/system/guide.py"
      ]
    },
    "citation": {
      "term": "citation",
      "group": "noun",
      "label": "citation",
      "gloss": "a recorded source a claim cites",
      "definition": "A pointer at the recorded artifact a claim was built from: a `kind` (see the `citation-kind` group), a `path`, an optional `sha256` of the file's content at read time (null when the file could not be read, which is what makes a claim `degraded`), and an optional `anchor` naming a specific location inside the file, such as `reviews[2]`.",
      "siblings": [
        "claim",
        "span"
      ],
      "computed_by": [
        "src/factory/system/models.py",
        "src/factory/system/_claims.py"
      ]
    }
  }
} as const;

export const REMEDIATION_DATA = {
  "version": 1,
  "states": {
    "task_no_sr": {
      "state": "task_no_sr",
      "headline": "Task satisfies no requirement",
      "what_it_means": "This task declares no `satisfies` edge at all (gaps.py: \"task declares no satisfies\").",
      "why_it_matters": "A task with no satisfies edge can't be counted toward any requirement's coverage, so the work it represents is invisible to the trace graph.",
      "command": "uv run python -m factory.trace link {id} --satisfies <SR-id>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "task_no_plan": {
      "state": "task_no_plan",
      "headline": "Task declares no source plan",
      "what_it_means": "This task declares no `source_plan` edge at all (gaps.py: \"task declares no source_plan\").",
      "why_it_matters": "Without a source_plan, the task->plan->spec chain has nothing to walk, so its Trace tab and the working traversal can't reach the plan or spec it came from.",
      "command": "uv run python -m factory.trace link {id} --source-plan <plan-filename>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "task_plan_missing": {
      "state": "task_plan_missing",
      "headline": "Task's source plan does not exist",
      "what_it_means": "This task's recorded `source_plan` points at a plan node id that isn't in the trace graph (gaps.py: \"source_plan target missing: <id>\").",
      "why_it_matters": "The link was recorded but the plan it names is gone or was never there, so the task's plan hop dead-ends instead of resolving.",
      "command": "uv run python -m factory.trace link {id} --source-plan <existing-plan-filename>",
      "command_kind": "shell",
      "severity": "failure"
    },
    "plan_no_spec": {
      "state": "plan_no_spec",
      "headline": "Plan references no spec",
      "what_it_means": "This plan declares no `spec_ref` edge at all (gaps.py: \"plan references no spec\").",
      "why_it_matters": "Without a spec_ref, the plan's design rationale can't be traced back to the spec that authorized it.",
      "command": "uv run python -m factory.trace link {id} --spec <spec-filename>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "dangling_upstream": {
      "state": "dangling_upstream",
      "headline": "Upstream reference points nowhere",
      "what_it_means": "This node's recorded `upstream` edge names a node id that isn't in the trace graph (gaps.py: \"upstream target missing: <id>\").",
      "why_it_matters": "The chain from business requirement down to this node is broken at the upstream hop, so its higher-level justification can't be traced.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "failure"
    },
    "sr_unsatisfied": {
      "state": "sr_unsatisfied",
      "headline": "No task satisfies this requirement",
      "what_it_means": "No task in the ledger declares a `satisfies` edge to {id} (gaps.py: \"no task declares satisfies for this SR\").",
      "why_it_matters": "Nothing implements it yet, so it cannot be validated and the feature it belongs to stays weak.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "sr_proposed": {
      "state": "sr_proposed",
      "headline": "Requirement's binding is not yet decided",
      "what_it_means": "This SR is `proposed`: accepted in substance, but it carries no measurement binding yet (gaps.py: \"binding not yet decided\").",
      "why_it_matters": "A proposed SR can never be validated -- there is no experiment, metric, or assertion recorded to check it against.",
      "command": "uv run python -m factory.requirements bind {id} --experiment <name> --metric <metric> --assert <expression>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "sr_unvalidatable": {
      "state": "sr_unvalidatable",
      "headline": "Validation could not run",
      "what_it_means": "This SR's recorded validation state is `error`: the harness ran but produced no verdict (validation_status.py `SrState`; gaps.py surfaces the recorded error, or \"validation could not run\" if none was recorded). This gap only fires once the SR already has a binding: it's raised in `find_gaps`'s (gaps.py:58) `else` branch of `if node.proposed`, and `proposed` itself means \"no binding\" -- set in `_id_node` (trace/model.py:59) -- so the binding exists, and `factory.requirements bind` is not the fix.",
      "why_it_matters": "An errored harness leaves the requirement's actual status unknown -- it is neither confirmed working nor confirmed broken. If the recorded binding names a harness that isn't actually configured, re-running validation surfaces that configuration error directly rather than silently passing; no command in the current surface repairs a missing harness declaration -- that still requires editing the binding by hand.",
      "command": "uv run python -m factory.validation run --satisfies {id}",
      "command_kind": "shell",
      "severity": "failure"
    },
    "sr_unvalidated": {
      "state": "sr_unvalidated",
      "headline": "Requirement was never validated",
      "what_it_means": "No entry for this SR exists in the validation report (gaps.py: \"absent from validation report\" -- status is absent, or its state is `never_validated`).",
      "why_it_matters": "A bound requirement with no validation entry has never been checked against its own metric, so passing or failing is still unknown.",
      "command": "uv run python -m factory.validation run --satisfies {id}",
      "command_kind": "shell",
      "severity": "absence"
    },
    "sr_stale": {
      "state": "sr_stale",
      "headline": "Validation result is stale",
      "what_it_means": "The recorded validation result predates a later change to this SR's statement or binding (gaps.py: \"result predates a change to statement or binding\").",
      "why_it_matters": "The passing or failing result on file no longer reflects what the requirement currently says or how it's measured, so it can't be trusted as current evidence.",
      "command": "uv run python -m factory.validation run --satisfies {id}",
      "command_kind": "shell",
      "severity": "failure"
    },
    "dangling_reference": {
      "state": "dangling_reference",
      "headline": "Verification-cycle edge points nowhere",
      "what_it_means": "A recorded verification-cycle edge (`parent_of`, `verified_by`, `demonstrates`, `evaluates`, `contains`, or `illustrates`) names a source or target node id that isn't in the trace graph (gaps.py: \"<kind> source/target missing: <id>\").",
      "why_it_matters": "The V-cycle view (design intent paired with its verifying evidence) can't be walked past this point for this node.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "failure"
    },
    "no_claims": {
      "state": "no_claims",
      "headline": "No claims recorded",
      "what_it_means": "The Brief tab's claims list came back empty for this scope (`query_brief`, queries.py) -- rendered as \"No claims recorded for this scope.\" (system-renderers.ts renderBrief).",
      "why_it_matters": "The Brief tab has nothing to show about this scope until its underlying register and trace data exist.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_matrix_rows": {
      "state": "no_matrix_rows",
      "headline": "No validation rows recorded",
      "what_it_means": "The Matrix tab's rows list came back empty for this scope (`query_matrix` found no sr: members to report on) -- rendered as \"No validation rows recorded for this scope.\" (system-renderers.ts renderMatrix).",
      "why_it_matters": "With no rows, there is nothing here to confirm this scope's requirements are actually validated.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_timeline_events": {
      "state": "no_timeline_events",
      "headline": "No recorded decisions",
      "what_it_means": "The Timeline tab's events list came back empty for this scope (`query_timeline`) -- rendered as \"No recorded decisions for this scope.\" (system-renderers.ts renderTimeline).",
      "why_it_matters": "Without timeline events, there's no recorded history of what was decided and when for this scope.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_guide_sections": {
      "state": "no_guide_sections",
      "headline": "No guide sections recorded",
      "what_it_means": "The Guide tab's sections list came back empty for this scope (`query_guide`) -- rendered as \"No guide sections recorded for this scope.\" (system-renderers.ts renderGuide).",
      "why_it_matters": "The synthesized narrative has nothing recorded to draw on for this scope.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_runs": {
      "state": "no_runs",
      "headline": "No recorded runs",
      "what_it_means": "This task's Story tab has no recorded runs -- rendered as \"No recorded runs for this task.\" (system-renderers.ts renderStory).",
      "why_it_matters": "Without a run, there is no execution evidence that this task was ever actually worked.",
      "command": "/factory-run {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_requirements": {
      "state": "no_requirements",
      "headline": "No requirements recorded on this task",
      "what_it_means": "This task's Story tab shows \"no requirements recorded\": the task declares no `satisfies` edges (story.py) -- the same condition the `task_no_sr` trace gap reports.",
      "why_it_matters": "A task with no requirement link can't be shown as implementing anything the system is tracking.",
      "command": "uv run python -m factory.trace link {id} --satisfies <SR-id>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "no_changed_files": {
      "state": "no_changed_files",
      "headline": "No changed files recorded",
      "what_it_means": "This run's implementation claim has an empty `changed_files` list -- rendered as \"no changed files recorded\" (system-renderers.ts renderChangedFiles).",
      "why_it_matters": "Without a changed-files list, this run's evidence can't show what it actually touched.",
      "command": "/factory-run {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_commit_range": {
      "state": "no_commit_range",
      "headline": "No commit range recorded",
      "what_it_means": "This run has no `start_commit`/`result_commit` recorded -- rendered as \"commit range not recorded\" (system-renderers.ts renderCommitRange).",
      "why_it_matters": "Without a commit range, this run's change can't be located in git history.",
      "command": "/factory-run {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_trace": {
      "state": "no_trace",
      "headline": "No trace recorded for this scope",
      "what_it_means": "The Trace tab found no SR refs to invert for this scope -- rendered as \"No trace recorded for this scope. See the Story or Reverse tabs.\" (system-renderers.ts renderTrace).",
      "why_it_matters": "With no SR refs to walk, the requirement -> task -> plan -> spec chain can't be shown for this scope.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_traversal_step": {
      "state": "no_traversal_step",
      "headline": "Traversal step not recorded",
      "what_it_means": "One step of the working traversal (tasks, design, or files) came back with no values -- rendered as \"Not recorded\" for that step (system-bootstrap.ts renderTraversal / addStep).",
      "why_it_matters": "The requirement -> tasks -> design -> files spine has a gap at this step, so the working traversal stops short.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "absence"
    },
    "no_bundles": {
      "state": "no_bundles",
      "headline": "No features defined yet",
      "what_it_means": "A feature bundle groups the requirements, tasks, and decisions you read together to understand one part of the system. Bundles are hand-authored, not generated: create `bundles/<id>.json` with `id`, `label`, and `members` (a list of `sr:`/`task:`/`spec:`/`plan:`/... refs), and optionally a `description` of at most 280 characters.",
      "why_it_matters": "Bundles are how this project is browsed, so until one exists the directory stays empty. The command below only checks a draft file you've already written -- its own docstring says it \"proposes nothing and writes nothing; the draft is judged, not generated\" (`cmd_bundle_check`, system/cli.py:103) -- there is no CLI that creates the bundle file for you.",
      "command": "uv run python -m factory.system bundle check --draft <path>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "no_description": {
      "state": "no_description",
      "headline": "No description recorded",
      "what_it_means": "No description is recorded for this artifact: a bundle has no `description` field, or a spec/plan has none of the named sections the label index looks for (`Purpose`, `Goal`, `Problem`, `Overview`, `Summary`, or a plan's `**Goal:**` line -- design Component 1).",
      "why_it_matters": "Without a recorded description, the card that opens on hover or focus has nothing to show beyond the id and title. For a bundle, add a `description` (<=280 characters) to its hand-authored `bundles/<id>.json` by hand, then use the command below to check it -- the command validates a draft you edit yourself; it does not write the field for you (`cmd_bundle_check`, system/cli.py:103). For a spec or plan, there is no CLI at all -- add the named section or `**Goal:**` line directly in the document.",
      "command": "uv run python -m factory.system bundle check --draft <path>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "traversal_not_applicable": {
      "state": "traversal_not_applicable",
      "headline": "Traversal doesn't apply to this scope",
      "what_it_means": "Traversal only applies to bundle:/sr: scopes; task:/file: scopes show \"Traversal is not applicable for this scope.\" instead (system-bootstrap.ts resetScopeEvidence).",
      "why_it_matters": "This is expected behavior for the current scope kind, not a defect -- there is nothing to remediate here.",
      "command": "/system",
      "command_kind": "slash",
      "severity": "absence"
    },
    "matrix_never_run": {
      "state": "matrix_never_run",
      "headline": "Requirement was never validated",
      "what_it_means": "This Matrix row's status is `never_run`: the SR resolves and carries a binding, but `_sr_matrix_row` (queries.py:1040) found no entry for it in the validation report -- its `status is None and not report_corrupt` branch returns `MatrixStatus.NEVER_RUN`, summary \"never validated\" (queries.py:1078-1083). This is distinct from an SR ref that doesn't resolve at all, which `_sr_missing_matrix_row` reports separately as `unknown` / \"sr does not exist\".",
      "why_it_matters": "A row that has never run carries no evidence either way -- it is not passing, not failing, simply unchecked.",
      "command": "uv run python -m factory.validation run --satisfies {id}",
      "command_kind": "shell",
      "severity": "absence"
    },
    "unbundled_artifact": {
      "state": "unbundled_artifact",
      "headline": "Not a member of any bundle",
      "what_it_means": "This artifact is not listed as a member of any bundle declaration (`factory.system coverage`'s `unbundled` list, bundles.py).",
      "why_it_matters": "Unbundled artifacts are unreachable by browsing the feature directory -- only a direct ref or the Trace tab reaches them. To fix this, add this ref to the `members` list of an existing (or new) hand-authored `bundles/<id>.json` -- the command below only checks that edit; it does not add the membership for you (`cmd_bundle_check`, system/cli.py:103, \"the draft is judged, not generated\").",
      "command": "uv run python -m factory.system bundle check --draft <path>",
      "command_kind": "shell",
      "severity": "absence"
    },
    "unresolved_ref": {
      "state": "unresolved_ref",
      "headline": "Reference does not resolve",
      "what_it_means": "A ref shown on this page (a member-of bundle id, a satisfies/upstream target, a trace hop) doesn't resolve to any node in the label index; the browser renders the raw string plus the note \"not in the label index\" (design Component 1).",
      "why_it_matters": "A ref that can't resolve means the id it names is either misspelled or was never created, so whatever it points at can't be reached from here. `/trace-fix` only helps when the broken ref is a trace edge (satisfies/source_plan/spec_ref/upstream) -- for the `member_of` flavour of this gap (a bundle listing a member ref that doesn't resolve), `factory.trace link` has no `--member-of` flag, so the fix is to hand-edit the bundle's `members` list directly; running `/trace-fix {id}` will not touch it.",
      "command": "/trace-fix {id}",
      "command_kind": "slash",
      "severity": "failure"
    }
  }
} as const;
