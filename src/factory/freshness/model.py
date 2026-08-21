from __future__ import annotations

import warnings

from substrate.freshness.model import (
    DependencyFingerprint,
    FreshnessIssue,
    FreshnessReport,
    FreshnessSeverity,
    GATE_FAILING_SEVERITIES,
)

warnings.warn(
    "factory.freshness.model is deprecated; import substrate.freshness.model",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DependencyFingerprint",
    "FreshnessSeverity",
    "FreshnessIssue",
    "FreshnessReport",
    "GATE_FAILING_SEVERITIES",
]
