import pytest
from factory.validation.assertions import evaluate_assertion

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,expr,expected",
    [
        (0.90, ">= 0.90", True),
        (0.89, ">= 0.90", False),
        (0.91, "> 0.90", True),
        (0.90, "> 0.90", False),
        (0.5, "<= 0.5", True),
        (0.4, "< 0.5", True),
        (1.0, "== 1.0", True),
        (0.80, ">=0.80", True),  # no space
    ],
)
def test_evaluate_assertion(value, expr, expected):
    assert evaluate_assertion(value, expr) is expected


def test_bad_expr_raises():
    with pytest.raises(ValueError):
        evaluate_assertion(1.0, "roughly 0.9")
