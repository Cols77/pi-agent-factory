"""Plain-language definitions for every contract word the navigator shows.

Static data. Inlined into the page by system-shell.ts at render time -- the
browser never fetches this. Exposed as `factory.system vocabulary --json` so
it stays inspectable and testable from Python.

`COVERAGE_REGISTRY` is grouped by where a value is read on the page; a value
that means the same recorded thing in two different groups (`unknown`,
`manifest`, `session`, `validated`, `bundle`, `review`, `validation`, `task`,
`not-recorded` -- nine collisions, all disclosed in their entries'
`definition`) gets exactly one `VOCABULARY` entry, filed under the group it
is *most often* read in, and that entry's `definition` names every other
context explicitly rather than silently picking one meaning.
`test_every_entry_is_in_the_registry` is the enforcement: `VOCABULARY`'s key
set must equal the union of every group's values, no more and no less.

Every group backed by a closed Python enum (`claim-kind`, `freshness`,
`matrix-status`, `timeline-actor`, `timeline-action`, `citation-kind`) is
additionally checked against that enum directly in
`test_vocabulary.py::test_registry_groups_backed_by_enums_match_those_enums_exactly`
-- the registry tuple is hand-authored prose sugar for humans reading this
file, but the enum is the actual authority, and drift between the two fails
the build.
"""
from __future__ import annotations

COVERAGE_REGISTRY: dict[str, tuple[str, ...]] = {
    "claim-kind": ("recorded", "derived", "synthesized", "missing"),
    "freshness": ("fresh", "stale", "degraded", "n/a"),
    "matrix-status": ("passed", "failed", "error", "blocked", "never-run", "unknown"),
    "validation-state": ("never_validated",),
    "readiness": ("weak", "medium", "strong"),
    "readiness-count": (
        "sr_total", "bound", "covered", "current", "deferred", "validated",
    ),
    "health-class": (
        "task->plan", "task->SR", "plan->spec", "SR satisfied", "SR validated",
    ),
    "health-counter": ("dangling", "deferred", "proposed"),
    "timeline-actor": (
        "human", "dev", "review", "validation", "orchestrator", "unknown",
        "not-recorded",
    ),
    "timeline-action": (
        "approved", "rejected", "validated", "repaired", "published",
        "stopped", "not-recorded",
    ),
    "citation-kind": (
        "manifest", "task", "requirement", "validation", "review",
        "decision", "trace", "bundle", "session", "failure", "goal",
    ),
    "scope-kind": ("bundle", "sr", "task", "run", "manifest"),
    "run-source": ("session",),
    "disposition": ("pending", "exempt"),
    "stops-at": ("task", "satisfies", "chain-complete"),
    "noun": (
        "bundle", "scope", "SR", "BR", "ADR", "evidence run",
        "evidence manifest", "session record", "claim", "span", "citation",
    ),
}


VOCABULARY: dict[str, dict] = {
    # -----------------------------------------------------------------
    # claim-kind (design SS3.1) -- where a rendered fact came from.
    # -----------------------------------------------------------------
    "recorded": {
        "term": "recorded",
        "group": "claim-kind",
        "label": "recorded",
        "gloss": "copied straight out of a file, nothing computed",
        "definition": (
            "The claim text was copied verbatim out of an artifact file "
            "(a requirement, task, ADR, or bundle declaration). Nothing was "
            "computed, aggregated, or written by a model to produce it."
        ),
        "siblings": ["derived", "synthesized", "missing"],
        "computed_by": [
            "src/factory/system/queries.py",
            "src/factory/system/models.py",
        ],
    },
    "derived": {
        "term": "derived",
        "group": "claim-kind",
        "label": "derived",
        "gloss": "computed by rolling up several recorded facts",
        "definition": (
            "The claim is a computation over one or more recorded facts -- for "
            "example a bundle's implementation summary (run count, latest "
            "outcome) rolled up from several evidence-manifest runs, or a "
            "guide section's bullet list rolled up from several claims, some "
            "of which may themselves be missing. Never a language-model "
            "output; always a deterministic aggregation."
        ),
        "siblings": ["recorded", "synthesized", "missing"],
        "computed_by": [
            "src/factory/system/queries.py",
            "src/factory/system/guide.py",
        ],
    },
    "synthesized": {
        "term": "synthesized",
        "group": "claim-kind",
        "label": "synthesized",
        "gloss": "scaffold prose wrapped around a verified verbatim quote",
        "definition": (
            "Fixed scaffolding text plus one or more verbatim spans copied "
            "character-for-character from a cited source file. No language "
            "model is invoked and no text is reworded: the exact substring "
            "is independently re-checked against the cited file before "
            "this kind is ever assigned -- it only fires when every fact "
            "backing the section is fresh; otherwise the section collapses "
            "to `derived` or `recorded` bullets instead."
        ),
        "siblings": ["recorded", "derived", "missing"],
        "computed_by": ["src/factory/system/guide.py"],
    },
    "missing": {
        "term": "missing",
        "group": "claim-kind",
        "label": "missing",
        "gloss": "no artifact exists to back this claim",
        "definition": (
            "There is no recorded basis for the claim at all -- a bundle "
            "member that does not resolve to a real file, a requirement with "
            "no validation report entry, or a scope that no longer exists. "
            "A claim of kind `missing` always has freshness `n/a`, and the "
            "reverse: the two always travel together."
        ),
        "siblings": ["recorded", "derived", "synthesized"],
        "computed_by": [
            "src/factory/system/_claims.py",
            "src/factory/system/models.py",
        ],
    },
    # -----------------------------------------------------------------
    # freshness (design SS3.2) -- whether a claim is still current.
    # -----------------------------------------------------------------
    "fresh": {
        "term": "fresh",
        "group": "freshness",
        "label": "fresh",
        "gloss": "cited inputs still match what is recorded now",
        "definition": (
            "Every dependency the claim was built from still matches its "
            "recorded current state -- a requirement's own declaration file "
            "is always fresh the moment it resolves; a validation result is "
            "fresh only while the report entry has not gone stale against a "
            "later edit to the requirement's statement or binding."
        ),
        "siblings": ["stale", "degraded", "n/a"],
        "computed_by": [
            "src/factory/system/models.py",
            "src/factory/system/_claims.py",
        ],
    },
    "stale": {
        "term": "stale",
        "group": "freshness",
        "label": "stale",
        "gloss": "the requirement changed since this result was recorded",
        "definition": (
            "The cited evidence exists and was once valid, but the "
            "requirement's statement or binding changed after that result "
            "was recorded, so the old outcome can no longer be trusted as "
            "current. Set for both a brief's validation claim and the "
            "matrix row for the same requirement."
        ),
        "siblings": ["fresh", "degraded", "n/a"],
        "computed_by": ["src/factory/trace/validation_status.py", "src/factory/system/queries.py"],
    },
    "degraded": {
        "term": "degraded",
        "group": "freshness",
        "label": "degraded",
        "gloss": "a cited file exists but could not read",
        "definition": (
            "Something recorded should back the claim, but the specific file "
            "could not be read or parsed -- a corrupt validation report, an "
            "evidence manifest whose sha256 came back null, or a rollup with "
            "at least one missing contributor. Distinct from `missing`: a "
            "degraded claim still has a citation, it just could not be "
            "verified."
        ),
        "siblings": ["fresh", "stale", "n/a"],
        "computed_by": ["src/factory/system/queries.py", "src/factory/system/guide.py"],
    },
    "n/a": {
        "term": "n/a",
        "group": "freshness",
        "label": "not applicable",
        "gloss": "no recorded basis to judge freshness at all",
        "definition": (
            "There is nothing recorded to be fresh or stale against -- a "
            "proposed requirement with no binding yet, or any claim of kind "
            "`missing`. This state only ever pairs with claim kind "
            "`missing`; it is never used for a claim that resolved to real "
            "content."
        ),
        "siblings": ["fresh", "stale", "degraded"],
        "computed_by": ["src/factory/system/models.py", "src/factory/system/queries.py"],
    },
    # -----------------------------------------------------------------
    # matrix-status (design SS7.3) -- the recorded validation outcome,
    # never staleness or absence (those live on freshness).
    # -----------------------------------------------------------------
    "passed": {
        "term": "passed",
        "group": "matrix-status",
        "label": "passed",
        "gloss": "the validation report recorded this requirement passing",
        "definition": (
            "`validation/validation-report.json` recorded an entry for this "
            "requirement with `passed: true` and no error. The requirement "
            "may still show freshness `stale` if its statement or binding "
            "changed afterward -- `passed` on its own only means the last "
            "recorded run succeeded, not that it is current."
        ),
        "siblings": ["failed", "error", "blocked", "never-run", "unknown"],
        "computed_by": ["src/factory/trace/validation_status.py", "src/factory/system/queries.py"],
    },
    "failed": {
        "term": "failed",
        "group": "matrix-status",
        "label": "failed",
        "gloss": "the validation report recorded this requirement failing",
        "definition": (
            "`validation/validation-report.json` recorded an entry for this "
            "requirement with `passed: false`. For a bundle's run-level "
            "verdict, any requirement recorded `passed: false` makes the "
            "whole run `failed`, taking priority over any stale result."
        ),
        "siblings": ["passed", "error", "blocked", "never-run", "unknown"],
        "computed_by": ["src/factory/trace/validation_status.py", "src/factory/system/queries.py"],
    },
    "error": {
        "term": "error",
        "group": "matrix-status",
        "label": "error",
        "gloss": "the validation attempt itself could not complete",
        "definition": (
            "The recorded report entry carries an `error` field: the "
            "validation harness itself could not run to a pass/fail verdict "
            "(a crashed experiment, a missing metric), as distinct from "
            "`failed`, where validation ran and the assertion did not hold."
        ),
        "siblings": ["passed", "failed", "blocked", "never-run", "unknown"],
        "computed_by": ["src/factory/trace/validation_status.py", "src/factory/system/queries.py"],
    },
    "blocked": {
        "term": "blocked",
        "group": "matrix-status",
        "label": "blocked",
        "gloss": "the requirement has no binding to validate against",
        "definition": (
            "The requirement is `proposed` -- its register entry has no "
            "binding yet -- so there is nothing recorded to run a validation "
            "against. This is decided before ever consulting the validation "
            "report; freshness is `n/a`, never `fresh`, since there is no "
            "basis to be current about."
        ),
        "siblings": ["passed", "failed", "error", "never-run", "unknown"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    "never-run": {
        "term": "never-run",
        "group": "matrix-status",
        "label": "never run",
        "gloss": "bound and validatable, but no report entry yet",
        "definition": (
            "The requirement has a decided binding, but "
            "`validation/validation-report.json` carries no entry for it -- "
            "validation has simply not been run yet, distinct from `blocked` "
            "(no binding to run) and `error` (ran and could not complete). "
            "Note the hyphen: the underlying validation state spells this "
            "same state `never_validated` with an underscore; they are the "
            "same recorded absence, spelled two ways for two different "
            "consumers."
        ),
        "siblings": ["passed", "failed", "error", "blocked", "unknown"],
        "computed_by": ["src/factory/trace/validation_status.py", "src/factory/system/queries.py"],
    },
    "unknown": {
        "term": "unknown",
        "group": "matrix-status",
        "label": "unknown",
        "gloss": "outcome cannot be determined at all",
        "definition": (
            "Two distinct \"cannot determine\" cases share this value. As a "
            "matrix status, it means either the referenced SR does not "
            "exist, or the validation report file exists but is corrupt or "
            "unparseable -- deliberately not `never-run`, which would "
            "assert a recorded fact the evidence does not support. As a "
            "timeline actor, it is a reserved closed-vocabulary value for "
            "an actor string that does not match a recognized case; this "
            "repo's timeline never actually emits it today -- it always "
            "emits `not-recorded` instead, because the review-decision "
            "artifact this repo reads carries no actor field at all."
        ),
        "siblings": ["passed", "failed", "error", "blocked", "never-run"],
        "computed_by": ["src/factory/system/queries.py", "src/factory/system/models.py"],
    },
    # -----------------------------------------------------------------
    # validation-state (trace.validation_status.SrState)
    # -----------------------------------------------------------------
    "never_validated": {
        "term": "never_validated",
        "group": "validation-state",
        "label": "never validated",
        "gloss": "no report entry recorded; underscore spelling of never-run",
        "definition": (
            "The underlying validation state's own spelling (with an "
            "underscore) of the state the matrix renders as `never-run` "
            "(with a hyphen). An SR absent from the validation report is "
            "simply absent from what the report parser returns -- this "
            "exact string is written separately, by a fallback summary "
            "used only when no status was found for the requirement at "
            "all, and is checked defensively wherever an absent status "
            "needs a name."
        ),
        "siblings": ["passed", "failed", "error"],
        "computed_by": [
            "src/factory/trace/validation_status.py",
            "src/factory/system/feature.py",
            "src/factory/trace/gaps.py",
        ],
    },
    # -----------------------------------------------------------------
    # readiness (design SS3.4, SP-B) -- per-bundle Strong/Medium/Weak.
    # -----------------------------------------------------------------
    "weak": {
        "term": "weak",
        "group": "readiness",
        "label": "weak",
        "gloss": "fallback: not every SR is bound and covered",
        "definition": (
            "The bundle's member SRs fail the `medium` bar -- at least one "
            "member SR has no decided binding, or has no non-exempt task "
            "satisfying it. Also the readiness of any bundle that declares "
            "no SR members at all. This is always computed by Python; the "
            "browser never computes it itself."
        ),
        "siblings": ["medium", "strong"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "medium": {
        "term": "medium",
        "group": "readiness",
        "label": "medium",
        "gloss": "every SR is bound and covered by task",
        "definition": (
            "Every member SR has a decided binding (`bound`) and at least "
            "one non-exempt task declaring `satisfies` for it (`covered`) -- "
            "but not necessarily `validated`. `bound` (a binding is decided "
            "and the SR is not proposed) is strictly stronger than "
            "`current` (a binding is recorded at all), so every member SR "
            "of a medium bundle is already current too; only `strong` "
            "additionally requires a fresh passing validation."
        ),
        "siblings": ["weak", "strong"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "strong": {
        "term": "strong",
        "group": "readiness",
        "label": "strong",
        "gloss": "every SR is covered, current, and passing validation",
        "definition": (
            "Every member SR is `covered` (a satisfying task), `current` "
            "(a decided binding, not a proposed placeholder), and `validated` "
            "(the validation report records a fresh pass for it). The "
            "highest of the three grades; this condition is checked first."
        ),
        "siblings": ["weak", "medium"],
        "computed_by": ["src/factory/system/health.py"],
    },
    # -----------------------------------------------------------------
    # readiness-count (health.py:67-93, per-bundle SR tallies)
    # -----------------------------------------------------------------
    "sr_total": {
        "term": "sr_total",
        "group": "readiness-count",
        "label": "SR total",
        "gloss": "how many SRs this bundle declares as members",
        "definition": (
            "The count of `sr:` refs the bundle declares as members. This "
            "is a per-bundle denominator, scoped to one bundle's declared "
            "membership; it is not the repo-wide SR count the `SR "
            "satisfied`/`SR validated` health classes use, which counts "
            "every SR node in the whole trace graph regardless of bundle "
            "membership."
        ),
        "siblings": ["bound", "covered", "current", "deferred", "validated"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "bound": {
        "term": "bound",
        "group": "readiness-count",
        "label": "bound",
        "gloss": "has a decided binding, not flagged proposed",
        "definition": (
            "How many of the bundle's member SRs have a decided binding in "
            "the requirements register *and* are not flagged `sr_proposed` "
            "in the trace graph. An SR can have a register binding yet "
            "still be excluded here if the trace independently marks it "
            "proposed."
        ),
        "siblings": ["sr_total", "covered", "current", "deferred", "validated"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "covered": {
        "term": "covered",
        "group": "readiness-count",
        "label": "covered",
        "gloss": "at least one non-exempt task satisfies this SR",
        "definition": (
            "How many of the bundle's member SRs have no `sr_unsatisfied` "
            "gap recorded against them -- i.e. at least one task declares "
            "`satisfies` for the SR. In principle an exempt "
            "`sr_unsatisfied` gap would also count as covered, but that "
            "case cannot actually happen: an SR's own gaps can never be "
            "marked `exempt`, only `pending` or `deferred`."
        ),
        "siblings": ["sr_total", "bound", "current", "deferred", "validated"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "current": {
        "term": "current",
        "group": "readiness-count",
        "label": "current",
        "gloss": "has a decided binding, not a placeholder",
        "definition": (
            "How many of the bundle's member SRs have a decided binding in "
            "the requirements register -- i.e. are not an auto-declined "
            "placeholder still waiting on a measurement decision. Unlike "
            "`bound`, this predicate checks the register alone and does not "
            "additionally consult the trace graph's `sr_proposed` gap."
        ),
        "siblings": ["sr_total", "bound", "covered", "deferred", "validated"],
        "computed_by": ["src/factory/system/health.py"],
    },
    "deferred": {
        "term": "deferred",
        "group": "readiness-count",
        "label": "deferred",
        "gloss": "postponed by a human note or auto-deferred proposal",
        "definition": (
            "This word means two different, non-interchangeable counts. As "
            "a readiness count: how many of the bundle's member SRs carry "
            "at least one gap whose disposition is `deferred`, checked "
            "over ALL of that SR's gaps. Two independent triggers set that "
            "disposition: a human recorded `trace_deferred: <reason>` on "
            "the node's frontmatter, OR the SR is `proposed` (no binding "
            "yet) -- every `sr_proposed` gap is automatically deferred "
            "regardless of whether any reason was recorded, so a proposed "
            "SR with no human note still counts here. As a health COUNTER, "
            "the same word names a repo-wide tally of gaps with "
            "disposition `deferred` that EXCLUDES `sr_proposed` gaps "
            "specifically -- a proposed SR's automatic deferral is routed "
            "into the repo-wide `proposed` counter instead. The two "
            "`deferred` numbers can disagree even for the same repo state."
        ),
        "siblings": ["sr_total", "bound", "covered", "current", "validated", "dangling", "proposed"],
        "computed_by": [
            "src/factory/system/health.py",
            "src/factory/trace/gaps.py",
            "src/factory/trace/health.py",
        ],
    },
    "validated": {
        "term": "validated",
        "group": "readiness-count",
        "label": "validated",
        "gloss": "validation report shows a fresh pass for SR",
        "definition": (
            "As a readiness count: how many of the bundle's member SRs have "
            "a validation-report entry that passed and is not stale. As a "
            "timeline action, the same word names a decision-timeline "
            "event recording that a requirement was validated; this "
            "repo's timeline does not currently emit that action (its "
            "only real source, review decisions, maps to "
            "`approved`/`rejected`/`not-recorded`)."
        ),
        "siblings": ["sr_total", "bound", "covered", "current", "deferred"],
        "computed_by": ["src/factory/system/health.py", "src/factory/trace/validation_status.py"],
    },
    # -----------------------------------------------------------------
    # health-class (trace/health.py) -- the five slot classes on the
    # landing page's health strip. Denominator rule is the load-bearing
    # part of every entry below.
    # -----------------------------------------------------------------
    "task->plan": {
        "term": "task->plan",
        "group": "health-class",
        "label": "Tasks linked to a plan",
        "gloss": "share of tasks with a resolving source_plan",
        "denominator_rule": "Counts every task; satisfied when it names the plan it came from.",
        "definition": (
            "Denominator: every `task` node in the trace graph, one slot "
            "each. Satisfied: the task declares a `source_plan` edge at "
            "all -- `task_no_plan` is the only gap kind that unfills this "
            "slot. A `source_plan` edge whose target does not resolve to a "
            "real node (`task_plan_missing`) does NOT unfill the slot: it "
            "is counted straight into the separate `dangling` counter "
            "instead -- so a task with a broken `source_plan` link is "
            "reported as `dangling`, not as an unfilled `task->plan` slot, "
            "and counts toward this class's percentage as satisfied. A "
            "task marked `trace_exempt` removes its slot from the "
            "denominator instead of counting it unfilled."
        ),
        "siblings": ["task->SR", "plan->spec", "SR satisfied", "SR validated"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    "task->SR": {
        "term": "task->SR",
        "group": "health-class",
        "label": "Tasks linked to a requirement",
        "gloss": "share of tasks that declare a satisfies edge",
        "denominator_rule": "Counts every task; satisfied when it names at least one requirement it helps satisfy.",
        "definition": (
            "Denominator: every `task` node in the trace graph, one slot "
            "each (the same task also has a `task->plan` slot; they are "
            "counted independently). Satisfied: the task declares at least "
            "one `satisfies` edge (`task_no_sr` is the gap when it declares "
            "none). Exempt tasks remove their slot from the denominator."
        ),
        "siblings": ["task->plan", "plan->spec", "SR satisfied", "SR validated"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    "plan->spec": {
        "term": "plan->spec",
        "group": "health-class",
        "label": "Plans linked to a spec",
        "gloss": "share of plans that cite a spec_ref",
        "denominator_rule": "Counts every plan; satisfied when it cites the spec it followed.",
        "definition": (
            "Denominator: every `plan` node in the trace graph, one slot "
            "each. Satisfied: the plan declares at least one `spec_ref` "
            "edge (`plan_no_spec` is the gap when it declares none). Exempt "
            "plans remove their slot from the denominator rather than "
            "counting as unfilled."
        ),
        "siblings": ["task->plan", "task->SR", "SR satisfied", "SR validated"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    "SR satisfied": {
        "term": "SR satisfied",
        "group": "health-class",
        "label": "Requirements with a satisfying task",
        "gloss": "share of all SRs with a satisfying task",
        "denominator_rule": "Counts every requirement, including ones not yet decided on; satisfied when a task claims to satisfy it.",
        "definition": (
            "Denominator: every `sr` node in the trace graph -- the full "
            "repo-wide count, including proposed SRs with no decided "
            "binding yet, which is why this denominator (e.g. 181) is much "
            "larger than `SR validated`'s (e.g. 43): proposed SRs keep "
            "their `SR satisfied` slot (a requirement with no task is a gap "
            "whether or not it is bound) but lose their `SR validated` slot "
            "entirely (there is nothing to validate yet). Satisfied: at "
            "least one task declares `satisfies` for the SR "
            "(`sr_unsatisfied` is the gap when none does)."
        ),
        "siblings": ["task->plan", "task->SR", "plan->spec", "SR validated"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    "SR validated": {
        "term": "SR validated",
        "group": "health-class",
        "label": "Requirements with a passing validation",
        "gloss": "share of non-proposed SRs with a fresh pass",
        "denominator_rule": "Counts only requirements that have been decided on; satisfied when there's a passing validation that hasn't gone stale.",
        "definition": (
            "Denominator: every `sr` node in the trace graph MINUS every SR "
            "flagged `sr_proposed` (no decided binding yet) -- one expected "
            "slot is subtracted per proposed SR, which is the entire "
            "reason this denominator (e.g. 43) is far smaller than `SR "
            "satisfied`'s (e.g. 181): a requirement cannot be validated "
            "before someone has decided what to measure. Satisfied: the "
            "requirement has a validation-report entry with state `passed` "
            "that is not stale (`sr_unvalidatable`, `sr_unvalidated`, and "
            "`sr_stale` are the gaps that leave this slot unfilled; in "
            "principle an exempt `sr_stale` would also count as satisfied, "
            "but that case cannot actually happen since SR gaps can never "
            "be `exempt`)."
        ),
        "siblings": ["task->plan", "task->SR", "plan->spec", "SR satisfied"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    # -----------------------------------------------------------------
    # health-counter (trace/health.py compute_health) -- reported on
    # their own line, never folded into a class percentage.
    # -----------------------------------------------------------------
    "dangling": {
        "term": "dangling",
        "group": "health-counter",
        "label": "dangling",
        "gloss": "an edge points at a missing node",
        "definition": (
            "A count of structural defects, not unfilled slots: a "
            "`source_plan`/`upstream` edge whose target does not resolve to "
            "any real node (`dangling_upstream`, `task_plan_missing`), or a "
            "V-cycle edge (`parent_of`/`verified_by`/`demonstrates`/"
            "`evaluates`/`contains`/`illustrates`) whose source or target is "
            "missing (`dangling_reference`). This is a health COUNTER, not a "
            "trace disposition -- it never appears as a gap's `disposition` "
            "field, only as this repo-wide tally."
        ),
        "siblings": ["proposed"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/gaps.py"],
    },
    "proposed": {
        "term": "proposed",
        "group": "health-counter",
        "label": "proposed",
        "gloss": "an SR with no decided binding yet",
        "definition": (
            "A count of SRs whose frontmatter carries no `binding` key -- "
            "nobody has yet decided what measurement would satisfy them. "
            "Reported on its own line rather than folded into `deferred`, "
            "because counting it as an unfilled validation slot would "
            "punish recording a real, honest state. Like `dangling`, this "
            "is a health COUNTER, not a trace disposition."
        ),
        "siblings": ["dangling"],
        "computed_by": ["src/factory/trace/health.py", "src/factory/trace/model.py"],
    },
    # -----------------------------------------------------------------
    # timeline-actor (design SS7.4) -- closed vocabulary for a decision
    # event's actor.
    # -----------------------------------------------------------------
    "human": {
        "term": "human",
        "group": "timeline-actor",
        "label": "human",
        "gloss": "reserved actor value: a human decision-maker",
        "definition": (
            "A reserved value in the closed vocabulary of timeline actors, "
            "for a decision event whose recorded artifact names a human as "
            "the actor. The timeline's only real source today -- a run "
            "manifest's `reviews` array -- carries no actor field at all, "
            "so this repo's timeline never actually emits `human`; every "
            "real event's actor is `not-recorded`."
        ),
        "siblings": ["dev", "review", "validation", "orchestrator", "unknown", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "dev": {
        "term": "dev",
        "group": "timeline-actor",
        "label": "dev",
        "gloss": "reserved actor value: the orchestrator's dev step",
        "definition": (
            "A reserved value in the closed vocabulary of timeline actors, "
            "for a decision event attributed to the orchestrator's "
            "automated dev step. Not currently emitted, for the same "
            "reason as `human`: the recorded review artifact carries no "
            "actor field."
        ),
        "siblings": ["human", "review", "validation", "orchestrator", "unknown", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "review": {
        "term": "review",
        "group": "timeline-actor",
        "label": "review",
        "gloss": "reserved value: a review step or artifact",
        "definition": (
            "As a timeline actor, a reserved value for a decision "
            "attributed to a review step; not currently emitted (see "
            "`human`). As a citation kind, a reserved value for citing a "
            "review artifact directly; this repo's own review-decision "
            "citations are built with kind `decision` instead, pointing at "
            "the owning evidence manifest's `reviews[i]` entry -- `review` "
            "is declared in the schema but not constructed by any query in "
            "this repo today."
        ),
        "siblings": ["human", "dev", "validation", "orchestrator", "unknown", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "orchestrator": {
        "term": "orchestrator",
        "group": "timeline-actor",
        "label": "orchestrator",
        "gloss": "the pipeline controller itself, per the closed vocabulary",
        "definition": (
            "A reserved value in the closed vocabulary of timeline actors, "
            "for a decision event attributed to the pipeline's own control "
            "flow rather than a person or a specific node. Not currently "
            "emitted, for the same reason as `human`."
        ),
        "siblings": ["human", "dev", "review", "validation", "unknown", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "not-recorded": {
        "term": "not-recorded",
        "group": "timeline-actor",
        "label": "not recorded",
        "gloss": "the source artifact records no such field",
        "definition": (
            "The honest recorded absence, not a guess -- and it does double "
            "duty across two groups. As a timeline actor, the run "
            "manifest's `reviews[i]` record this repo reads has no field "
            "for an actor identity at all, so every real timeline event's "
            "actor is set to this value -- every review-decision actor in "
            "this repo actually carries this value today. As a timeline "
            "action, the same spelling is set when `reviews[i].decision` "
            "is anything other than `\"approve\"`/`\"reject\"` -- an "
            "unrecognized or absent decision value, not merely \"nobody "
            "decided yet\"."
        ),
        "siblings": ["human", "dev", "review", "validation", "orchestrator", "unknown"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    # -----------------------------------------------------------------
    # timeline-action (design SS7.4) -- closed vocabulary for a decision
    # event's action.
    # -----------------------------------------------------------------
    "approved": {
        "term": "approved",
        "group": "timeline-action",
        "label": "approved",
        "gloss": "a run manifest recorded decision: \"approve\"",
        "definition": (
            "The owning evidence manifest's `reviews[i].decision` field is "
            "exactly the string `\"approve\"`. This is one of the two "
            "actions this repo's timeline actually emits today, from the "
            "same recorded `reviews` array documented under "
            "`citation-kind`'s `decision` entry."
        ),
        "siblings": ["rejected", "validated", "repaired", "published", "stopped", "not-recorded"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    "rejected": {
        "term": "rejected",
        "group": "timeline-action",
        "label": "rejected",
        "gloss": "a run manifest recorded decision: \"reject\"",
        "definition": (
            "The owning evidence manifest's `reviews[i].decision` field is "
            "exactly the string `\"reject\"`. The other action this repo's "
            "timeline actually emits today."
        ),
        "siblings": ["approved", "validated", "repaired", "published", "stopped", "not-recorded"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    "repaired": {
        "term": "repaired",
        "group": "timeline-action",
        "label": "repaired",
        "gloss": "reserved action value: an automated fix",
        "definition": (
            "A reserved value in the closed vocabulary of timeline "
            "actions, for an event recording that something was repaired. "
            "Not currently emitted: its only recorded source "
            "(`reviews[i].decision`) only ever carries `approve` or "
            "`reject`, mapped to `approved`/`rejected`; anything else maps "
            "to `not-recorded`."
        ),
        "siblings": ["approved", "rejected", "validated", "published", "stopped", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "published": {
        "term": "published",
        "group": "timeline-action",
        "label": "published",
        "gloss": "reserved action value: a publish step",
        "definition": (
            "A reserved value in the closed vocabulary of timeline "
            "actions, for an event recording a publish action. Not "
            "currently emitted, for the same reason as `repaired`."
        ),
        "siblings": ["approved", "rejected", "validated", "repaired", "stopped", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "stopped": {
        "term": "stopped",
        "group": "timeline-action",
        "label": "stopped",
        "gloss": "reserved action value: a stop event",
        "definition": (
            "A reserved value in the closed vocabulary of timeline "
            "actions, for an event recording that a run or pipeline was "
            "stopped. Not currently emitted, for the same reason as "
            "`repaired`."
        ),
        "siblings": ["approved", "rejected", "validated", "repaired", "published", "not-recorded"],
        "computed_by": ["src/factory/system/models.py"],
    },
    # -----------------------------------------------------------------
    # citation-kind (design SS7.2) -- what kind of recorded source a
    # claim's citation points at.
    # -----------------------------------------------------------------
    "manifest": {
        "term": "manifest",
        "group": "citation-kind",
        "label": "evidence manifest",
        "gloss": "cites a durable evidence/runs/<run_id>.json file",
        "definition": (
            "As a citation kind, the cited path is a durable per-run "
            "evidence manifest, `evidence/runs/<run_id>.json` -- always a "
            "file, never a directory. As a scope kind for a "
            "timeline/citation subject (`kind: \"run\" | \"manifest\"`), it "
            "identifies the subject as the manifest record itself rather "
            "than the run's outcome."
        ),
        "siblings": ["task", "requirement", "review", "decision", "trace", "bundle", "session", "failure", "goal"],
        "computed_by": ["src/factory/system/_claims.py", "src/factory/system/story.py"],
    },
    "task": {
        "term": "task",
        "group": "citation-kind",
        "label": "task",
        "gloss": "cites the task's own T-*.md file",
        "definition": (
            "This word does three jobs. As a citation kind, the cited path "
            "is the task's own file under `tasks/` -- the same file the "
            "orchestrator's ledger loads task status from; used for both a "
            "bundle's `task:` member claim and its companion "
            "implementation-status claim. As a scope/subject kind, it "
            "identifies a subject as a task rather than an SR, run, or "
            "manifest -- e.g. the Story tab's own scope. As a `stops_at` "
            "value on the Reverse tab, `stops_at: \"task\"` means the "
            "walked run's own task did not resolve in the ledger at all -- "
            "the earliest possible stop in the file -> run -> task -> "
            "requirements chain, one step before the `satisfies` stop."
        ),
        "siblings": [
            "manifest", "requirement", "validation", "review", "decision",
            "trace", "bundle", "session", "failure", "goal", "sr", "run", "satisfies", "chain-complete",
        ],
        "computed_by": [
            "src/factory/system/queries.py",
            "src/factory/system/reverse.py",
            "src/factory/system/models.py",
        ],
    },
    "validation": {
        "term": "validation",
        "group": "citation-kind",
        "label": "validation",
        "gloss": "cites the validation-report.json file itself",
        "definition": (
            "As a citation kind, the cited path is "
            "`validation/validation-report.json` itself, attached to "
            "every SR's brief validation claim. This is an ACTIVELY "
            "constructed kind, unlike most of this table's reserved "
            "values. As a timeline actor, the same spelling is a reserved "
            "closed-vocabulary value for a decision attributed to the "
            "validation pipeline running automatically -- the timeline "
            "never emits it; see `not-recorded` for what it emits instead."
        ),
        "siblings": ["manifest", "task", "requirement", "review", "decision", "trace", "bundle", "session"],
        "computed_by": ["src/factory/system/queries.py", "src/factory/system/models.py"],
    },
    "requirement": {
        "term": "requirement",
        "group": "citation-kind",
        "label": "requirement",
        "gloss": "cites the SR/BR's own file under requirements/",
        "definition": (
            "The cited path is the requirement's own `SR-*.md` (or "
            "`BR-*.md`) file under `requirements/`. Used for a "
            "requirement's statement, upstream, binding, and validation "
            "claims alike."
        ),
        "siblings": ["manifest", "task", "review", "decision", "trace", "bundle", "session", "failure", "goal"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    "decision": {
        "term": "decision",
        "group": "citation-kind",
        "label": "decision",
        "gloss": "cites an ADR file or a review entry",
        "definition": (
            "The cited path is either an ADR document under `docs/adr/`, or "
            "an evidence manifest with an `anchor` naming the specific "
            "`reviews[i]` array entry it points at -- the sole source of "
            "signed review decisions. This is the kind actually used for "
            "every review-decision timeline event in this repo (not "
            "`review`)."
        ),
        "siblings": ["manifest", "task", "requirement", "review", "trace", "bundle", "session", "failure", "goal"],
        "computed_by": ["src/factory/system/queries.py"],
    },
    "failure": {
        "term": "failure",
        "group": "citation-kind",
        "label": "failure record",
        "gloss": "cites a failure record under docs/failures/",
        "definition": (
            "The cited path is a failure record, `docs/failures/FR-*.md`, "
            "loaded through `factory.memory.failure_record` -- the durable "
            "artifact that captures reproduction ref -> root cause -> "
            "rejected hypotheses -> fix -> regression guard. Introduced by "
            "Inc 8's durable-memory projection: a decision entry cites its "
            "ADR, a failure record and each of its rejected hypotheses cite "
            "the FR file itself (`factory.memory.durable`)."
        ),
        "siblings": ["manifest", "task", "requirement", "validation", "review", "decision", "trace", "bundle", "session", "goal"],
        "computed_by": ["src/factory/memory/durable.py"],
    },
    "goal": {
        "term": "goal",
        "group": "citation-kind",
        "label": "goal",
        "gloss": "cites a goal file under goals/",
        "definition": (
            "The cited path is a goal file under `goals/`, loaded through "
            "`factory.goals.registry` -- the measurable engineering "
            "contract (brief §5.3). Used by the durable-memory projection's "
            "open-goal entries (`factory.memory.durable`) so an open goal's "
            "entry carries a citation to the goal file that declares it."
        ),
        "siblings": ["manifest", "task", "requirement", "validation", "review", "decision", "trace", "bundle", "session", "failure"],
        "computed_by": ["src/factory/memory/durable.py"],
    },
    "trace": {
        "term": "trace",
        "group": "citation-kind",
        "label": "trace",
        "gloss": "cites a spec, plan, feature, metric, or goal",
        "definition": (
            "The cited path is one of the trace graph's other document "
            "kinds -- a spec, a plan, or a feat/metric/goal node -- "
            "resolved through the same loader the `factory.trace` command "
            "itself uses, never a second parser."
        ),
        "siblings": ["manifest", "task", "requirement", "review", "decision", "bundle", "session", "failure", "goal"],
        "computed_by": ["src/factory/system/queries.py", "src/factory/trace/model.py"],
    },
    "bundle": {
        "term": "bundle",
        "group": "citation-kind",
        "label": "bundle",
        "gloss": "cites the bundle's own declaration file under bundles/",
        "definition": (
            "As a citation kind, the cited path is the bundle's own "
            "declaration file under `bundles/`. As a scope kind, "
            "`\"bundle\"` is the `kind` value for `--scope bundle:<id>`. As "
            "the noun, a bundle is a declared feature-scope grouping of "
            "spec/plan/task/SR/feat/metric/goal members with a label and "
            "exact member refs -- no status or rationale of its own; "
            "readiness and health are always computed over its members."
        ),
        "siblings": ["manifest", "task", "requirement", "review", "decision", "trace", "session", "failure", "goal", "sr"],
        "computed_by": ["src/factory/system/bundles.py", "src/factory/system/models.py"],
    },
    "session": {
        "term": "session",
        "group": "citation-kind",
        "label": "session record",
        "gloss": "cites a fallback sessions/*.session.json when no manifest",
        "definition": (
            "As a citation kind, the cited path is a `sessions/*.session.json` "
            "record -- thinner than an evidence manifest by nature: no "
            "commit range, no changed files, no patch, because none was "
            "recorded. As a run's source, `\"session\"` means this "
            "particular run was reconstructed from that fallback record "
            "because no durable evidence manifest exists for it; "
            "`\"manifest\"` is the other, preferred source."
        ),
        "siblings": ["manifest", "task", "requirement", "review", "decision", "trace", "bundle", "failure", "goal"],
        "computed_by": ["src/factory/system/sessions.py", "src/factory/system/story.py"],
    },
    # -----------------------------------------------------------------
    # scope-kind -- union of SystemScopeKind (system-cli.ts:9: "bundle" |
    # "sr") and TimelineSubjectRef.kind (system-cli.ts:106: "task" | "sr" |
    # "run" | "manifest"). "bundle" and "task" are defined above under
    # citation-kind (each entry's definition covers this meaning too);
    # "run" and "sr" are new here.
    # -----------------------------------------------------------------
    "run": {
        "term": "run",
        "group": "scope-kind",
        "label": "run",
        "gloss": "a timeline/citation subject naming one evidence run",
        "definition": (
            "One legal value of a timeline or citation subject's `kind` -- "
            "identifies the subject as a specific evidence run (a "
            "`run_id`), as distinct from `manifest`, which names the file "
            "that recorded it."
        ),
        "siblings": ["manifest", "bundle", "sr", "task"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "sr": {
        "term": "sr",
        "group": "scope-kind",
        "label": "SR (scope/subject kind)",
        "gloss": "lowercase kind tag for an SR-scoped subject",
        "definition": (
            "The lowercase `kind` value used wherever a scope or subject "
            "ref names a requirement: for `--scope sr:<id>`, for a "
            "Matrix row's subject, and as one of a Timeline event's four "
            "legal subject kinds. Distinct from the noun `SR`, which names "
            "the requirement itself -- its file, statement, and binding -- "
            "not this kind tag."
        ),
        "siblings": ["bundle", "task", "run", "manifest"],
        "computed_by": ["src/factory/system/models.py", "pi-ext/factory-watch/src/system-cli.ts"],
    },
    # -----------------------------------------------------------------
    # disposition (trace/gaps.py:23) -- pending/exempt/deferred are the
    # only three; "dangling"/"proposed" above are counters, not this.
    # -----------------------------------------------------------------
    "pending": {
        "term": "pending",
        "group": "disposition",
        "label": "pending",
        "gloss": "the default: a real, unaddressed gap",
        "definition": (
            "The default disposition a gap gets when the node it belongs to "
            "carries neither `trace_exempt: true` nor a `trace_deferred` "
            "reason. A pending gap is a live defect -- it counts as "
            "unfilled in its health-class slot, and never reduces the "
            "class denominator the way `exempt` does."
        ),
        "siblings": ["exempt", "deferred"],
        "computed_by": ["src/factory/trace/gaps.py"],
    },
    "exempt": {
        "term": "exempt",
        "group": "disposition",
        "label": "exempt",
        "gloss": "waived by a recorded trace_exempt flag",
        "definition": (
            "The node's frontmatter declares `trace_exempt: true`. This "
            "removes the slot from the health-class denominator entirely "
            "rather than counting it unfilled -- an exempt gap does not "
            "drag the percentage down. SRs and BRs can never carry this "
            "disposition: a requirement's gap can be deferred, never "
            "waived outright."
        ),
        "siblings": ["pending", "deferred"],
        "computed_by": ["src/factory/trace/gaps.py"],
    },
    # -----------------------------------------------------------------
    # stops-at (system.reverse -- the file->run->task->requirements walk)
    # -----------------------------------------------------------------
    "satisfies": {
        "term": "satisfies",
        "group": "stops-at",
        "label": "satisfies",
        "gloss": "reverse walk stopped: task resolved, no satisfies",
        "definition": (
            "In `system reverse`'s file -> run -> task -> requirements walk, "
            "`stops_at: \"satisfies\"` means the task itself resolved in the "
            "ledger but declares no `satisfies` list, so the walk cannot "
            "continue to a requirement. The other named stop, `\"task\"`, "
            "means the run's own `task_id` did not resolve in the ledger at "
            "all -- one step earlier in the same chain."
        ),
        "siblings": ["chain-complete"],
        "computed_by": ["src/factory/system/reverse.py"],
    },
    "chain-complete": {
        "term": "chain-complete",
        "group": "stops-at",
        "label": "chain complete",
        "gloss": "display label for a null stops_at",
        "definition": (
            "The browser's rendering of `stops_at: null`, shown as "
            "\"null (chain complete)\" -- meaning the walk reached at "
            "least one requirement with no unresolved hop in between. "
            "Never a value written into the recorded JSON; `null` is the "
            "recorded value, `chain-complete` is only ever a rendered "
            "label for it."
        ),
        "siblings": ["satisfies"],
        "computed_by": ["src/factory/system/reverse.py", "pi-ext/factory-watch/src/system-renderers.ts"],
    },
    # -----------------------------------------------------------------
    # noun -- plain nouns the interface uses without defining ("scope",
    # "SR", "BR", "ADR", and the evidence-run/session-record/claim/span/
    # citation shapes). "bundle" is defined above under citation-kind.
    # -----------------------------------------------------------------
    "scope": {
        "term": "scope",
        "group": "noun",
        "label": "scope",
        "gloss": "what a page is about: bundle or SR",
        "definition": (
            "A `{kind, ref}` pointer naming what a page's brief/matrix/"
            "timeline/guide is about -- today always `bundle:<id>` or "
            "`sr:<id>` for `--scope`-driven commands, though the same "
            "shape is reused more broadly for declared bundle members and "
            "timeline/matrix subjects, which allow a wider set of kinds."
        ),
        "siblings": ["citation", "claim"],
        "computed_by": ["src/factory/system/models.py", "src/factory/system/queries.py"],
    },
    "SR": {
        "term": "SR",
        "group": "noun",
        "label": "SR (requirement)",
        "gloss": "a satisfaction requirement file under requirements/SR-*.md",
        "definition": (
            "A requirement declared in `requirements/SR-*.md`. Carries a "
            "statement, optional upstream requirements, and an optional "
            "binding (a harness/experiment/metric/assertion) that "
            "validation runs against. An SR with no binding is `proposed`; "
            "SRs and BRs are the only node kinds that can never be marked "
            "`trace_exempt`."
        ),
        "siblings": ["BR", "bundle"],
        "computed_by": ["src/factory/requirements/register.py", "src/factory/trace/model.py"],
    },
    "BR": {
        "term": "BR",
        "group": "noun",
        "label": "BR (business requirement)",
        "gloss": "same file convention as SR, requirements/BR-*.md",
        "definition": (
            "A requirement declared in `requirements/BR-*.md` -- the same "
            "id/title/frontmatter shape an SR gets, loaded as trace node "
            "kind `\"br\"`. Like an SR, a BR can never be marked "
            "`trace_exempt`, but unlike an SR it has no health-class slot "
            "of its own -- only `task`/`plan`/`sr` node kinds get one."
        ),
        "siblings": ["SR"],
        "computed_by": ["src/factory/trace/model.py"],
    },
    "ADR": {
        "term": "ADR",
        "group": "noun",
        "label": "ADR (architecture decision record)",
        "gloss": "a recorded decision doc, brief only",
        "definition": (
            "A decision document under `docs/adr/`. An ADR scope renders "
            "Brief only -- design and gaps but no validation matrix, no "
            "runs, and no reverse walk -- because those tabs would be "
            "permanently degraded for a document that is a decision "
            "record, not an implementation unit."
        ),
        "siblings": ["SR", "BR"],
        "computed_by": ["src/factory/system/adr.py", "src/factory/system/queries.py"],
    },
    "evidence run": {
        "term": "evidence run",
        "group": "noun",
        "label": "evidence run",
        "gloss": "one run_id in a task's story",
        "definition": (
            "One entry in a task's story (`StoryRun`): a `run_id`, its "
            "outcome, timestamps, optional commit range, and an "
            "implementation claim -- sourced either from a durable evidence "
            "manifest (`source: \"manifest\"`) or, when no manifest exists "
            "for that run, from a session record (`source: \"session\"`, "
            "which never carries changed files or a commit range)."
        ),
        "siblings": ["evidence manifest", "session record"],
        "computed_by": ["src/factory/system/story.py"],
    },
    "evidence manifest": {
        "term": "evidence manifest",
        "group": "noun",
        "label": "evidence manifest",
        "gloss": "the durable evidence/runs/<run_id>.json file for a run",
        "definition": (
            "The durable, schema-validated record of one run, "
            "`evidence/runs/<run_id>.json`, read through the same loader "
            "everywhere this package consumes it -- never a second parser. "
            "Carries the run's `implementation` (changed files, commit "
            "range), its `validation` array, and its `reviews` array (the "
            "sole source of signed review decisions)."
        ),
        "siblings": ["evidence run", "session record"],
        "computed_by": ["src/factory/evidence/manifests.py", "src/factory/system/_claims.py"],
    },
    "session record": {
        "term": "session record",
        "group": "noun",
        "label": "session record",
        "gloss": "a thinner sessions/*.session.json fallback, no changed files",
        "definition": (
            "A `sessions/*.session.json` file, used as a fallback for a "
            "task run when no durable evidence manifest exists for it. "
            "Thinner by nature -- no commit range, no changed files, no "
            "patch -- because a session record never captures those; where "
            "both exist for the same `run_id`, the manifest always wins and "
            "the session record is never read into the story."
        ),
        "siblings": ["evidence run", "evidence manifest"],
        "computed_by": ["src/factory/system/sessions.py", "src/factory/system/story.py"],
    },
    "claim": {
        "term": "claim",
        "group": "noun",
        "label": "claim",
        "gloss": "the shared record shape: kind, text, citations, freshness",
        "definition": (
            "The shared record shape every fact the navigator renders is "
            "packaged as: a `kind` (recorded/derived/synthesized/missing), "
            "`text`, a `freshness` verdict, and the `citations` it is "
            "traceable back to. A claim also carries `spans` -- but only "
            "when `kind` is `synthesized`."
        ),
        "siblings": ["span", "citation"],
        "computed_by": ["src/factory/system/models.py"],
    },
    "span": {
        "term": "span",
        "group": "noun",
        "label": "span",
        "gloss": "a verbatim quoted excerpt, verified against its citation",
        "definition": (
            "A verbatim quoted excerpt of source text (`text`) plus the "
            "index of the citation it was pulled from (`citation_index`), "
            "present only on `synthesized` claims. The cited file is "
            "independently re-read to confirm the candidate text is a "
            "literal substring of it before a span is ever emitted -- "
            "never a paraphrase, never a best-effort quote."
        ),
        "siblings": ["claim", "citation"],
        "computed_by": ["src/factory/system/models.py", "src/factory/system/guide.py"],
    },
    "citation": {
        "term": "citation",
        "group": "noun",
        "label": "citation",
        "gloss": "a recorded source a claim cites",
        "definition": (
            "A pointer at the recorded artifact a claim was built from: a "
            "`kind` (see the `citation-kind` group), a `path`, an optional "
            "`sha256` of the file's content at read time (null when the "
            "file could not be read, which is what makes a claim "
            "`degraded`), and an optional `anchor` naming a specific "
            "location inside the file, such as `reviews[2]`."
        ),
        "siblings": ["claim", "span"],
        "computed_by": ["src/factory/system/models.py", "src/factory/system/_claims.py"],
    },
}


def build_vocabulary() -> dict:
    return {"version": 1, "terms": VOCABULARY}


# ---------------------------------------------------------------------------
# PANELS (design Component 4) -- one persistent orientation line per tab,
# shown beneath the tab strip for whichever panel is active. `TABS_BY_KIND`
# (pi-ext/factory-watch/src/system-bootstrap.ts) holds thirteen tab ids; this
# table needs exactly one entry per id, or the completeness test in
# system-page-dom.test.ts fails.
#
# The seven below marked "fact-checked against the spec table" carry wording
# copied verbatim from the design doc's Component 4 table (already
# fact-checked there against their renderers). The remaining six -- Vcycle,
# Validation, Feature, Goal, Sim, Diagram -- were fact-checked here, during
# this task, by reading their renderers directly:
#   Vcycle:     pi-ext/factory-watch/src/system-vcycle-view.ts + system/vcycle.py
#   Validation: pi-ext/factory-watch/src/system-validation-view.ts +
#               queries.query_validation + trace/validation_status.py
#   Feature:    pi-ext/factory-watch/src/system-feature-view.ts (renderFeature)
#   Goal:       pi-ext/factory-watch/src/system-goal-view.ts + queries.query_goal
#   Sim:        pi-ext/factory-watch/src/system-sim-view.ts +
#               queries.query_simulation_run
#   Diagram:    pi-ext/factory-watch/src/system-diagram-view.ts +
#               queries.query_diagram
# -----------------------------------------------------------------
PANELS: dict[str, dict] = {
    "Brief": {
        "label": "Brief",
        "what_it_shows": "Every claim this scope makes, with the evidence behind it.",
        "how_to_read": (
            "The badge says where the claim came from: copied from a file, "
            "computed, scaffold text wrapped around a verbatim quote, or "
            "missing -- a claim can be recorded as absent."
        ),
    },
    "Matrix": {
        "label": "Matrix",
        "what_it_shows": (
            "Whether each requirement's validation has run, and what it "
            "concluded."
        ),
        "how_to_read": (
            "`never-run` means no result was ever recorded -- not that it "
            "failed."
        ),
    },
    "Timeline": {
        "label": "Timeline",
        "what_it_shows": "Decisions recorded against this scope, in a deterministic recorded order.",
        "how_to_read": (
            "An actor of `not-recorded` means the record does not say who "
            "decided."
        ),
    },
    "Guide": {
        "label": "Guide",
        "what_it_shows": (
            "A prose walkthrough: fixed scaffolding with verbatim quotes "
            "inserted into it."
        ),
        "how_to_read": (
            "The quoted spans are verbatim from their sources; the prose "
            "around them is template text, NOT derived from the quotes."
        ),
    },
    "Trace": {
        "label": "Trace",
        "what_it_shows": (
            "The V-cycle chain: requirement, the tasks satisfying it, and "
            "their plans and specs."
        ),
        "how_to_read": (
            "A hop reading `unresolved` covers two cases: no link was ever "
            "recorded, or a link exists whose target cannot be found."
        ),
    },
    # -- Fact-checked during Task 4, against their real renderers. --------
    "Vcycle": {
        "label": "V-cycle",
        "what_it_shows": (
            "The full V-cycle for this requirement or feature: what defines "
            "it (needs through code) on one side, what verifies it (unit "
            "through system validation) on the other, plus its goals, "
            "metrics, and runs."
        ),
        "how_to_read": (
            "Each node's colour comes from its own recorded validation, "
            "goal, or task status; a band with nothing recorded reads "
            "'none recorded' rather than being left blank."
        ),
    },
    "Validation": {
        "label": "Validation",
        "what_it_shows": (
            "This requirement's recorded validation result, the goals "
            "bound to it, the simulation runs that declare it, "
            "and the metrics those goals evaluate."
        ),
        "how_to_read": (
            "The raw state comes from the validation report alone; the "
            "goal-aware status beside it is judged separately: `REGRESSED` "
            "if any bound goal regressed, `VALIDATED` only if every bound "
            "goal reached its target, `VERIFICATION_PENDING` if goals are "
            "bound but neither, or `not recorded` when no goal is bound "
            "to this requirement at all."
        ),
    },
    "Feature": {
        "label": "Feature",
        "what_it_shows": (
            "This feature's dossier: its intent, the requirements it "
            "covers, its design records, implementation files, tasks and "
            "their runs, tests, simulations, goals, and recent changes."
        ),
        "how_to_read": (
            "Every section renders even when nothing is recorded for it -- "
            "an absent section reads 'none recorded' or 'not recorded' "
            "rather than being left out."
        ),
    },
    "Story": {
        "label": "Story",
        "what_it_shows": "Every recorded run of this task, and what each one changed.",
        "how_to_read": (
            "A run sourced from a session has no commit range; only "
            "evidence manifests record one."
        ),
    },
    "Reverse": {
        "label": "Reverse",
        "what_it_shows": "Which requirement this file traces back to, and through which run.",
        "how_to_read": "\"Stops at\" names the first hop that did not resolve.",
    },
    "Goal": {
        "label": "Goal",
        "what_it_shows": (
            "This goal's contract and current state: the requirements and "
            "feature it belongs to, the metric and target it is measured "
            "against, its latest evidence, and its full recorded history."
        ),
        "how_to_read": (
            "The state badge is whatever was last recorded; History lists "
            "every past state in order, not just the latest one."
        ),
    },
    "Sim": {
        "label": "Simulation",
        "what_it_shows": (
            "One recorded simulation run: its experiment, feature, "
            "requirements, goals, commit, result, per-metric values, and a "
            "link to its recording."
        ),
        "how_to_read": (
            "A field with nothing recorded for it -- no commit, no "
            "recording, no metrics -- renders 'not recorded' or 'none "
            "recorded' explicitly rather than being omitted."
        ),
    },
    "Diagram": {
        "label": "Diagram",
        "what_it_shows": (
            "One diagram's already-committed HTML file, embedded directly, "
            "plus its recorded title."
        ),
        "how_to_read": (
            "The panel never generates or re-derives a diagram -- when the "
            "diagram file is missing or its declared path is invalid, it "
            "states that explicitly instead."
        ),
    },
    "Catchup": {
        "label": "Catch me up",
        "what_it_shows": (
            "The deterministic delta for this feature since your last "
            "recorded review: PRs merged, requirements and ADRs changed, "
            "new experiments run, goals reached or regressed, metric "
            "changes, and new open items."
        ),
        "how_to_read": (
            "Every field is computed, never an LLM summary -- a feature "
            "with no recorded review states that plainly, and a delta "
            "with no changes says so instead of rendering empty."
        ),
    },
}


def build_panels() -> dict:
    return {"version": 1, "panels": PANELS}
