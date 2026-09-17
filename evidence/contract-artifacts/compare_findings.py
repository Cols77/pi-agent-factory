"""Compare two `navigate health --json` / `navigate freshness --json` outputs.

Prints only the differences in the finding-code/subject sets, so a
no-catalog regression claim can be checked mechanically instead of by eye.

Usage: uv run python compare_findings.py <base.json> <head.json> <label>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _findings(path: Path) -> set[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "code" in node and "subject" in node:
                out.add((str(node["code"]), str(node["subject"])))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def main() -> int:
    base_path, head_path, label = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    base, head = _findings(base_path), _findings(head_path)
    added = sorted(head - base)
    removed = sorted(base - head)
    print(f"== {label} ==")
    print(f"base findings: {len(base)}   head findings: {len(head)}")
    print(f"added ({len(added)}):")
    for code, subject in added:
        print(f"  + {code}  {subject}")
    print(f"removed ({len(removed)}):")
    for code, subject in removed:
        print(f"  - {code}  {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())