from __future__ import annotations

import json
from pathlib import Path

import pytest
from factory.trace.propose import next_gap, proposal_to_dict

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sr(tmp_path: Path, sr_id: str, statement: str) -> None:
    _write(
        tmp_path / "requirements" / f"{sr_id}.md",
        f"---\nid: {sr_id}\ntitle: {sr_id} title\nstatement: {statement}\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
    )


def test_returns_none_when_nothing_is_pending(tmp_path):
    assert next_gap(tmp_path) is None


def test_proposes_the_first_pending_gap_with_candidates(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Preempt patrol on shark detection\nstatus: todo\ndod: []\n---\n"
        "\nThe navigation system must preempt patrol when a shark is detected.\n",
    )
    _sr(tmp_path, "SR-001", "navigation shall preempt patrol when a shark is detected")
    _sr(tmp_path, "SR-002", "battery telemetry shall be published every second")

    proposal = next_gap(tmp_path)

    assert proposal is not None
    assert proposal.gap.node_id == "T-001"
    assert proposal.gap.kind == "task_no_sr"
    assert proposal.candidates[0].id == "SR-001"
    assert proposal.candidates[0].score > proposal.candidates[-1].score


def test_every_candidate_is_returned_never_truncated(tmp_path):
    # A lexical ranker must not decide which links are reachable. A correct match
    # whose vocabulary differs would otherwise be unpickable.
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n\nbody\n",
    )
    for n in range(1, 13):
        _sr(tmp_path, f"SR-{n:03d}", f"requirement number {n}")

    assert len(next_gap(tmp_path).candidates) == 12


def test_candidate_carries_the_statement_not_just_a_term_count(tmp_path):
    # The consumer reasons semantically, which a shared-term count cannot support.
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Preempt patrol\nstatus: todo\ndod: []\n---\n\nshark detected\n",
    )
    _sr(tmp_path, "SR-001", "preempt patrol when a shark is detected")

    candidate = next_gap(tmp_path).candidates[0]

    assert candidate.summary == "preempt patrol when a shark is detected"
    assert "shark" in candidate.shared_terms


def test_pending_total_is_reported(tmp_path):
    for task_id in ("T-001", "T-002", "T-003"):
        _write(
            tmp_path / "tasks" / f"{task_id}.md",
            f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n---\n",
        )

    # each task yields task_no_sr and task_no_plan
    assert next_gap(tmp_path).pending_total == 6


def test_deferred_and_exempt_gaps_are_skipped(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: A\nstatus: todo\ndod: []\ntrace_exempt: true\n---\n",
    )
    _write(
        tmp_path / "tasks" / "T-002.md",
        '---\nid: T-002\ntitle: B\nstatus: todo\ndod: []\ntrace_deferred: "later"\n---\n',
    )

    assert next_gap(tmp_path) is None


def test_ordering_is_stable_across_calls(tmp_path):
    for task_id in ("T-003", "T-001", "T-002"):
        _write(
            tmp_path / "tasks" / f"{task_id}.md",
            f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n---\n",
        )

    assert next_gap(tmp_path).gap.node_id == next_gap(tmp_path).gap.node_id == "T-001"


def test_proposal_dict_is_json_serialisable(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n\nbody\n",
    )

    json.dumps(proposal_to_dict(next_gap(tmp_path)))
