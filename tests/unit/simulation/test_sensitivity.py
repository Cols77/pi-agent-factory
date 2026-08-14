"""Evidence-sensitivity (patch-reversal) tests (Inc 3 Task 6b, brief §5.2)."""

from __future__ import annotations

import pytest

from factory.simulation.sensitivity import (
    InsensitiveError,
    evaluate_sensitivity,
    sensitivity_verdict,
)

pytestmark = pytest.mark.unit


def test_sensitive_when_metric_degrades_beyond_tol():
    enabled = {"reacquisition_rate": 1.0, "false_reacquisition_rate": 0.0}
    disabled = {"reacquisition_rate": 0.6, "false_reacquisition_rate": 0.4}
    result = evaluate_sensitivity(
        enabled,
        disabled,
        keys=["reacquisition_rate"],
        tol=0.2,
    )
    assert result.deltas["reacquisition_rate"] == pytest.approx(-0.4)
    assert result.verdict == "SENSITIVE"


def test_insensitive_when_no_material_degradation():
    enabled = {"reacquisition_rate": 1.0, "false_reacquisition_rate": 0.0}
    disabled = {"reacquisition_rate": 0.98, "false_reacquisition_rate": 0.0}
    result = evaluate_sensitivity(
        enabled,
        disabled,
        keys=["reacquisition_rate"],
        tol=0.2,
    )
    assert result.verdict == "INSENSITIVE"


def test_no_threshold_means_any_change_is_sensitive():
    enabled = {"reacquisition_rate": 1.0}
    disabled = {"reacquisition_rate": 0.99}
    result = evaluate_sensitivity(enabled, disabled, keys=["reacquisition_rate"], tol=0.0)
    assert result.verdict == "SENSITIVE"


def test_insensitive_raises_by_default_for_a_blockable_gate():
    enabled = {"reacquisition_rate": 1.0}
    disabled = {"reacquisition_rate": 0.98}
    with pytest.raises(InsensitiveError):
        sensitivity_verdict(
            evaluate_sensitivity(enabled, disabled, keys=["reacquisition_rate"], tol=0.2),
            block_insensitive=True,
        )


def test_insensitive_passive_returns_verdict_without_raising():
    enabled = {"reacquisition_rate": 1.0}
    disabled = {"reacquisition_rate": 0.98}
    verdict = sensitivity_verdict(
        evaluate_sensitivity(enabled, disabled, keys=["reacquisition_rate"], tol=0.2),
        block_insensitive=False,
    )
    assert verdict == "INSENSITIVE"


def test_multiple_keys_reports_each_delta():
    enabled = {"a": 1.0, "b": 0.5}
    disabled = {"a": 0.4, "b": 0.49}
    result = evaluate_sensitivity(enabled, disabled, keys=["a", "b"], tol=0.1)
    assert "a" in result.deltas and "b" in result.deltas
    assert result.verdict == "SENSITIVE"  # at least one key degraded beyond tol


def test_empty_key_set_is_overall_insensitive():
    enabled = {"a": 1.0}
    disabled = {"a": 0.4}
    result = evaluate_sensitivity(enabled, disabled, keys=[], tol=0.2)
    assert result.verdict == "INSENSITIVE"
