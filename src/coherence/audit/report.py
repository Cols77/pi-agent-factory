from __future__ import annotations


def render_human_summary(report: dict) -> str:
    """Return a plain-text human summary of the coverage report."""
    lines: list[str] = []
    lines.append(f"Coverage Review: {report.get('feature', '?')}")
    lines.append(f"Run: {report.get('run_id', '?')}")
    lines.append(f"Generated: {report.get('generated_at', '?')}")
    lines.append("")

    gate = report.get("gate", {})
    outcome = gate.get("outcome", "unknown")
    lines.append(f"Gate: {outcome.upper()}")
    if gate.get("failed"):
        lines.append(f"  FAILED: {', '.join(gate['failed'])}")
    if gate.get("degraded"):
        lines.append(f"  DEGRADED: {', '.join(gate['degraded'])}")
    if gate.get("warned"):
        lines.append(f"  WARNED: {', '.join(gate['warned'])}")
    lines.append("")

    scope = report.get("scope", {})
    lines.append(f"Declared SRs: {len(scope.get('declared', []))}")
    lines.append(f"Linked SRs:   {len(scope.get('linked', []))}")
    task_ids = {
        t.get("task_id")
        for sr in report.get("srs", {}).values()
        for t in sr.get("tasks", [])
    }
    lines.append(f"Tasks:        {len(task_ids)}")
    lines.append("")

    completeness = report.get("completeness", [])
    if completeness:
        lines.append("Completeness findings:")
        for f in completeness:
            lines.append(f"  - {f.get('kind', '?')}: {f.get('sr_id', '?')}")
        lines.append("")

    for sr_id, sr_data in sorted(report.get("srs", {}).items()):
        lines.append(f"--- {sr_id} ---")
        lines.append(f"  Statement: {sr_data.get('statement', '?')[:80]}")
        lines.append(f"  Checksum: {sr_data.get('checksum_state', '?')}")
        lines.append(f"  Tasks: {len(sr_data.get('tasks', []))}")
        meas = sr_data.get("measurement")
        if meas:
            lines.append(
                f"  Measured: {meas.get('passed')} "
                f"({meas.get('value', '?')} vs {meas.get('assert', '?')})"
            )
        else:
            lines.append("  Measured: (none)")
        if sr_data.get("states"):
            state, notes = sr_data["states"][0]
            lines.append(f"  State: {state}")
            for note in notes:
                lines.append(f"    - {note}")
        lines.append("")

    lines.append(f"Outcome: {outcome}")

    return "\n".join(lines)


__all__ = ["render_human_summary"]
