"""Deterministic context delta computation (Inc 7 Task 2).

`compute_delta` answers "what changed since the developer's last checkpoint"
for one feature -- spec §31 / §9.4. Every field is computed from *recorded*
sources (git history, goal transition logs, simulation run bundles), never
from an LLM summarizing the past.

Interpretation notes (honest degradation):

* ``prs_merged`` -- merge-commit subjects in ``since..HEAD`` touching the
  feature's files (feature doc + its requirements + evidenced implementation
  files). No merge commits for the feature's paths -> ``[]``.
* ``requirements_changed`` -- the feature's declared requirements whose
  artifact file changed in ``since..HEAD``.
* ``adrs_added`` -- ADR files *added* in ``since..HEAD`` (reported by id when
  the filename is an id, else by repo-relative path).
* ``scenarios_added`` -- simulation *experiments* first recorded for the
  feature after the checkpoint (the recorded run unit; there is no separate
  scenario registry in the factory).
* ``goals_reached``/``goals_regressed`` -- feature goals whose transition log
  records an entry into REACHED/REGRESSED after the checkpoint.
* ``metric_changes`` -- per feature-goal metric, the value at the checkpoint
  (last run at-or-before) vs the value of the latest run after; ``regression``
  is True only when the latest value fails the goal target while the
  checkpoint value satisfied it (None when no target is declared).
* ``new_open_items`` -- bullet items under the feature document's
  "Open Questions" heading present now but absent at the checkpoint commit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from factory.delta import git_ops
from factory.goals.registry import load_goal
from factory.simulation import evidence as sim_evidence
from factory.simulation import registry as sim_registry
from factory.system._claims import evidence_dir as _evidence_dir
from factory.system.feature import feature_context
from factory.system.vcycle import vcycle_slice
from factory.trace.graph import build_graph

_OPEN_QUESTIONS_RE = re.compile(r"^#{1,6}\s*open\s+questions?\s*$", re.IGNORECASE | re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")

_OPERATORS = {">=", "<=", ">", "<", "=="}


@dataclass(frozen=True)
class ContextDelta:
    """What changed for one feature since one recorded checkpoint commit."""

    feature: str
    since_commit: str
    prs_merged: list[str] = field(default_factory=list)
    requirements_changed: list[str] = field(default_factory=list)
    adrs_added: list[str] = field(default_factory=list)
    scenarios_added: list[str] = field(default_factory=list)
    goals_reached: list[str] = field(default_factory=list)
    goals_regressed: list[str] = field(default_factory=list)
    metric_changes: list[dict] = field(default_factory=list)
    new_open_items: list[str] = field(default_factory=list)
    # Inc 7 Task 5k: freshness integration (filled by delta.freshness
    # apply_freshness; deterministic, from recorded sources only).
    code_files_changed: list[str] = field(default_factory=list)
    invalidated: list[str] = field(default_factory=list)
    auto_refreshed: list[str] = field(default_factory=list)
    refresh_required: list[str] = field(default_factory=list)
    blocked_refreshes: list[str] = field(default_factory=list)
    freshness_closure_reached: bool = False


def _feature_requirements(root: Path, feature_id: str) -> list[str]:
    """The feature's declared requirements (trace `contains` edges), sorted."""
    graph = build_graph(root)
    feature = next(
        (node for node in graph.nodes if node.kind == "feat" and node.id == feature_id),
        None,
    )
    if feature is None:
        raise ValueError(f"feature not found: {feature_id!r}")
    req_ids = {
        edge.dst
        for edge in graph.edges
        if edge.kind == "contains"
        and edge.src == feature.id
        and (edge.dst.startswith("SR-") or edge.dst.startswith("BR-"))
    }
    return sorted(req_ids)


def _feature_goal_ids(root: Path, feature_id: str) -> list[str]:
    """Goal ids in the feature's V-cycle slice (declared `demonstrates`/`evaluates`)."""
    return sorted(goal.id for goal in vcycle_slice(root, f"feat:{feature_id}").goals)


def _placed_after(root: Path, since_commit: str, commit: str | None, ts: str | None) -> bool:
    """True iff a recorded event happened strictly after the checkpoint.

    Commit ancestry is authoritative; a missing commit falls back to the
    ISO timestamp vs the checkpoint's commit date. Neither available ->
    the event cannot be placed and is NOT reported (honest incompleteness).
    """
    if commit:
        return not git_ops.is_ancestor(root, commit, since_commit)
    if ts:
        since_iso = git_ops.commit_iso(root, since_commit)
        return bool(since_iso and ts > since_iso)
    return False


def _open_questions(body: str) -> list[str]:
    """Bullet items under an "Open Questions" heading in a markdown body."""
    match = _OPEN_QUESTIONS_RE.search(body)
    if match is None:
        return []
    items: list[str] = []
    for line in body[match.end():].splitlines():
        if re.match(r"^\s*#{1,6}\s", line):
            break
        bullet = _BULLET_RE.match(line)
        if bullet:
            items.append(bullet.group(1).strip())
    return items


def _compare(value: float, target: dict) -> bool:
    operator = target.get("operator")
    bound = target.get("value")
    if operator not in _OPERATORS or not isinstance(bound, (int, float)):
        return False
    if operator == ">=":
        return value >= bound
    if operator == "<=":
        return value <= bound
    if operator == ">":
        return value > bound
    if operator == "<":
        return value < bound
    return value == bound


def _metric_changes(root: Path, feature_id: str, since_commit: str) -> list[dict]:
    """Per-goal metric deltas since the checkpoint, deterministic."""
    changes: list[dict] = []
    evidence = _evidence_dir(root)
    for goal_id in _feature_goal_ids(root, feature_id):
        goal = load_goal(root / "goals" / f"{goal_id}.md")
        metric = goal.metric.get("name") if goal.metric else None
        if not metric:
            continue
        history = sim_evidence.metric_history(evidence, metric)
        pre = [e for e in history if not _placed_after(root, since_commit, e.get("commit"), e.get("ts"))]
        post = [e for e in history if _placed_after(root, since_commit, e.get("commit"), e.get("ts"))]
        if not post:
            continue
        from_value = pre[-1]["value"] if pre else None
        to_value = post[-1]["value"]
        regression: bool | None = None
        if goal.target and from_value is not None:
            from_passed = _compare(from_value, goal.target)
            to_passed = _compare(to_value, goal.target)
            regression = from_passed and not to_passed
        changes.append(
            {
                "metric": metric,
                "from": from_value,
                "to": to_value,
                "regression": regression,
            }
        )
    return changes


def compute_delta(root: Path, feature: str, since_commit: str) -> ContextDelta:
    """Compute the deterministic "since your last review" delta for one feature.

    Raises ``ValueError`` when the feature or the checkpoint commit cannot be
    resolved -- an unresolvable checkpoint must never silently read as
    "nothing changed".
    """
    requirements = _feature_requirements(root, feature)
    if not git_ops.commit_exists(root, since_commit):
        raise ValueError(f"since_commit not found in repo: {since_commit!r}")

    feature_path = Path("docs") / "features" / f"{feature}.md"
    req_paths = [Path("requirements") / f"{req}.md" for req in requirements]
    try:
        implementation_files = feature_context(root, feature).get("implementation_files", [])
    except ValueError:
        implementation_files = []
    feature_files = [feature_path, *req_paths, *[Path(p) for p in implementation_files]]

    prs_merged = git_ops.merge_subjects_since(root, since_commit, feature_files)

    requirements_changed = [
        req
        for req in requirements
        if git_ops.changed_files_since(root, since_commit, [Path("requirements") / f"{req}.md"])
    ]

    added_adrs = git_ops.added_files_since(root, since_commit, [Path("docs/adr")])
    adrs_added = [
        Path(path).stem if Path(path).name.startswith("ADR-") else path
        for path in added_adrs
    ]

    evidence = _evidence_dir(root)
    runs = sim_registry.load_runs(evidence)
    scenarios_added = sorted(
        {
            run.experiment
            for run in runs
            if run.feature == feature
            and _placed_after(root, since_commit, run.commit, run.recorded_ts)
        }
    )

    goal_ids = _feature_goal_ids(root, feature)
    goals_reached = sorted(
        _transitioned_to(root, since_commit, goal_ids, "REACHED")
    )
    goals_regressed = sorted(
        _transitioned_to(root, since_commit, goal_ids, "REGRESSED")
    )

    metric_changes = _metric_changes(root, feature, since_commit)

    code_files_changed = _code_files_changed(root, feature, since_commit, feature_files)

    current_body = git_ops.read_file_at(root, "HEAD", feature_path) or ""
    old_body = git_ops.read_file_at(root, since_commit, feature_path) or ""
    new_open_items = sorted(set(_open_questions(current_body)) - set(_open_questions(old_body)))

    return ContextDelta(
        feature=feature,
        since_commit=since_commit,
        prs_merged=prs_merged,
        requirements_changed=requirements_changed,
        adrs_added=adrs_added,
        scenarios_added=scenarios_added,
        goals_reached=goals_reached,
        goals_regressed=goals_regressed,
        metric_changes=metric_changes,
        new_open_items=new_open_items,
        code_files_changed=code_files_changed,
    )


def _code_files_changed(
    root: Path, feature: str, since_commit: str, feature_files: list[Path]
) -> list[str]:
    """Implementation/code files under the feature's paths changed since the
    checkpoint (repo-relative). Deterministic via git; excludes markdown docs.
    Includes the code files the feature's evidence runs record as dependencies.
    """
    from factory.simulation.registry import load_runs

    paths = list(feature_files)
    for run in load_runs(_evidence_dir(root)):
        if run.feature != feature:
            continue
        try:
            manifest = json.loads(run.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, dict):
            continue
        for dep in manifest.get("dependencies", []):
            if isinstance(dep, dict) and isinstance(dep.get("source"), str):
                paths.append(Path(dep["source"]))
    changed = git_ops.changed_files_since(root, since_commit, paths)
    return sorted(
        path
        for path in changed
        if path.rsplit(".", 1)[-1] in {"py", "ts", "tsx", "js", "jsx", "go", "rs", "c", "cpp", "h"}
    )


def _transitioned_to(root: Path, since_commit: str, goal_ids: list[str], to_state: str) -> list[str]:
    """Goal ids with a transition-log entry INTO `to_state` placed after the checkpoint."""
    out: list[str] = []
    goals_dir = root / "goals"
    for goal_id in goal_ids:
        log = goals_dir / f"{goal_id}-transitions.jsonl"
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("to_state") != to_state:
                continue
            if _placed_after(
                root, since_commit, entry.get("commit"), entry.get("recorded_at")
            ):
                out.append(goal_id)
                break
    return out
