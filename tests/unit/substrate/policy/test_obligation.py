import pytest
from substrate.policy.obligation import Obligation

pytestmark = pytest.mark.unit


def test_obligation_is_the_documented_contract():
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
