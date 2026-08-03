from __future__ import annotations

from collections.abc import Iterator


def _iter_specs(report: dict) -> Iterator[dict]:
    """Flatten Playwright's nested suites -> spec objects.

    The JSON reporter emits {"suites": [{"file", "specs": [...], "suites": [...]}]}
    with arbitrary nesting. Each yielded spec carries its inherited "file" so
    callers can match on file OR title.
    """

    def walk(suite: dict, file_hint: str) -> Iterator[dict]:
        file = suite.get("file", file_hint)
        for spec in suite.get("specs", []):
            yield {**spec, "file": spec.get("file", file)}
        for child in suite.get("suites", []):
            yield from walk(child, file)

    for suite in report.get("suites", []):
        yield from walk(suite, "")


def _spec_passed(report: dict, experiment: str) -> bool:
    """True iff at least one spec matches *experiment* (substring of file or
    title) and every matched spec is ok. No match -> False (a requirement whose
    spec did not run is not silently 'passed')."""
    matched = [
        s
        for s in _iter_specs(report)
        if experiment in s.get("file", "") or experiment in s.get("title", "")
    ]
    if not matched:
        return False
    return all(bool(s.get("ok")) for s in matched)
