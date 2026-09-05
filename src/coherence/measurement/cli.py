from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from coherence.measurement.pipeline import validate_task_requirements
from coherence.measurement.report import (
    existing_report_origin,
    harness_provenance,
    report_has_measurement,
    write_validation_report,
)

__all__ = ["cmd_validate", "main"]


def _write_refusal(path: Path, report: dict, *, replace_recorded: bool) -> str | None:
    """Why this run may not replace the report at *path*, or None.

    Two independent guards, because the reported defect was two failures
    composing: a sweep that measures nothing still replaced the file, and it
    still exited 0.
    """
    if not report_has_measurement(report):
        return (
            f"refusing to write {path}: this run measured nothing -- every entry is "
            "an error placeholder, or there were no entries at all. The report on "
            "disk is left exactly as found."
        )
    origin = existing_report_origin(path)
    if origin in ("absent", "harness") or replace_recorded:
        return None
    return (
        f"refusing to write {path}: the report already there was recorded by "
        f"'{origin}', not by this harness, so this code cannot reproduce what it "
        "would destroy. Re-run with --replace-recorded to supersede it deliberately."
    )


def cmd_validate(
    project_root: Path,
    *,
    full_sweep: bool,
    satisfies: list[str] | None = None,
    replace_recorded: bool = False,
) -> tuple[dict, bool]:
    report, ok = validate_task_requirements(project_root, satisfies or [], full_sweep=full_sweep)
    # Review round 3, Critical 2: every validation report on disk declares who
    # or what recorded it. This is the one place the canonical report is
    # produced from a real measurement sweep, so it is the one place entitled
    # to stamp `recorded_by: "harness"`.
    command = "coherence-measurement run" + ("" if not full_sweep else " --all")
    for sr_id in satisfies or []:
        command += f" --satisfies {sr_id}"
    report = {"provenance": harness_provenance(command), **report}
    path = project_root / "validation" / "validation-report.json"
    refusal = _write_refusal(path, report, replace_recorded=replace_recorded)
    if refusal is not None:
        # Deliberately stricter than validate_task_requirements' own `ok`. That
        # function answers "did THIS TASK's own SRs come out clean" and is right
        # to treat an unrelated periodic setup gap as a warning (see
        # tests/unit/validation/test_pipeline.py::
        # test_unrelated_periodic_sr_error_stays_a_warning, SR-010's own
        # accepted evidence). cmd_validate answers a different question -- did
        # this invocation produce a durable record at all -- and a run that
        # wrote nothing must not exit 0. Do not "simplify" these two back into
        # agreement; that reintroduces exit-0-while-destroying-the-file.
        print(refusal, file=sys.stderr)
        return {**report, "write_skipped": refusal}, False
    write_validation_report(path, report)
    return report, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-measurement")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--project-root", default=Path("."), type=Path)
    p_run.add_argument("--all", action="store_true", help="full sweep (include periodic SRs)")
    p_run.add_argument("--satisfies", action="append", default=[], metavar="SR-###")
    p_run.add_argument(
        "--replace-recorded",
        action="store_true",
        help="supersede a validation report this harness did not produce (hand-, "
        "agent-recorded, or unattributable). Without it such a report is left alone.",
    )
    args = parser.parse_args(argv)

    report, ok = cmd_validate(
        args.project_root,
        full_sweep=args.all,
        satisfies=args.satisfies,
        replace_recorded=args.replace_recorded,
    )
    print(json.dumps(report, indent=2))
    return 0 if ok else 1
