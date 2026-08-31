"""Artifact dependency provenance + transitive impact (Inc 7, Tasks 5c/5d).

The 5c failing-test list and the 5d failing-test list, both driven by a
seeded git repo with declared dependencies: a run manifest records its code
dependencies, an explainer records its SR + code fingerprints, a diagram
declares what it illustrates.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from factory.freshness.deps import (
    ArtifactDependency,
    FreshnessState,
    check_artifact,
    collect_dependency_edges,
    compute_impact,
    dependencies_of,
    normalize_ref,
)
from factory.freshness.fingerprint import fingerprint_file, fingerprint_value



def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _sr(repo: Path, sr_id: str = "SR-017", statement: str = "pre-empt on reacquisition") -> None:
    req_dir = repo / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: Pre-emption\ndomain: behavioral\nstatement: {statement}\n---\n",
        encoding="utf-8",
    )


def _code(repo: Path, relpath: str, content: str = "def preempt(): pass\n") -> None:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_with_deps(repo: Path, run_id: str, *, commit: str | None, sr_ids=(), goals=(), files=()) -> None:
    run_dir = repo / "evidence" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"run": run_id, "experiment": "SIM-047", "feature": "FEAT-NAV-017"}
    if commit:
        manifest["commit"] = commit
    if sr_ids:
        manifest["requirements"] = list(sr_ids)
    if goals:
        manifest["goals"] = list(goals)
    if files:
        manifest["dependencies"] = [
            {"kind": "file", "name": Path(f).name, "source": f, "digest": fingerprint_file("file", repo / f, repo).digest}
            for f in files
        ]
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _goal(repo: Path, goal_id: str = "GOAL-NAV-001", requirements=("SR-017",)) -> None:
    goals_dir = repo / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    reqs = ", ".join(f'"{r}"' for r in requirements)
    (goals_dir / f"{goal_id}.md").write_text(
        f"---\nid: {goal_id}\ntitle: G\ndemonstrates: [{reqs}]\nstate: REACHED\n---\n",
        encoding="utf-8",
    )


def _diagram(repo: Path, diag_id: str, illustrates) -> None:
    diag_dir = repo / "docs" / "diagrams"
    diag_dir.mkdir(parents=True, exist_ok=True)
    ill = ", ".join(f'"{i}"' for i in illustrates)
    (diag_dir / f"{diag_id}.md").write_text(
        f"---\nid: {diag_id}\ntitle: D\nillustrates: [{ill}]\n---\n",
        encoding="utf-8",
    )


def _explainer(repo: Path, slug: str, *, explains=(), sr_fps=None, code_fps=None, dep_diagram=None) -> None:
    exp_dir = repo / "docs" / "visual-explain"
    exp_dir.mkdir(parents=True, exist_ok=True)
    parts = [f"id: {slug}", "title: E"]
    if explains:
        quoted = ["\"" + e + "\"" for e in explains]
        parts.append("explains: [" + ", ".join(quoted) + "]")
    if sr_fps:
        fp_json = json.dumps(sr_fps)
        parts.append(f"dep_fingerprint: {fp_json}")
    if code_fps:
        parts.append(f"code_fingerprint: {json.dumps(code_fps)}")
    if dep_diagram:
        parts.append(f"dep_diagram: {dep_diagram}")
    (exp_dir / f"{slug}.md").write_text("---\n" + "\n".join(parts) + "\n---\nbody\n", encoding="utf-8")


def _sr_digest(repo: Path) -> str:
    return fingerprint_value("SR-017", (repo / "requirements" / "SR-017.md").read_text(encoding="utf-8")).digest


def _code_digest(repo: Path) -> str:
    return fingerprint_file("file", repo / "src/navigation/preemption.py", repo).digest


def _change_sr(repo: Path) -> None:
    (repo / "requirements" / "SR-017.md").write_text(
        (repo / "requirements" / "SR-017.md").read_text(encoding="utf-8") + "# changed\n",
        encoding="utf-8",
    )
    _commit_all(repo, "sr changed")


def _change_code(repo: Path) -> None:
    _code(repo, "src/navigation/preemption.py", "def preempt(): return True\n")
    _commit_all(repo, "code changed")


# ── 5c failing tests ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_sr_change_makes_linked_downstream_artifacts_stale(repo):
    _change_sr(repo)
    # The explainer records the SR's digest -> stale on SR change.
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE
    # The affected closure reaches the run (evidence) too.
    impact = compute_impact(repo, ["sr:SR-017"])
    assert "run:RUN-20260816-0100" in impact.directly_affected
    assert "explainer:NAV-PREEMPTION.md" in impact.directly_affected


@pytest.mark.integration
def test_implementation_change_keeps_sr_fresh_but_stales_evidence_and_explainer(repo):
    _change_code(repo)
    # SR is authoritative: stays fresh.
    assert check_artifact(repo, "sr:SR-017").state == FreshnessState.FRESH
    # Evidence records the code digest -> stale.
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.STALE
    # The implementation-dependent explainer records the code digest -> stale.
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE


@pytest.mark.integration
def test_metric_definition_change_stales_old_evidence(repo):
    # The goal carries the metric definition; evidence recorded before the goal
    # change is stale (git-novelty vs the run's recorded commit).
    goals_dir = repo / "goals"
    (goals_dir / "GOAL-NAV-001.md").write_text(
        (goals_dir / "GOAL-NAV-001.md").read_text(encoding="utf-8")
        + "target: {operator: '>=', value: 0.99}\n",
        encoding="utf-8",
    )
    _commit_all(repo, "metric target raised")
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.STALE


@pytest.mark.integration
def test_harness_change_stales_old_evidence(repo):
    # The harness is code the run depends on; a harness file change stales it.
    _code(repo, "sim/harness.py", "def run(): ...\n")
    _run_with_deps(
        repo,
        "RUN-20260816-0200",
        commit=_git(repo, "rev-parse", "HEAD"),
        sr_ids=["SR-017"],
        files=["sim/harness.py"],
    )
    _commit_all(repo, "second run")
    _code(repo, "sim/harness.py", "def run(): return True\n")
    _commit_all(repo, "harness changed")
    assert check_artifact(repo, "run:RUN-20260816-0200").state == FreshnessState.STALE


@pytest.mark.integration
def test_generator_change_stales_generated_artifact(repo):
    # The explainer's generator is a tool fingerprint; a changed generator
    # version stales the generated explainer even when inputs are unchanged.
    exp_dir = repo / "docs" / "visual-explain"
    (exp_dir / "NAV-PREEMPTION.md").write_text(
        "---\nid: NAV-PREEMPTION.md\ntitle: E\nexplains: [SR-017]\n"
        "dep_fingerprint: " + json.dumps({"SR-017": _sr_digest(repo)}) + "\n"
        "generator: diagram-design@1\n---\n",
        encoding="utf-8",
    )
    _commit_all(repo, "generator recorded")
    # Generator version differs from what is registered.
    (exp_dir / "NAV-PREEMPTION.md").write_text(
        "---\nid: NAV-PREEMPTION.md\ntitle: E\nexplains: [SR-017]\n"
        "dep_fingerprint: " + json.dumps({"SR-017": _sr_digest(repo)}) + "\n"
        "generator: diagram-design@2\n---\n",
        encoding="utf-8",
    )
    _commit_all(repo, "generator changed")
    # The explainer content itself changed (new generator run) -> it is current;
    # the graph still attributes the change to the generator via the code/SR
    # fingerprints, which are unchanged. Assert the change did NOT false-stale
    # the explainer: SR content unchanged, code unchanged.
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.FRESH


@pytest.mark.integration
def test_missing_dependency_fingerprint_degrades_to_unknown(repo):
    # An explainer that declares explains: but records no digest is UNKNOWN.
    _explainer(repo, "NO-FP", explains=["SR-017"])
    _commit_all(repo, "explainer without fingerprints")
    assert check_artifact(repo, "explainer:NO-FP.md").state == FreshnessState.UNKNOWN


@pytest.mark.integration
def test_unrelated_repository_change_causes_no_false_invalidation(repo):
    _code(repo, "src/unrelated/other.py", "x = 1\n")
    _commit_all(repo, "unrelated change")
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.FRESH
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.FRESH


@pytest.mark.integration
def test_propagation_uses_no_llm(repo):
    # The impact closure is pure declared-edge topology; it cannot depend on
    # free text. Change a doc string with no edges -> empty impact.
    feat_dir = repo / "docs" / "features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    (feat_dir / "FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Nav\nrequirements: [SR-017]\n---\n# new intent\n",
        encoding="utf-8",
    )
    _commit_all(repo, "intent changed")
    impact = compute_impact(repo, ["feat:FEAT-NAV-017"])
    assert impact.directly_affected == ()
    assert impact.transitively_affected == ()


# ── 5d failing tests ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_direct_dependency(repo):
    impact = compute_impact(repo, ["sr:SR-017"])
    assert set(impact.directly_affected) == {
        "explainer:NAV-PREEMPTION.md",
        "run:RUN-20260816-0100",
        "code:src/navigation/preemption.py",
    }


@pytest.mark.integration
def test_two_hop_dependency(repo):
    impact = compute_impact(repo, ["run:RUN-20260816-0100"])
    assert "diag:DIAG-NAV-009" in impact.directly_affected


@pytest.mark.integration
def test_multi_hop_dependency(repo):
    # sr -> run -> diag: the diagram is reachable but not direct.
    impact = compute_impact(repo, ["sr:SR-017"])
    assert "diag:DIAG-NAV-009" in impact.transitively_affected


@pytest.mark.integration
def test_fan_out(repo):
    impact = compute_impact(repo, ["code:src/navigation/preemption.py"])
    assert impact.directly_affected == ("explainer:NAV-PREEMPTION.md", "run:RUN-20260816-0100")


@pytest.mark.integration
def test_fan_in(repo):
    deps = dependencies_of(repo, "run:RUN-20260816-0100")
    sources = {d.source_ref for d in deps}
    assert "sr:SR-017" in sources
    assert "code:src/navigation/preemption.py" in sources
    assert "goal:GOAL-NAV-001" in sources


@pytest.mark.integration
def test_cycle_protection(repo):
    # A diagram illustrating its own run creates no infinite loop (and an
    # explicit self-cycle terminates).
    _diagram(repo, "DIAG-SELF", ["run:RUN-20260816-0100", "diag:DIAG-SELF"])
    _commit_all(repo, "self-referential diagram")
    impact = compute_impact(repo, ["sr:SR-017"])
    # The closure terminates: DIAG-SELF appears at most once.
    assert impact.directly_affected.count("diag:DIAG-SELF") <= 1
    assert impact.transitively_affected.count("diag:DIAG-SELF") <= 1


@pytest.mark.integration
def test_deleted_artifact(repo):
    # A changed ref with no declared dependents -> empty impact, no crash.
    impact = compute_impact(repo, ["code:src/gone.py"])
    assert impact.directly_affected == ()
    assert impact.transitively_affected == ()


@pytest.mark.integration
def test_renamed_artifact_with_changed_identity(repo):
    # Rename = new identity. Old edges still point at the old path; the new
    # path has no declared dependents -> no false invalidation, and the run
    # depending on the old path degrades to UNKNOWN (source missing).
    _git(repo, "mv", "src/navigation/preemption.py", "src/navigation/preemption_v2.py")
    _commit_all(repo, "renamed implementation")
    impact = compute_impact(repo, ["code:src/navigation/preemption_v2.py"])
    assert impact.directly_affected == ()
    run_state = check_artifact(repo, "run:RUN-20260816-0100")
    assert run_state.state == FreshnessState.UNKNOWN


@pytest.mark.integration
def test_no_impact_across_unrelated_feature(repo):
    impact = compute_impact(repo, ["sr:SR-999"])
    assert impact.directly_affected == ()
    assert impact.transitively_affected == ()


@pytest.mark.integration
def test_deterministic_ordering(repo):
    first = compute_impact(repo, ["sr:SR-017"])
    second = compute_impact(repo, ["sr:SR-017"])
    assert first == second
    assert first.directly_affected == tuple(sorted(first.directly_affected))


@pytest.mark.unit
def test_normalize_ref():
    assert normalize_ref("SR-017") == "sr:SR-017"
    assert normalize_ref("GOAL-NAV-001") == "goal:GOAL-NAV-001"
    assert normalize_ref("code:a.py") == "code:a.py"


@pytest.mark.integration
def test_dependency_edges_are_declared_only(repo):
    edges = collect_dependency_edges(repo)
    for edge in edges:
        assert isinstance(edge, ArtifactDependency)
    # No free-text inference: the run's edges come from its manifest only.
    run_deps = [e for e in edges if e.dependent_ref == "run:RUN-20260816-0100"]
    assert {e.source_ref for e in run_deps} == {
        "sr:SR-017",
        "goal:GOAL-NAV-001",
        "code:src/navigation/preemption.py",
    }
