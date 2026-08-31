#!/usr/bin/env python3
"""Adapt provider/local diffs to the pure changed-campaign classifier."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from coherence.policy.impact import classify_changed_paths  # noqa: E402

_ZERO_SHA = "0" * 40


def _git_names(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.splitlines()


def _committed_diff(root: Path, base: str, head: str) -> list[str]:
    if not base or not head or base == _ZERO_SHA or head == _ZERO_SHA:
        raise ValueError("diff endpoints are unavailable")
    return _git_names(root, "diff", "--name-only", "--diff-filter=ACDMRTUXB", base, head, "--")


def _working_tree_diff(root: Path) -> list[str]:
    tracked = _git_names(root, "diff", "--name-only", "HEAD", "--")
    untracked = _git_names(root, "ls-files", "--others", "--exclude-standard")
    return tracked + untracked


def _event_diff(root: Path) -> list[str] | None:
    """Resolve GitHub event endpoints; this provider knowledge stays in the adapter."""
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "pull_request":
        base = os.environ.get("GITHUB_BASE_SHA", "")
        head = os.environ.get("GITHUB_HEAD_SHA", "") or os.environ.get("GITHUB_SHA", "")
        return _committed_diff(root, base, head)
    if event == "push":
        base = os.environ.get("GITHUB_BEFORE_SHA", "") or os.environ.get(
            "GITHUB_EVENT_BEFORE", ""
        )
        head = os.environ.get("GITHUB_AFTER_SHA", "") or os.environ.get("GITHUB_SHA", "")
        return _committed_diff(root, base, head)
    return None


def acquire_paths(
    root: Path,
    *,
    paths: Sequence[str] | None = None,
    paths_file: Path | None = None,
    base: str | None = None,
    head: str | None = None,
    working_tree: bool = False,
) -> list[str] | None:
    """Obtain changed names from explicit, committed, local, or provider input."""
    if paths is not None:
        return list(paths)
    if paths_file is not None:
        return paths_file.read_text(encoding="utf-8").splitlines()
    if base is not None or head is not None:
        if base is None or head is None:
            raise ValueError("both --base and --head are required")
        return _committed_diff(root, base, head)
    if working_tree:
        return _working_tree_diff(root)
    return _event_diff(root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", dest="paths", action="append", help="explicit changed path")
    parser.add_argument("--paths-file", type=Path)
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--working-tree", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="accepted for callers that request JSON; JSON is always emitted",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        changed = acquire_paths(
            root,
            paths=args.paths,
            paths_file=args.paths_file,
            base=args.base,
            head=args.head,
            working_tree=args.working_tree,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        changed = None

    campaigns = list(classify_changed_paths(changed))
    encoded = json.dumps(campaigns, separators=(",", ":"))
    print(encoded)
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"campaigns={encoded}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
