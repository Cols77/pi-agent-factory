"""`coherence status` -- one truthful, precedence-ordered picture of what needs
attention right now (Increment 5 Task 1, spec plan
docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md).

This module owns two things:

1. A pure contract -- `StatusLine`/`StatusSnapshot` -- and the precedence rule
   that picks one `StatusLine` as the snapshot's `primary` line. This half has
   no I/O and is exercised directly with fake probe results.
2. `status_snapshot(project_root)`, which concurrently runs five read-only
   probes (trace check, register check, current run checkpoint, newest audit
   age, membership --gate) over existing tool entry points -- it never
   reimplements their logic, only calls them and classifies the result.

Every `StatusLine` names its producer (`produced_by`, a fully-qualified
callable name) and carries an ordered `resolve_cmd` tuple (Increment 2B
contract: each item is one fully-substituted, ready-to-run command; never a
semicolon-joined string, never reordered or deduplicated). A probe that
raises is caught by `_run_probe` and still produces exactly one `StatusLine`
(`outcome="probe_error"`) -- a probe crash must never abort the whole
snapshot, and must never be reported as if nothing was pending.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# --------------------------------------------------------------------------
# Pure contract
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusLine:
    source: str
    outcome: str
    summary: str
    produced_by: str
    resolve_cmd: tuple[str, ...] | None
    observation_ref: str | None


@dataclass(frozen=True)
class StatusSnapshot:
    lines: tuple[StatusLine, ...]
    primary: StatusLine
    exit_code: int


# Precedence, worst first. `nothing_pending` is the only "clean" outcome --
# every other value, including one this module has never seen before, is
# treated as needing attention (see `_outcome_rank`'s fallback below), so a
# probe author cannot invent a new outcome string that silently reads as
# clean.
def _probe_inbox(project_root: Path) -> StatusLine:
    """Inbox triage (Inc 6 Task 4): surface an inbox with any pending item.

    Reads the pure `coherence.inbox.list_items` (never writes). A non-empty
    inbox is a pending triage gate; an empty one is clean. The summary and an
    ordered resolver are driven off the pure items.
    """
    from coherence.inbox import list_items

    items = list_items(project_root, _now_iso())
    if not items:
        return StatusLine(
            source="inbox",
            outcome="nothing_pending",
            summary="inbox empty",
            produced_by="coherence.inbox.list_items",
            resolve_cmd=None,
            observation_ref="inbox",
        )
    counts: dict[str, int] = {}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    kinds = ", ".join(f"{k}:{c}" for k, c in sorted(counts.items()))
    return StatusLine(
        source="inbox",
        outcome="pending_inbox",
        summary=f"inbox: {len(items)} item(s) ({kinds})",
        produced_by="coherence.inbox.list_items",
        resolve_cmd=(
            (f"coherence status --project-root {project_root}",) if items else None
        ),
        observation_ref="inbox",
    )


_PRECEDENCE: tuple[str, ...] = (
    "interrupted_run",
    "probe_error",
    "failing_gate",
    "stale_audit",
    "proposed_backlog",
    "pending_inbox",
    "nothing_pending",
)
_RANK = {name: index for index, name in enumerate(_PRECEDENCE)}


def _outcome_rank(outcome: str) -> int:
    # An unrecognized outcome is ranked as severe as a caught probe error
    # (never as low/clean as `nothing_pending`'s rank) -- a stale or errored
    # line must never be able to fall through to looking current.
    return _RANK.get(outcome, _RANK["probe_error"])


def snapshot_from_lines(lines: tuple[StatusLine, ...]) -> StatusSnapshot:
    """Pure precedence rule: `lines` itself comes back worst-first sorted by
    outcome rank, ties broken by declared order (stable sort -- first probe
    wins among equally-ranked outcomes, not `sorted`'s happenstance
    semantics, made explicit here since callers rely on it: both `primary`
    AND every consumer of the full `lines` list, e.g. the `/using-coherence`
    menu, depend on this ordering, not just the single worst line)."""
    if not lines:
        raise ValueError("snapshot_from_lines requires at least one StatusLine")
    sorted_lines = tuple(sorted(lines, key=lambda line: _outcome_rank(line.outcome)))
    primary = sorted_lines[0]
    exit_code = 0 if primary.outcome == "nothing_pending" else 1
    return StatusSnapshot(lines=sorted_lines, primary=primary, exit_code=exit_code)


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------


def _probe_trace_check(project_root: Path) -> StatusLine:
    from coherence.trace.cli import cmd_check

    text, code = cmd_check(project_root)
    summary = text.splitlines()[0] if text else "trace check"
    return StatusLine(
        source="trace_check",
        outcome="failing_gate" if code != 0 else "nothing_pending",
        summary=summary,
        produced_by="coherence.trace.cli.cmd_check",
        resolve_cmd=(
            (f"coherence trace check --project-root {project_root}",) if code != 0 else None
        ),
        observation_ref="trace:graph",
    )


def _probe_register_check(project_root: Path) -> StatusLine:
    from coherence.register.cli import cmd_check

    text, code = cmd_check(project_root)
    summary = text.splitlines()[0] if text else "register check"
    return StatusLine(
        source="register_check",
        outcome="failing_gate" if code != 0 else "nothing_pending",
        summary=summary,
        produced_by="coherence.register.cli.cmd_check",
        resolve_cmd=(
            (f"coherence register check --project-root {project_root}",) if code != 0 else None
        ),
        observation_ref="register:requirements",
    )


def _probe_run_checkpoint(project_root: Path) -> StatusLine:
    from factory.orchestrator.run_cli import load_current_checkpoint

    checkpoint = load_current_checkpoint(project_root)
    if checkpoint is None:
        return StatusLine(
            source="run_checkpoint",
            outcome="nothing_pending",
            summary="no interrupted run",
            produced_by="factory.orchestrator.run_cli.load_current_checkpoint",
            resolve_cmd=None,
            observation_ref=None,
        )
    # Mirrors run_doctor's `interrupted_run` finding
    # (src/factory/orchestrator/run_cli.py::run_doctor) -- same condition
    # (checkpoint present, node not completed/closed already guaranteed by
    # load_current_checkpoint itself) and the same `run-state inspect`
    # resolver, but as a proper ordered resolve_cmd tuple, never the
    # semicolon-joined detail string run_doctor renders for humans.
    return StatusLine(
        source="run_checkpoint",
        outcome="interrupted_run",
        summary=(
            f"run {checkpoint.run_id} ({checkpoint.task_id}) is interrupted at "
            f"{checkpoint.node}"
        ),
        produced_by="factory.orchestrator.run_cli.load_current_checkpoint",
        resolve_cmd=(
            f"{sys.executable} -m factory.orchestrator run-state inspect "
            f"{checkpoint.run_id} --repo {project_root}",
        ),
        observation_ref=f"run:{checkpoint.run_id}",
    )


def _probe_membership_gate(project_root: Path) -> StatusLine:
    from coherence.navigate.cli import cmd_coverage

    result = cmd_coverage(project_root)
    unbundled = result.get("unbundled", [])
    summary = f"bundle coverage: {result.get('bundled', 0)}/{result.get('total', 0)} artifacts"
    if unbundled:
        return StatusLine(
            source="membership_gate",
            outcome="failing_gate",
            summary=f"{summary}; {len(unbundled)} unbundled",
            produced_by="coherence.navigate.cli.cmd_coverage",
            resolve_cmd=(f"coherence navigate membership --gate --repo-root {project_root}",),
            observation_ref="bundle:coverage",
        )
    return StatusLine(
        source="membership_gate",
        outcome="nothing_pending",
        summary=summary,
        produced_by="coherence.navigate.cli.cmd_coverage",
        resolve_cmd=None,
        observation_ref="bundle:coverage",
    )


def _now_iso() -> str:
    """Wall-clock now as an ISO-8601 UTC string (for inbox expiry checks)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_age(delta: timedelta) -> str:
    """Render a non-negative timedelta as a coarse, human-readable age --
    the largest whole unit that applies (days, else hours, else minutes,
    else "less than a minute")."""
    seconds = max(delta.total_seconds(), 0.0)
    days = int(seconds // 86400)
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''}"
    hours = int(seconds // 3600)
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    minutes = int(seconds // 60)
    if minutes >= 1:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return "less than a minute"


def _audit_age_phrase(generated_at_raw: str) -> str:
    """"last ran <age> ago" for the newest audit run's `generated_at`, computed
    against wall-clock now -- this is the actual age measurement the probe's
    name promises (review finding: the previous version only used
    `generated_at` to pick the newest run, never compared it to "now"). Falls
    back to a plain, non-crashing phrase for a missing/malformed timestamp
    rather than raising out of a status probe."""
    if not generated_at_raw:
        return "last ran at an unknown time"
    try:
        generated_at = datetime.fromisoformat(generated_at_raw)
    except ValueError:
        return "last ran at an unknown time"
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    age = _format_age(datetime.now(timezone.utc) - generated_at)
    return f"last ran {age} ago"


def _probe_audit_age(project_root: Path) -> StatusLine:
    """"Newest audit age" has no ready-made helper in this codebase (flagged
    as genuinely under-specified by the task brief) -- documenting the
    judgment call made here for review:

    - Read every recorded coverage-review run directly off disk (the layout
      coherence.audit.cli._run_dir already writes:
      `<root>/coverage-reviews/<feat>-<run_id>/{report.json,audit.json}`) --
      preferring the consolidated `report.json`, falling back to `audit.json`
      for a run that never reached consolidation. This only reads artifacts
      those existing commands already produce; it does not recompute an
      audit.
    - "Newest" = the run with the latest `generated_at` across every feature.
    - "Stale" reuses this codebase's one existing staleness vocabulary for
      audit scope -- `SrScope.checksum_state`
      ("current"/"stale"/"proposed", `coherence.audit.scope`, ultimately
      `coherence.register.register.is_checksum_current`) -- rather than
      inventing a new age-based threshold nothing else in the system uses:
      if the newest run recorded any SR whose checksum was already not
      "current" at audit time, that run's own evidence is known-stale, so
      `stale_audit`. This is about requirement-checksum staleness *as
      recorded by the audit*, not elapsed wall-clock time -- the
      outcome/precedence tier is deliberately not driven by age, per
      controller ruling (no age-threshold convention exists anywhere in this
      codebase to anchor an elapsed-time outcome to).
    - Wall-clock age IS surfaced, just not as the outcome driver: whenever a
      newest run is found (`stale_audit` or the clean `nothing_pending`
      branch below), its `generated_at` is compared to `datetime.now(utc)`
      and rendered into the summary via `_audit_age_phrase` (e.g. "last ran
      12 days ago") -- the one thing "newest audit age" as a probe name
      promises, now genuinely measured rather than only used to pick which
      run counts as newest.
    - If no coverage-review run has EVER been recorded, but
      `coherence.audit.cli.cmd_list_features` reports at least one declared
      feature, that is a real backlog: registered work nobody has audited
      yet -> `proposed_backlog` (ranks below `stale_audit`, above
      `nothing_pending`, per the brief's precedence order). The resolver
      names the alphabetically-first unaudited feature -- deterministic, not
      an arbitrary pick.
    - No features at all -> nothing to audit -> `nothing_pending`.
    """
    from coherence.audit.cli import cmd_list_features

    reviews_dir = project_root / "coverage-reviews"
    runs: list[tuple[str, str, dict]] = []
    if reviews_dir.is_dir():
        for run_dir in sorted(reviews_dir.glob("*")):
            if not run_dir.is_dir():
                continue
            payload_path = run_dir / "report.json"
            if not payload_path.exists():
                payload_path = run_dir / "audit.json"
            if not payload_path.exists():
                continue
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            runs.append(
                (str(payload.get("feature", "")), str(payload.get("run_id", "")), payload)
            )

    if runs:
        feat, run_id, payload = max(runs, key=lambda item: str(item[2].get("generated_at", "")))
        age_phrase = _audit_age_phrase(str(payload.get("generated_at", "")))
        srs = payload.get("srs", {})
        stale_srs = sorted(
            sr_id
            for sr_id, sr in srs.items()
            if isinstance(sr, dict) and sr.get("checksum_state") not in (None, "current")
        )
        if stale_srs:
            return StatusLine(
                source="audit_age",
                outcome="stale_audit",
                summary=(
                    f"newest audit {feat} {run_id} ({age_phrase}) recorded {len(stale_srs)} "
                    f"stale-checksum SR(s): {', '.join(stale_srs)}"
                ),
                produced_by="coherence.status._probe_audit_age",
                resolve_cmd=(f"coherence audit run {feat} --project-root {project_root}",),
                observation_ref=f"audit:{feat}:{run_id}",
            )
        return StatusLine(
            source="audit_age",
            outcome="nothing_pending",
            summary=f"newest audit {feat} {run_id} ({age_phrase}) is current",
            produced_by="coherence.status._probe_audit_age",
            resolve_cmd=None,
            observation_ref=f"audit:{feat}:{run_id}",
        )

    features = cmd_list_features(project_root)
    if features:
        backlog_feat = sorted(f["id"] for f in features)[0]
        return StatusLine(
            source="audit_age",
            outcome="proposed_backlog",
            summary=f"{len(features)} feature(s) declared; none has ever been audited",
            produced_by="coherence.status._probe_audit_age",
            resolve_cmd=(f"coherence audit run {backlog_feat} --project-root {project_root}",),
            observation_ref=None,
        )
    return StatusLine(
        source="audit_age",
        outcome="nothing_pending",
        summary="no features declared; nothing to audit",
        produced_by="coherence.status._probe_audit_age",
        resolve_cmd=None,
        observation_ref=None,
    )


_PROBES: tuple[tuple[str, Callable[[Path], StatusLine]], ...] = (
    ("trace_check", _probe_trace_check),
    ("register_check", _probe_register_check),
    ("run_checkpoint", _probe_run_checkpoint),
    ("audit_age", _probe_audit_age),
    ("membership_gate", _probe_membership_gate),
    ("inbox", _probe_inbox),
)


def _run_probe(source: str, probe: Callable[[Path], StatusLine], project_root: Path) -> StatusLine:
    try:
        return probe(project_root)
    except Exception as exc:  # noqa: BLE001 -- a probe crash must still yield one line, never abort the snapshot
        return StatusLine(
            source=source,
            outcome="probe_error",
            summary=f"{source} probe failed: {exc}",
            produced_by=f"coherence.status._probe_{source}",
            resolve_cmd=None,
            observation_ref=None,
        )


def status_snapshot(project_root: Path) -> StatusSnapshot:
    """Concurrently run every probe (each isolated by `_run_probe`, so one
    probe's crash never takes down the rest) and fold the results through the
    pure precedence rule."""
    project_root = Path(project_root)
    with ThreadPoolExecutor(max_workers=len(_PROBES)) as executor:
        futures = [
            executor.submit(_run_probe, source, probe, project_root)
            for source, probe in _PROBES
        ]
        lines = tuple(future.result() for future in futures)
    return snapshot_from_lines(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _snapshot_payload(snapshot: StatusSnapshot) -> dict:
    return {
        "primary": asdict(snapshot.primary),
        "exit_code": snapshot.exit_code,
        "lines": [asdict(line) for line in snapshot.lines],
    }


def _render_resolve_cmd(resolve_cmd: tuple[str, ...] | None, indent: str) -> list[str]:
    if not resolve_cmd:
        return []
    rendered = [f"{indent}resolve:"]
    rendered.extend(f"{indent}  - {command}" for command in resolve_cmd)
    return rendered


def _render_snapshot(snapshot: StatusSnapshot) -> str:
    primary = snapshot.primary
    lines = [f"status: {primary.outcome} [{primary.source}]", f"  {primary.summary}"]
    lines.extend(_render_resolve_cmd(primary.resolve_cmd, "  "))
    lines.append("")
    lines.append("all probes:")
    for line in snapshot.lines:
        lines.append(f"  [{line.source}] {line.outcome}: {line.summary}")
        lines.extend(_render_resolve_cmd(line.resolve_cmd, "    "))
    return "\n".join(lines)


def inbox_triage(project_root: Path, now: str) -> list[dict]:
    """Return the pure inbox as JSON-shaped triage items (Inc 6 Task 4).

    The Pi renderer consumes InboxItem JSON only; this is that JSON.
    """
    from coherence.inbox import list_items

    return [item.to_dict() for item in list_items(project_root, now)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-status")
    parser.add_argument("--project-root", default=Path("."), type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    snapshot = status_snapshot(args.project_root)
    if args.json:
        payload = _snapshot_payload(snapshot)
        try:
            from coherence.runs.service import list_run_statuses

            rows = list_run_statuses(args.project_root)
            from coherence.runs.transport import serialize_run_statuses

            runs = serialize_run_statuses(rows)
            payload["runs"] = runs.get("runs", [])
        except Exception:  # noqa: BLE001 -- a run-projection fault must not break the snapshot
            payload["runs"] = []
        print(json.dumps(payload, indent=2))
    else:
        print(_render_snapshot(snapshot))
    return snapshot.exit_code


__all__ = [
    "StatusLine",
    "StatusSnapshot",
    "snapshot_from_lines",
    "status_snapshot",
    "main",
]
