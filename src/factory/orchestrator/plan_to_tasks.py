from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

from substrate.ledger.plans import NoTasksFoundError, ParsedPlanTask, parse_plan_tasks, run

warnings.warn(
    "factory.orchestrator.plan_to_tasks is deprecated; import substrate.ledger.plans",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["NoTasksFoundError", "ParsedPlanTask", "parse_plan_tasks", "run", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator.plan_to_tasks")
    parser.add_argument("plan_file")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    plan_path = Path(args.plan_file).resolve()

    try:
        created = run(plan_path, repo_root)
    except NoTasksFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not created:
        print("no new tasks (already parsed)")
    else:
        print("created: " + ", ".join(created))


if __name__ == "__main__":
    main()
