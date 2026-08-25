"""Increment 6B Task 5: the thin vertical slice, end to end, dual projections.

Spec §8 steps 4-8 in one integration test (spec D19): run `T-031` (corrective)
and `T-940` (requirement-delivery) through the progressive-assurance spine,
confirm the `prototype` feature incurs no high-assurance ceremony while the
`high_assurance` requirement cannot close with missing/errored verification,
check every compiled obligation explains itself and its cost, and confirm the
compact agent projection (`cmd_obligations`) and the human-rendered projection
(`_render_obligations`) agree on outcome for the same observation.

This plan authors no production code; it exercises obligation kinds compiled by
Increments 2B/4/6 and the suspect-relationship classifier from Increment 6.
"""
import pytest
from pathlib import Path

from coherence.navigate.cli import _render_obligations, cmd_obligations
from coherence.policy.compiler import compile_obligations
from substrate.ledger.tasks import get_task, load_tasks

pytestmark = pytest.mark.integration


def _root() -> Path:
    # tests/integration/<file> -> repo root is parents[2].
    return Path(__file__).resolve().parents[2]


def test_prototype_feature_incurs_no_high_assurance_ceremony() -> None:
    obligations = compile_obligations(_root(), "feat:FEAT-DOGFOOD-PROTOTYPE")
    # No human_review obligation is even applicable under prototype (D16).
    hr = [o for o in obligations if o.kind == "human_review"]
    assert not hr or all(o.requiredness == "not_applicable" for o in hr)


def test_high_assurance_feature_cannot_close_with_missing_verification() -> None:
    obligations = compile_obligations(_root(), "sr:SR-DOGFOOD-001")
    blocking_open = [
        o for o in obligations if o.requiredness == "blocking" and o.state != "satisfied"
    ]
    # SR-DOGFOOD-001 has a binding but no recorded passing run or approved
    # human-review evidence -- both obligations must still be open/blocking.
    assert {"verification_result", "human_review"} <= {o.kind for o in blocking_open}


def test_t031_traces_through_corrects_not_a_fabricated_satisfies() -> None:
    task = get_task(load_tasks(_root() / "tasks"), "T-031")
    assert task is not None
    assert task.satisfies == []
    assert any(j.kind == "corrects" and j.target_id == "NC-0001" for j in task.justification)


def test_every_obligation_explains_itself_and_its_cost() -> None:
    for scope in ("project", "sr:SR-DOGFOOD-001", "task:T-940"):
        for obligation in compile_obligations(_root(), scope):
            assert obligation.reason  # "explains itself"
            assert obligation.resolve_cmd  # "and its cost" -- how to satisfy it


def test_dual_projection_agrees_on_outcome() -> None:
    result = cmd_obligations(_root(), "sr:SR-DOGFOOD-001")
    rendered = _render_obligations(result)
    # The compact (agent) projection and the human-rendered text projection
    # come from the SAME `result` dict -- confirm every obligation's kind and
    # requiredness named in the JSON also appears, verbatim, in the text.
    for obligation in result["obligations"]:
        assert obligation["kind"] in rendered
        assert obligation["requiredness"] in rendered