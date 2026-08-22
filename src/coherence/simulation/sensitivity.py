"""Evidence sensitivity (patch-reversal) — brief §5.2.

A green simulation is not strong evidence for a feature if it stays green after
the capability under test is removed. ``evaluate_sensitivity`` compares the same
metric keys across an enabled and a disabled evidence set (paired seeds) and
reports the per-key deltas and an overall SENSITIVE / INSENSITIVE verdict.

Semantics:
- A metric is "materially degraded" when its value drops by more than ``tol``.
- The overall verdict is SENSITIVE when at least one monitored key degrades
  beyond ``tol``; otherwise INSENSITIVE.
- ``tol=0.0`` means any change in a monitored key counts as sensitivity.
- INSENSITIVE is a gate-not-worthy state: ``sensitivity_verdict(...,
  block_insensitive=True)`` raises :class:`InsensitiveError` so a caller can
  choose to block; passive callers just read the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SensitivityResult:
    deltas: dict[str, float]
    verdict: str  # "SENSITIVE" | "INSENSITIVE"


class InsensitiveError(Exception):
    """Raised when a feature shows no material evidence sensitivity."""


def evaluate_sensitivity(
    enabled: Mapping[str, float],
    disabled: Mapping[str, float],
    *,
    keys: list[str],
    tol: float,
) -> SensitivityResult:
    """Compare monitored metric keys across enabled and disabled evidence.

    Purpose: detect whether a feature's evidence degrades materially when the
    capability under test is disabled (patch-reversal). Keys present in one
    side but not the other are treated as an absolute degradation when their
    value drops and a metric appears in both.

    Args:
        enabled: metric map from the enabled (capability on) run.
        disabled: metric map from the disabled (capability off) run, paired seeds.
        keys: metric names to monitor (empty means nothing is monitored).
        tol: absolute drop threshold beyond which a key counts as degraded.

    Returns:
        A ``SensitivityResult`` with per-key ``deltas`` (disabled - enabled) and
        an overall ``verdict``.

    Raises:
        None.
    """
    deltas: dict[str, float] = {}
    degraded = False
    for key in keys:
        e = enabled.get(key)
        d = disabled.get(key)
        if isinstance(e, (int, float)) and isinstance(d, (int, float)):
            delta = float(d) - float(e)
            deltas[key] = delta
        elif key in enabled or key in disabled:
            # Present on one side only: treat its absence as a total loss.
            present = enabled if key in enabled else disabled
            value = float(present[key]) if isinstance(present[key], (int, float)) else 0.0
            deltas[key] = -value if key in enabled else value
            if key in enabled:
                degraded = True
            continue
        else:
            continue  # monitored key absent from both sides: nothing to compare
        if delta < -abs(tol) or (tol == 0.0 and delta != 0.0):
            degraded = True
    verdict = "SENSITIVE" if degraded else "INSENSITIVE"
    return SensitivityResult(deltas=deltas, verdict=verdict)


def sensitivity_verdict(result: SensitivityResult, *, block_insensitive: bool) -> str:
    """Return the verdict; raise :class:`InsensitiveError` when asked to block.

    Purpose: let callers enforce the §5.2 gate — a green-though-insensitive
    feature must not silently pass when the caller treats insensitivity as a
    gate-not-worthy state.

    Args:
        result: the computed sensitivity result.
        block_insensitive: if True and the verdict is INSENSITIVE, raise.

    Returns:
        The verdict string ("SENSITIVE" or "INSENSITIVE").

    Raises:
        InsensitiveError: when ``block_insensitive`` is True and verdict is
            INSENSITIVE.
    """
    if block_insensitive and result.verdict == "INSENSITIVE":
        raise InsensitiveError("evidence is insensitive to the capability under test")
    return result.verdict

