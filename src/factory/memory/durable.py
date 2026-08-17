"""Durable-memory projection: decisions, failures, hypotheses, goals, conflicts.

Inc 8 Task 2. Turns the *canonical* engineering memory artifacts a clean
session must be able to recover from into one provenance-carrying read:

- **decisions** — the SCC SP-A `adr:` kind, loaded through
  `factory.system.adr.load_adrs` (never a re-glob);
- **failure records** — `docs/failures/FR-*.md`, loaded through
  `factory.memory.failure_record.load_failures`;
- **rejected hypotheses** — the `rejected_hypotheses` arrays of those
  records, surfaced with their own evidence refs;
- **open goals** — goals whose lifecycle state is not terminal, loaded
  through `factory.goals.registry.load_goals`;
- **conflicts** — structural contradictions between memory links and the
  artifacts they cite (a `reproduced_by` run that no evidence manifest
  records, a `superseded_by` ADR that no ADR declares, a hypothesis whose
  `run:` evidence does not exist). Both sides are shown, never silently
  resolved (brief §5.6 #4). Deeper evidence-vs-note fingerprint comparison
  is Inc 8 Task 3's `conflict.py`; this module only surfaces what the
  composed loaders can already prove.

Discipline (brief §5.6, D3, D9): this is durable memory, not an archive. The
projection LINKS canonical artifacts with provenance citations — it never
re-states requirement/ADR/evidence prose. Decisions carry id/title/status/
superseded_by and a citation to the ADR file; the ADR's `## Decision` body is
left in the file. Failure records carry their frontmatter fields and a
citation to the record file; the record's own root-cause prose is the
record's content, never re-quoted here. Everything is deterministic: order
by declared id (ADR/FR id, goal id), never by mtime, and scope resolution is
exact (`feat:`/`sr:`/`goal:`/`adr:`/`fr:` ids must match a declared id — no
fuzzy matching).
"""
from __future__ import annotations

from pathlib import Path

from factory.evidence import manifests as evidence_manifests
from factory.goals import registry as goal_registry
from factory.memory.failure_record import load_failures
from factory.system import adr as adr_module
from factory.system import bundles
from factory.system._claims import evidence_dir as _evidence_dir
from factory.system._claims import fresh as _fresh
from factory.system._claims import sha256_file as _sha256_file
from factory.system.models import (
    CitationKind,
    SystemCitation,
    to_dict,
)

# Goal lifecycle states that are terminal (spec §13): a goal that is REACHED
# or NOT_REACHED has a recorded outcome and is no longer open. Everything
# else (DECLARED, ACTIVE, EVALUATING, REGRESSED, BLOCKED) is still open.
_TERMINAL_GOAL_STATES = {"REACHED", "NOT_REACHED"}

# Scope kinds `query_memory` accepts. `bundle:`/`task:`/`file:`/`diag:`/
# `metric:` are system-navigator scopes, not memory scopes — memory is
# anchored on the artifacts it projects (feat/sr via declared links, goal/
# adr/fr by exact id).
_MEMORY_SCOPE_KINDS = ("feat", "sr", "goal", "adr", "fr")


def _parse_memory_scope(scope_ref: str) -> tuple[str, str]:
    """`all` or `kind:id`; anything else is rejected outright (no fuzzy fallback).

    The identifier is always a `str` -- `all` uses an empty (unused) one so
    callers never have to handle `None` for the exact-ref kinds.
    """
    if scope_ref == "all":
        return "all", ""
    kind, sep, identifier = scope_ref.partition(":")
    if not sep or kind not in _MEMORY_SCOPE_KINDS or not identifier:
        raise ValueError(
            f"invalid scope ref {scope_ref!r}: unsupported scope kind or malformed ref "
            f"(expected all, feat:<id>, sr:<id>, goal:<id>, adr:<id> or fr:<id>)"
        )
    return kind, identifier


def _decision_citation(path: Path) -> SystemCitation:
    return SystemCitation(kind=CitationKind.DECISION, path=str(path), sha256=_sha256_file(path))


def _failure_citation(path: Path) -> SystemCitation:
    return SystemCitation(kind=CitationKind.FAILURE, path=str(path), sha256=_sha256_file(path))


def _goal_citation(path: Path) -> SystemCitation:
    return SystemCitation(kind=CitationKind.GOAL, path=str(path), sha256=_sha256_file(path))


def _run_ids(repo_root: Path) -> set[str]:
    """Every run id recorded in evidence manifests, both shapes (§20 `run` and
    v1 `run_id`). Absent or empty evidence is a legitimate state."""
    ids: set[str] = set()
    for manifest in evidence_manifests.list_run_manifests(_evidence_dir(repo_root)):
        for key in ("run", "run_id"):
            value = manifest.get(key)
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


def _run_ref_missing(repo_root: Path, run_ref: str) -> bool:
    """True when `run_ref` is a `run:<id>` ref whose id no evidence manifest
    records. Non-`run:` refs (task refs, etc.) are not checked here — only
    the evidence link this projection can prove."""
    if not run_ref.startswith("run:"):
        return False
    run_id = run_ref[len("run:"):]
    return bool(run_id) and run_id not in _run_ids(repo_root)


def _decision_links(repo_root: Path, feat_ids: list[str], sr_ids: list[str]) -> list[str]:
    """ADR ids linked to a scope through bundle membership (SP-A's bundle map
    is the sole recorded link from a feature/SR to its design decisions —
    `queries._traversal_for_sr` reads the same link). Exact ref matching,
    declared data only, no prose inference."""
    linked: list[str] = []
    for ref in [f"feat:{f}" for f in feat_ids] + [f"sr:{s}" for s in sr_ids]:
        for bundle_id in bundles.bundles_containing(repo_root, ref):
            try:
                bundle = bundles.load_bundle(repo_root / "bundles", bundle_id)
            except (OSError, ValueError):
                continue
            for member in bundle.members:
                if member.kind == "adr" and member.ref not in linked:
                    linked.append(member.ref)
    return linked


def _decision_payload(doc: adr_module.AdrDocument) -> dict:
    """A decision entry: curated frontmatter facts + citation. The ADR's own
    `## Decision` body is left in the file — never re-stated here."""
    return {
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "superseded_by": doc.superseded_by,
        "citation": to_dict(_decision_citation(doc.path)),
        "freshness": to_dict(_fresh()),
        "scope_errors": doc.schema_errors,
    }


def _failure_payload(rec) -> dict:
    """A failure-record entry: curated frontmatter fields + citation. The
    record's root-cause prose is the record's own content; the projection
    links it, it does not re-quote the record's body."""
    return {
        "id": rec.id,
        "title": rec.title,
        "reproduced_by": rec.reproduced_by,
        "root_cause": rec.root_cause,
        "fix": rec.fix,
        "regression_link": rec.regression_link,
        "linked_req": list(rec.linked_req),
        "linked_feature": list(rec.linked_feature),
        "citation": to_dict(_failure_citation(rec.path)),
        "freshness": to_dict(_fresh()),
        "scope_errors": list(rec.scope_errors),
    }


def _hypothesis_payload(rec, index: int, hypothesis: dict) -> dict:
    """One rejected hypothesis: its own text and evidence ref + a citation to
    the record file that hosts it (the hypothesis has no file of its own)."""
    return {
        "id": f"{rec.id}#hyp-{index + 1}",
        "record": rec.id,
        "hypothesis": hypothesis.get("hypothesis", ""),
        "why_rejected": hypothesis.get("why_rejected", ""),
        "evidence": hypothesis.get("evidence", ""),
        "citation": to_dict(_failure_citation(rec.path)),
        "freshness": to_dict(_fresh()),
    }


def _goal_payload(goal) -> dict:
    """An open-goal entry: contract fields + citation. Goal prose (the file
    body) is left in the file."""
    return {
        "id": goal.id,
        "title": goal.title,
        "state": goal.state,
        "feature": list(goal.feature),
        "requirements": list(goal.requirements),
        "metric": goal.metric,
        "target": goal.target,
        "citation": to_dict(_goal_citation(goal.path)),
        "freshness": to_dict(_fresh()),
        "scope_errors": list(goal.scope_errors),
    }


def query_memory(repo_root: Path, scope_ref: str) -> dict:
    """One read of durable memory: decisions, failure records, rejected
    hypotheses, open goals, and conflicts — all with provenance citations.

    `scope_ref` is `all` (every recorded artifact) or an exact
    `feat:<id>` / `sr:<id>` / `goal:<id>` / `adr:<id>` / `fr:<id>` ref.
    Feature/SR scopes filter failure records and goals by their declared
    `linked_feature` / `linked_req` / `feature` / `requirements` fields and
    resolve decisions through bundle membership (the SP-A bundle map). A
    `goal:`/`adr:`/`fr:` scope returns that artifact's own entry plus
    anything declared to link to it. Unknown kinds and unresolvable ids are
    rejected or empty, never fuzzy-matched.

    Conflicts surface structural contradictions the composed loaders can
    prove: a failure record whose `reproduced_by` run has no evidence
    manifest, an ADR whose `superseded_by` names no declared ADR, a
    hypothesis whose `run:` evidence does not exist. Both sides are shown
    (`memory` claim vs `evidence` state), never silently resolved.
    """
    kind, identifier = _parse_memory_scope(scope_ref)

    adrs = adr_module.load_adrs(repo_root)
    failures = load_failures(repo_root)
    goals = goal_registry.load_goals(repo_root)
    run_ids = _run_ids(repo_root)

    if kind == "all":
        feat_ids: list[str] = []
        sr_ids: list[str] = []
        adr_ids = list(adrs)
        fr_ids = list(failures)
        goal_ids = list(goals)
    elif kind == "feat":
        feat_ids, sr_ids = [identifier], []
        adr_ids = _decision_links(repo_root, feat_ids, sr_ids)
        # The failures dict is keyed by declared id, so keys are the ids --
        # never `r.id` (Optional on the record model).
        fr_ids = [fid for fid, r in failures.items() if identifier in r.linked_feature]
        goal_ids = [g.id for g in goals.values() if identifier in g.feature]
    elif kind == "sr":
        feat_ids, sr_ids = [], [identifier]
        adr_ids = _decision_links(repo_root, feat_ids, sr_ids)
        fr_ids = [fid for fid, r in failures.items() if identifier in r.linked_req]
        goal_ids = [g.id for g in goals.values() if identifier in g.requirements]
    elif kind == "goal":
        goal = goals.get(identifier)
        if goal is None:
            raise ValueError(f"no goal declares id {identifier!r}")
        feat_ids, sr_ids = list(goal.feature), list(goal.requirements)
        adr_ids = _decision_links(repo_root, feat_ids, sr_ids)
        fr_ids = [
            fid
            for fid, r in failures.items()
            if set(r.linked_feature) & set(feat_ids) or set(r.linked_req) & set(sr_ids)
        ]
        goal_ids = [goal.id]
    elif kind == "adr":
        if identifier not in adrs:
            raise ValueError(f"no ADR declares id {identifier!r}")
        feat_ids, sr_ids = [], []
        adr_ids = [identifier]
        fr_ids = []
        goal_ids = []
    else:  # fr
        if identifier not in failures:
            raise ValueError(f"no failure record declares id {identifier!r}")
        feat_ids, sr_ids = list(failures[identifier].linked_feature), list(failures[identifier].linked_req)
        adr_ids = _decision_links(repo_root, feat_ids, sr_ids)
        fr_ids = [identifier]
        goal_ids = [
            g.id for g in goals.values() if set(g.feature) & set(feat_ids) or set(g.requirements) & set(sr_ids)
        ]

    decisions = [_decision_payload(adrs[a]) for a in adr_ids if a in adrs]

    failure_records: list[dict] = []
    rejected_hypotheses: list[dict] = []
    for fr_id in fr_ids:
        rec = failures.get(fr_id)
        if rec is None:
            continue
        failure_records.append(_failure_payload(rec))
        for index, hypothesis in enumerate(rec.rejected_hypotheses):
            rejected_hypotheses.append(_hypothesis_payload(rec, index, hypothesis))

    open_goals = [
        _goal_payload(goals[g])
        for g in goal_ids
        if g in goals and str(goals[g].state) not in _TERMINAL_GOAL_STATES
    ]

    # Deterministic order: declared id (ADR/FR/goal), never mtime.
    failure_records.sort(key=lambda e: e["id"])
    rejected_hypotheses.sort(key=lambda e: e["id"])
    open_goals.sort(key=lambda e: e["id"])

    conflicts = _build_conflicts(
        repo_root,
        decisions=decisions,
        failure_records=failure_records,
        rejected_hypotheses=rejected_hypotheses,
        adr_ids=adr_ids,
        run_ids=run_ids,
    )

    return {
        "scope": scope_ref,
        "decisions": decisions,
        "failure_records": failure_records,
        "rejected_hypotheses": rejected_hypotheses,
        "open_goals": open_goals,
        "conflicts": conflicts,
    }


def _run_ref_detected(value: str) -> bool:
    """Whether a `reproduced_by` value names a run rather than a task ref.

    The record schema allows a reproduction *task ref* (`task:T-###` or a
    bare `T-###`) as well as a run id. Only run refs are checked against
    evidence manifests: `run:`-prefixed ids and bare ids that are neither
    task-prefixed nor task-shaped (`T-###`). Everything else is left
    unchecked rather than flagged.
    """
    if value.startswith("run:"):
        return True
    if ":" in value:
        return False
    return not value.startswith("T-")


def _build_conflicts(
    repo_root: Path,
    *,
    decisions: list[dict],
    failure_records: list[dict],
    rejected_hypotheses: list[dict],
    adr_ids: list[str],
    run_ids: set[str],
) -> list[dict]:
    """Structural conflicts: a memory link that contradicts the artifacts it
    cites. Both sides shown, never silently resolved.

    Scope-aware: conflicts are only reported for the memory entries the
    scope selected — an out-of-scope record never drags its own orphan into
    a feature's read.
    """
    conflicts: list[dict] = []

    adrs = adr_module.load_adrs(repo_root)
    selected_adr_ids = {d["id"] for d in decisions}
    for adr_id in adr_ids:
        doc = adrs.get(adr_id)
        if doc is None or adr_id not in selected_adr_ids:
            continue
        target = doc.superseded_by
        if doc.status == "superseded" and target and target not in adrs:
            conflicts.append(
                {
                    "kind": "missing-adr",
                    "memory": {"id": adr_id, "field": "superseded_by", "value": target},
                    "evidence": f"no ADR declares id {target!r}",
                    "citation": to_dict(_decision_citation(doc.path)),
                    "freshness": to_dict(_fresh()),
                }
            )

    for fr in failure_records:
        reproduced_by = fr.get("reproduced_by")
        if isinstance(reproduced_by, str) and _run_ref_detected(reproduced_by):
            run_id = (
                reproduced_by[len("run:"):] if reproduced_by.startswith("run:") else reproduced_by
            )
            if run_id and run_id not in run_ids:
                conflicts.append(
                    {
                        "kind": "missing-run",
                        "memory": {
                            "id": fr["id"],
                            "field": "reproduced_by",
                            "value": reproduced_by,
                        },
                        "evidence": f"no run manifest found for {run_id!r}",
                        "citation": fr["citation"],
                        "freshness": to_dict(_fresh()),
                    }
                )

    # Hypothesis evidence refs (`run:<id>`): each must resolve too. The
    # hypothesis has no file of its own, so its citation is the record's.
    for hypothesis in rejected_hypotheses:
        evidence = hypothesis.get("evidence", "")
        if _run_ref_missing(repo_root, evidence):
            run_id = evidence[len("run:"):]
            conflicts.append(
                {
                    "kind": "missing-run",
                    "memory": {
                        "id": hypothesis["record"],
                        "field": "evidence",
                        "value": evidence,
                    },
                    "evidence": f"no run manifest found for {run_id!r}",
                    "citation": hypothesis["citation"],
                    "freshness": to_dict(_fresh()),
                }
            )

    conflicts.sort(key=lambda c: (c["kind"], c["memory"]["id"], c["memory"].get("field", "")))
    return conflicts
