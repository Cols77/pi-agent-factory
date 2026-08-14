"""What to do about each gap, and the exact command that does it.

Static data, inlined into the page at render time (design
`2026-08-14-system-navigator-comprehension-layer-design.md` Component 3). The
navigator only ever displays these commands and copies them to the
clipboard; it never runs one -- write operations are out of scope here.

`{id}` is the bare identifier the target command expects (e.g. `SR-121`,
`T-055`), `{ref}` the canonical ref (`sr:SR-121`). Every current command
takes a bare identifier, so every template below uses `{id}`. Any other
placeholder (a plan filename, a spec filename, a measurement name) is
written `<like-this>` -- a human value the browser never fills in.

Keys are exactly the eleven `GapKind` values (`trace/gaps.py:9`) plus the
sixteen browser-decided absence states named in the design doc -- each an
explicit `if (!x.length)` (or equivalent) branch in `system-renderers.ts` /
`system-bootstrap.ts`, so the browser always knows which key applies without
interpreting any free text.
"""
from __future__ import annotations

ABSENCE_STATES: tuple[str, ...] = (
    "no_claims", "no_matrix_rows", "no_timeline_events", "no_guide_sections",
    "no_runs", "no_requirements", "no_changed_files", "no_commit_range",
    "no_trace", "no_traversal_step", "no_bundles", "no_description",
    "traversal_not_applicable", "matrix_never_run", "unbundled_artifact",
    "unresolved_ref",
)

REMEDIATION: dict[str, dict] = {
    # -- GapKind: trace/gaps.py:9, produced by find_gaps() ------------------
    "task_no_sr": {
        "state": "task_no_sr",
        "headline": "Task satisfies no requirement",
        "what_it_means": (
            "This task declares no `satisfies` edge at all "
            "(gaps.py: \"task declares no satisfies\")."
        ),
        "why_it_matters": (
            "A task with no satisfies edge can't be counted toward any "
            "requirement's coverage, so the work it represents is invisible "
            "to the trace graph."
        ),
        "command": "uv run python -m factory.trace link {id} --satisfies <SR-id>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "task_no_plan": {
        "state": "task_no_plan",
        "headline": "Task declares no source plan",
        "what_it_means": (
            "This task declares no `source_plan` edge at all "
            "(gaps.py: \"task declares no source_plan\")."
        ),
        "why_it_matters": (
            "Without a source_plan, the task->plan->spec chain has nothing "
            "to walk, so its Trace tab and the working traversal can't "
            "reach the plan or spec it came from."
        ),
        "command": "uv run python -m factory.trace link {id} --source-plan <plan-filename>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "task_plan_missing": {
        "state": "task_plan_missing",
        "headline": "Task's source plan does not exist",
        "what_it_means": (
            "This task's recorded `source_plan` points at a plan node id "
            "that isn't in the trace graph "
            "(gaps.py: \"source_plan target missing: <id>\")."
        ),
        "why_it_matters": (
            "The link was recorded but the plan it names is gone or was "
            "never there, so the task's plan hop dead-ends instead of "
            "resolving."
        ),
        "command": "uv run python -m factory.trace link {id} --source-plan <existing-plan-filename>",
        "command_kind": "shell",
        "severity": "failure",
    },
    "plan_no_spec": {
        "state": "plan_no_spec",
        "headline": "Plan references no spec",
        "what_it_means": (
            "This plan declares no `spec_ref` edge at all "
            "(gaps.py: \"plan references no spec\")."
        ),
        "why_it_matters": (
            "Without a spec_ref, the plan's design rationale can't be "
            "traced back to the spec that authorized it."
        ),
        "command": "uv run python -m factory.trace link {id} --spec <spec-filename>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "dangling_upstream": {
        "state": "dangling_upstream",
        "headline": "Upstream reference points nowhere",
        "what_it_means": (
            "This node's recorded `upstream` edge names a node id that "
            "isn't in the trace graph "
            "(gaps.py: \"upstream target missing: <id>\")."
        ),
        "why_it_matters": (
            "The chain from business requirement down to this node is "
            "broken at the upstream hop, so its higher-level justification "
            "can't be traced."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "failure",
    },
    "sr_unsatisfied": {
        "state": "sr_unsatisfied",
        "headline": "No task satisfies this requirement",
        "what_it_means": (
            "No task in the ledger declares a `satisfies` edge to {id} "
            "(gaps.py: \"no task declares satisfies for this SR\")."
        ),
        "why_it_matters": (
            "Nothing implements it yet, so it cannot be validated and the "
            "feature it belongs to stays weak."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "sr_proposed": {
        "state": "sr_proposed",
        "headline": "Requirement's binding is not yet decided",
        "what_it_means": (
            "This SR is `proposed`: accepted in substance, but it carries "
            "no measurement binding yet (gaps.py: \"binding not yet "
            "decided\")."
        ),
        "why_it_matters": (
            "A proposed SR can never be validated -- there is no "
            "experiment, metric, or assertion recorded to check it "
            "against."
        ),
        "command": (
            "uv run python -m factory.requirements bind {id} "
            "--experiment <name> --metric <metric> --assert <expression>"
        ),
        "command_kind": "shell",
        "severity": "absence",
    },
    "sr_unvalidatable": {
        "state": "sr_unvalidatable",
        "headline": "Validation could not run",
        "what_it_means": (
            "This SR's recorded validation state is `error`: the harness "
            "ran but produced no verdict "
            "(validation_status.py `SrState`; gaps.py surfaces the "
            "recorded error, or \"validation could not run\" if none was "
            "recorded). This gap only fires once the SR already has a "
            "binding (gaps.py:90-108's `else` branch of `if node.proposed`, "
            "where `proposed` itself means \"no binding\" -- "
            "trace/model.py:73) -- the binding exists, so `factory."
            "requirements bind` is not the fix."
        ),
        "why_it_matters": (
            "An errored harness leaves the requirement's actual status "
            "unknown -- it is neither confirmed working nor confirmed "
            "broken. If the recorded binding names a harness that isn't "
            "actually configured, re-running validation surfaces that "
            "configuration error directly rather than silently passing; "
            "no command in the current surface repairs a missing harness "
            "declaration -- that still requires editing the binding by "
            "hand."
        ),
        "command": "uv run python -m factory.validation run --satisfies {id}",
        "command_kind": "shell",
        "severity": "failure",
    },
    "sr_unvalidated": {
        "state": "sr_unvalidated",
        "headline": "Requirement was never validated",
        "what_it_means": (
            "No entry for this SR exists in the validation report "
            "(gaps.py: \"absent from validation report\" -- status is "
            "absent, or its state is `never_validated`)."
        ),
        "why_it_matters": (
            "A bound requirement with no validation entry has never been "
            "checked against its own metric, so passing or failing is "
            "still unknown."
        ),
        "command": "uv run python -m factory.validation run --satisfies {id}",
        "command_kind": "shell",
        "severity": "absence",
    },
    "sr_stale": {
        "state": "sr_stale",
        "headline": "Validation result is stale",
        "what_it_means": (
            "The recorded validation result predates a later change to "
            "this SR's statement or binding "
            "(gaps.py: \"result predates a change to statement or "
            "binding\")."
        ),
        "why_it_matters": (
            "The passing or failing result on file no longer reflects "
            "what the requirement currently says or how it's measured, so "
            "it can't be trusted as current evidence."
        ),
        "command": "uv run python -m factory.validation run --satisfies {id}",
        "command_kind": "shell",
        "severity": "failure",
    },
    "dangling_reference": {
        "state": "dangling_reference",
        "headline": "Verification-cycle edge points nowhere",
        "what_it_means": (
            "A recorded verification-cycle edge (`parent_of`, "
            "`verified_by`, `demonstrates`, `evaluates`, `contains`, or "
            "`illustrates`) names a source or target node id that isn't "
            "in the trace graph (gaps.py: \"<kind> source/target "
            "missing: <id>\")."
        ),
        "why_it_matters": (
            "The V-cycle view (design intent paired with its verifying "
            "evidence) can't be walked past this point for this node."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "failure",
    },
    # -- Browser-decided absence states --------------------------------------
    "no_claims": {
        "state": "no_claims",
        "headline": "No claims recorded",
        "what_it_means": (
            "The Brief tab's claims list came back empty for this scope "
            "(`query_brief`, queries.py) -- rendered as \"No claims "
            "recorded for this scope.\" (system-renderers.ts renderBrief)."
        ),
        "why_it_matters": (
            "The Brief tab has nothing to show about this scope until its "
            "underlying register and trace data exist."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_matrix_rows": {
        "state": "no_matrix_rows",
        "headline": "No validation rows recorded",
        "what_it_means": (
            "The Matrix tab's rows list came back empty for this scope "
            "(`query_matrix` found no sr: members to report on) -- "
            "rendered as \"No validation rows recorded for this scope.\" "
            "(system-renderers.ts renderMatrix)."
        ),
        "why_it_matters": (
            "With no rows, there is nothing here to confirm this scope's "
            "requirements are actually validated."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_timeline_events": {
        "state": "no_timeline_events",
        "headline": "No recorded decisions",
        "what_it_means": (
            "The Timeline tab's events list came back empty for this "
            "scope (`query_timeline`) -- rendered as \"No recorded "
            "decisions for this scope.\" (system-renderers.ts "
            "renderTimeline)."
        ),
        "why_it_matters": (
            "Without timeline events, there's no recorded history of "
            "what was decided and when for this scope."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_guide_sections": {
        "state": "no_guide_sections",
        "headline": "No guide sections recorded",
        "what_it_means": (
            "The Guide tab's sections list came back empty for this "
            "scope (`query_guide`) -- rendered as \"No guide sections "
            "recorded for this scope.\" (system-renderers.ts renderGuide)."
        ),
        "why_it_matters": (
            "The synthesized narrative has nothing recorded to draw on "
            "for this scope."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_runs": {
        "state": "no_runs",
        "headline": "No recorded runs",
        "what_it_means": (
            "This task's Story tab has no recorded runs -- rendered as "
            "\"No recorded runs for this task.\" "
            "(system-renderers.ts renderStory)."
        ),
        "why_it_matters": (
            "Without a run, there is no execution evidence that this "
            "task was ever actually worked."
        ),
        "command": "/factory-run {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_requirements": {
        "state": "no_requirements",
        "headline": "No requirements recorded on this task",
        "what_it_means": (
            "This task's Story tab shows \"no requirements recorded\": "
            "the task declares no `satisfies` edges (story.py) -- the "
            "same condition the `task_no_sr` trace gap reports."
        ),
        "why_it_matters": (
            "A task with no requirement link can't be shown as "
            "implementing anything the system is tracking."
        ),
        "command": "uv run python -m factory.trace link {id} --satisfies <SR-id>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "no_changed_files": {
        "state": "no_changed_files",
        "headline": "No changed files recorded",
        "what_it_means": (
            "This run's implementation claim has an empty `changed_files` "
            "list -- rendered as \"no changed files recorded\" "
            "(system-renderers.ts renderChangedFiles)."
        ),
        "why_it_matters": (
            "Without a changed-files list, this run's evidence can't "
            "show what it actually touched."
        ),
        "command": "/factory-run {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_commit_range": {
        "state": "no_commit_range",
        "headline": "No commit range recorded",
        "what_it_means": (
            "This run has no `start_commit`/`result_commit` recorded -- "
            "rendered as \"commit range not recorded\" "
            "(system-renderers.ts renderCommitRange)."
        ),
        "why_it_matters": (
            "Without a commit range, this run's change can't be located "
            "in git history."
        ),
        "command": "/factory-run {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_trace": {
        "state": "no_trace",
        "headline": "No trace recorded for this scope",
        "what_it_means": (
            "The Trace tab found no SR refs to invert for this scope -- "
            "rendered as \"No trace recorded for this scope. See the "
            "Story or Reverse tabs.\" (system-renderers.ts renderTrace)."
        ),
        "why_it_matters": (
            "With no SR refs to walk, the requirement -> task -> plan -> "
            "spec chain can't be shown for this scope."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_traversal_step": {
        "state": "no_traversal_step",
        "headline": "Traversal step not recorded",
        "what_it_means": (
            "One step of the working traversal (tasks, design, or files) "
            "came back with no values -- rendered as \"Not recorded\" "
            "for that step (system-bootstrap.ts renderTraversal / "
            "addStep)."
        ),
        "why_it_matters": (
            "The requirement -> tasks -> design -> files spine has a gap "
            "at this step, so the working traversal stops short."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_bundles": {
        "state": "no_bundles",
        "headline": "No features defined yet",
        "what_it_means": (
            "A feature bundle groups the requirements, tasks, and "
            "decisions you read together to understand one part of the "
            "system. Bundles are hand-authored, not generated: create "
            "`bundles/<id>.json` with `id`, `label`, and `members` (a "
            "list of `sr:`/`task:`/`spec:`/`plan:`/... refs), and "
            "optionally a `description` of at most 280 characters."
        ),
        "why_it_matters": (
            "Bundles are how this project is browsed, so until one "
            "exists the directory stays empty. The command below only "
            "checks a draft file you've already written -- its own "
            "docstring says it \"proposes nothing and writes nothing; "
            "the draft is judged, not generated\" (system/cli.py:103-111) "
            "-- there is no CLI that creates the bundle file for you."
        ),
        "command": "uv run python -m factory.system bundle check --draft <path>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "no_description": {
        "state": "no_description",
        "headline": "No description recorded",
        "what_it_means": (
            "No description is recorded for this artifact: a bundle has "
            "no `description` field, or a spec/plan has none of the "
            "named sections the label index looks for (`Purpose`, "
            "`Goal`, `Problem`, `Overview`, `Summary`, or a plan's "
            "`**Goal:**` line -- design Component 1)."
        ),
        "why_it_matters": (
            "Without a recorded description, the card that opens on "
            "hover or focus has nothing to show beyond the id and title. "
            "For a bundle, add a `description` (<=280 characters) to its "
            "hand-authored `bundles/<id>.json` by hand, then use the "
            "command below to check it -- the command validates a draft "
            "you edit yourself; it does not write the field for you "
            "(system/cli.py:103-111). For a spec or plan, there is no "
            "CLI at all -- add the named section or `**Goal:**` line "
            "directly in the document."
        ),
        "command": "uv run python -m factory.system bundle check --draft <path>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "traversal_not_applicable": {
        "state": "traversal_not_applicable",
        "headline": "Traversal doesn't apply to this scope",
        "what_it_means": (
            "Traversal only applies to bundle:/sr: scopes; task:/file: "
            "scopes show \"Traversal is not applicable for this scope.\" "
            "instead (system-bootstrap.ts resetScopeEvidence)."
        ),
        "why_it_matters": (
            "This is expected behavior for the current scope kind, not a "
            "defect -- there is nothing to remediate here."
        ),
        "command": "/system",
        "command_kind": "slash",
        "severity": "absence",
    },
    "matrix_never_run": {
        "state": "matrix_never_run",
        "headline": "Requirement was never validated",
        "what_it_means": (
            "This Matrix row's status is `never_run`: the SR resolves and "
            "carries a binding, but `_sr_matrix_row` found no entry for "
            "it in the validation report (`status is None and not "
            "report_corrupt` -> `MatrixStatus.NEVER_RUN`, summary "
            "\"never validated\" -- queries.py:1026-1034). This is "
            "distinct from an SR ref that doesn't resolve at all, which "
            "`_sr_missing_matrix_row` reports separately as `unknown` / "
            "\"sr does not exist\"."
        ),
        "why_it_matters": (
            "A row that has never run carries no evidence either way -- "
            "it is not passing, not failing, simply unchecked."
        ),
        "command": "uv run python -m factory.validation run --satisfies {id}",
        "command_kind": "shell",
        "severity": "absence",
    },
    "unbundled_artifact": {
        "state": "unbundled_artifact",
        "headline": "Not a member of any bundle",
        "what_it_means": (
            "This artifact is not listed as a member of any bundle "
            "declaration (`factory.system coverage`'s `unbundled` list, "
            "bundles.py)."
        ),
        "why_it_matters": (
            "Unbundled artifacts are unreachable by browsing the "
            "feature directory -- only a direct ref or the Trace tab "
            "reaches them. To fix this, add this ref to the `members` "
            "list of an existing (or new) hand-authored "
            "`bundles/<id>.json` -- the command below only checks that "
            "edit; it does not add the membership for you "
            "(system/cli.py:103-111, \"the draft is judged, not "
            "generated\")."
        ),
        "command": "uv run python -m factory.system bundle check --draft <path>",
        "command_kind": "shell",
        "severity": "absence",
    },
    "unresolved_ref": {
        "state": "unresolved_ref",
        "headline": "Reference does not resolve",
        "what_it_means": (
            "A ref shown on this page (a member-of bundle id, a "
            "satisfies/upstream target, a trace hop) doesn't resolve to "
            "any node in the label index; the browser renders the raw "
            "string plus the note \"not in the label index\" (design "
            "Component 1)."
        ),
        "why_it_matters": (
            "A ref that can't resolve means the id it names is either "
            "misspelled or was never created, so whatever it points at "
            "can't be reached from here. `/trace-fix` only helps when "
            "the broken ref is a trace edge (satisfies/source_plan/"
            "spec_ref/upstream) -- for the `member_of` flavour of this "
            "gap (a bundle listing a member ref that doesn't resolve), "
            "`factory.trace link` has no `--member-of` flag, so the fix "
            "is to hand-edit the bundle's `members` list directly; "
            "running `/trace-fix {id}` will not touch it."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "failure",
    },
}


def build_remediation() -> dict:
    return {"version": 1, "states": REMEDIATION}
