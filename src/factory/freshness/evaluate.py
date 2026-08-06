from __future__ import annotations

from collections.abc import Callable

from factory.freshness.model import (
    DependencyFingerprint,
    FreshnessIssue,
    FreshnessReport,
    FreshnessSeverity,
)

SeverityFor = Callable[[str], FreshnessSeverity]


def compare_dependencies(
    recorded: list[DependencyFingerprint],
    current: list[DependencyFingerprint],
    *,
    subject: str,
    severity_for: SeverityFor,
) -> FreshnessReport:
    expected_by_name = {item.name: item for item in recorded}
    actual_by_name = {item.name: item for item in current}
    issues: list[FreshnessIssue] = []
    for name in sorted(set(expected_by_name) | set(actual_by_name)):
        expected = expected_by_name.get(name)
        actual = actual_by_name.get(name)
        if expected is not None and actual is not None and expected.digest == actual.digest:
            continue
        if expected is None:
            code = "dependency_added"
            detail = f"dependency {name} was added after evidence was recorded"
        elif actual is None or actual.digest == "missing":
            code = "dependency_missing"
            detail = f"dependency {name} is now missing"
        else:
            code = "dependency_changed"
            detail = f"dependency {name} changed after evidence was recorded"
        issues.append(
            FreshnessIssue(
                code=code,
                severity=severity_for(name),
                subject=subject,
                dependency=name,
                expected=expected.digest if expected else None,
                actual=actual.digest if actual else None,
                detail=detail,
            )
        )
    return FreshnessReport(issues)
