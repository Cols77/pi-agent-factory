import dataclasses

import pytest
from substrate.policy.obligation import Obligation

pytestmark = pytest.mark.unit


@pytest.mark.sr("SR-009")
def test_obligation_is_the_documented_contract():
    # AC-1: "exposes exactly the documented fields" -- pin the dataclass's own
    # field set, not just a successful construction (which extra optional
    # fields with defaults would still pass silently).
    assert {f.name for f in dataclasses.fields(Obligation)} == {
        "id",
        "scope_ref",
        "kind",
        "requiredness",
        "reason",
        "source_policy",
        "state",
        "resolve_cmd",
    }

    ob = Obligation(
        id="ob:ci_verification:project",
        scope_ref="project",
        kind="ci_verification",
        requiredness="blocking",
        reason="every default preset requires CI-verified gates",
        source_policy="prototype",
        state="open",
        resolve_cmd=("pytest -m unit",),
    )
    assert ob.requiredness in ("not_applicable", "advisory", "required", "blocking")
    assert ob.resolve_cmd == ("pytest -m unit",)
