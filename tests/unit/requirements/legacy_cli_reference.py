"""Small, independent reference for the pre-migration requirements CLI.

This module intentionally has no imports from ``factory.requirements`` or
``coherence.register``.  It models the old CLI's dispatch and rendering
contract for the parity fixture, so importing the compatibility shim cannot
make the parity test tautological.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import frontmatter

STATEMENT = "When a shark is detected, the system shall warn the swimmer."


def _checksum(post: frontmatter.Post) -> str:
    binding = post["binding"]
    canonical = "\n".join(
        [
            str(post["statement"]).strip(),
            str(binding.get("harness", "")),
            str(binding["experiment"]),
            str(binding["metric"]),
            str(binding["assert"]),
            str(binding.get("trials", 1)),
            repr(binding.get("window")),
        ]
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def stamp_checksum(path: Path) -> None:
    post = frontmatter.load(str(path))
    post["checksum"] = _checksum(post)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _requirement(requirements: Path) -> frontmatter.Post:
    return frontmatter.load(str(requirements / "SR-001.md"))


def _state(root: Path) -> str:
    requirements = root / "requirements"
    post = _requirement(requirements)
    if "binding" not in post.metadata:
        return "proposed"
    if post.get("trace_deferred"):
        return "deferred"
    stored = post.get("checksum")
    if stored != _checksum(post):
        return "stale"
    manifests = list((root / "evidence" / "runs").glob("*.json"))
    if manifests:
        measured = json.loads(manifests[0].read_text(encoding="utf-8"))
        passed = measured["validation"][0]["requirements"][0]["passed"]
        return "measured-passing" if passed else "measured-failing"
    return "bound-current"


def _render(root: Path, command: str) -> tuple[str, int]:
    requirements = root / "requirements"
    state = _state(root) if command != "new" else "proposed"
    post = _requirement(requirements) if command != "new" else None
    statement = str(post["statement"]) if post else STATEMENT

    if command == "new":
        return f"{requirements / 'SR-002.md'}\n", 0
    if command == "index":
        entry = {"id": "SR-001", "checksum": None, "proposed": True}
        code = 0
        if state != "proposed":
            entry = {"id": "SR-001", "checksum": post.get("checksum"), "stale": state == "stale"}
            code = int(state == "stale")
        return json.dumps({"requirements": [entry]}, indent=2) + "\n", code
    if command == "status":
        if state == "proposed":
            return "SR-001  [proposed]  proposed requirement\n", 0
        status = "STALE" if state == "stale" else "current"
        return f"SR-001  [{status}]  {state} requirement\n", 0
    if command == "show":
        if state == "proposed":
            return (
                "SR-001  proposed requirement\n"
                f"statement: {statement}\n"
                "binding: (proposed -- not yet measurable)\n"
                "source: (none)\n"
            ), 0
        freshness = "STALE" if state == "stale" else "current"
        return (
            f"SR-001  {state} requirement\n"
            f"statement: {statement}\n"
            "binding: sim-testbench/patrol success_rate >= 0.90 (trials=1)\n"
            f"checksum: {freshness}\n"
        ), 0
    if command == "bind":
        return "SR-001  bound to sim-testbench: success_rate >= 0.95\n", 0
    if command == "defer":
        return "SR-001  deferred: blocked by the next test window\n", 0
    if command == "check":
        if state in {"proposed", "bound-current", "stale"}:
            detail = (
                "SR-001: binding checksum is stale; re-bind to refresh it"
                if state == "stale"
                else "SR-001: no measurement, task, or deferral accounts for this requirement"
            )
            summary = "1 pending, 0 unmeasurable, 0 measured-passing, 0 measured-failing, 0 declined (0 with no binding)"
            return (
                "requirements closure: 1 requirement(s) evaluated\n"
                f"{summary}\n\n"
                "undecided requirements (the gate fails on these):\n"
                f"  ! {'SR-001':<10} {detail}\n"
            ), 1
        if state == "deferred":
            summary = "0 pending, 0 unmeasurable, 0 measured-passing, 0 measured-failing, 1 declined (0 with no binding)"
            return "requirements closure: 1 requirement(s) evaluated\n" f"{summary}\n", 0
        passing = int(state == "measured-passing")
        failing = int(state == "measured-failing")
        summary = f"0 pending, 0 unmeasurable, {passing} measured-passing, {failing} measured-failing, 0 declined (0 with no binding)"
        report = "requirements closure: 1 requirement(s) evaluated\n" f"{summary}\n"
        if failing:
            report += (
                "\nmeasured failing — decided and measured; the system does not meet these:\n"
                f"  x {'SR-001':<10} SR-001: measured failing\n"
            )
        return report, 0
    if command == "next":
        if state in {"proposed", "bound-current", "stale"}:
            return f"SR-001  {state} requirement\nstatement: {statement}\ncandidate tasks: none\n", 0
        return "nothing pending -- every requirement is decided\n", 0
    raise AssertionError(f"unhandled command: {command}")


def main(argv: list[str] | None = None) -> int:
    rest = list(argv or [])
    command = rest[0]
    root = Path(".")
    for index, value in enumerate(rest):
        if value in {"--requirements-dir", "--project-root"} and index + 1 < len(rest):
            root = Path(rest[index + 1])
            break
    if command in {"check", "next"}:
        return_code_root = root
    else:
        return_code_root = root.parent if root.name == "requirements" else root
    output, code = _render(return_code_root, command)
    print(output, end="")
    return code
