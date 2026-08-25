"""Runs service -- the sole integration registry for unified run status.

Aggregates the five source adapters' internal :class:`RunStatusInput` rows and
assembles the public :class:`RunStatus` -- computing the deterministic
``blocking_obligation`` / ``blocking_obligation_resolve_cmd`` / ``rerun_allowed``
triplet (Increment 7 Task 5 addendum) from each run's OWN native ``requirement_ids``.

Only this module reads ``requirement_ids`` and converts an input into a public
status; no adapter imports or calls the assembly helper. The serialization of
the assembled rows is owned by ``coherence.runs.transport``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from coherence.runs.model import RunStatus, RunStatusInput

__all__ = ["list_run_statuses", "_blocking_for", "_assemble"]

_SOURCE_ORDER: tuple[str, ...] = (
    "factory",
    "audit",
    "measurement",
    "simulation",
    "experiment",
)


def _run_functions():
    from coherence.runs import (
        audit_adapter,
        experiment_adapter,
        factory_adapter,
        measurement_adapter,
        simulation_adapter,
    )

    return {
        "factory": factory_adapter.factory_run_status,
        "audit": audit_adapter.audit_run_status,
        "measurement": measurement_adapter.measurement_run_status,
        "simulation": simulation_adapter.simulation_run_status,
        "experiment": experiment_adapter.experiment_run_status,
    }


def iter_source_inputs(root: Path) -> Iterable[RunStatusInput]:
    """Yield every source's inputs in the canonical ``_SOURCE_ORDER``."""
    sources = _run_functions()
    for producer in _SOURCE_ORDER:
        for row in sources[producer](root):
            yield row


def _blocking_for(
    root: Path,
    requirement_ids: tuple[str, ...],
    *,
    policy_bound: bool,
    verdict_files: Mapping[str, Path],
    repeatable_policy: Mapping[str, bool],
    max_reruns: int,
    reruns_used: int,
) -> tuple[str | None, tuple[str, ...] | None, bool]:
    """Deterministic run -> obligation mapping (Increment 7 Task 5 addendum)."""
    from coherence.policy.compiler import compile_obligations

    candidates: list[tuple[str, object]] = []
    for req_id in sorted(requirement_ids):
        try:
            obligations = compile_obligations(root, f"sr:{req_id}")
        except Exception:  # noqa: BLE001 -- an SR that is not a resolvable trace artifact is missing context, treated as absent
            continue
        for ob in obligations:
            if (
                ob.kind in ("verification_result", "human_review")
                and ob.requiredness == "blocking"
                and ob.state != "satisfied"
            ):
                candidates.append((req_id, ob))
    if not candidates:
        return None, None, False
    # verification_result wins over human_review (it is the auto-rerunnable one;
    # a human_review winner must never auto-rerun). Within a kind, deterministic
    # first pick by (scope_ref, obligation id).
    candidates.sort(
        key=lambda item: (
            item[1].kind != "verification_result",
            item[1].scope_ref,
            item[1].id,
        )
    )
    req_id, winner = candidates[0]
    rerun_allowed = (
        winner.kind == "verification_result"
        and policy_bound
        and verdict_files.get(req_id) is not None
        and verdict_files[req_id].is_file()
        and repeatable_policy.get(req_id, False)
        and max_reruns > 0
        and reruns_used < max_reruns
        and bool(winner.resolve_cmd)
    )
    return winner.id, winner.resolve_cmd, rerun_allowed


def _assemble(
    root: Path,
    input_row: RunStatusInput,
    *,
    policy_bound: bool,
    verdict_files: Mapping[str, Path],
    repeatable_policy: Mapping[str, bool],
    max_reruns: int,
    reruns_used: int,
) -> RunStatus:
    blocking_id, blocking_cmd, rerun = _blocking_for(
        root,
        input_row.requirement_ids,
        policy_bound=policy_bound,
        verdict_files=verdict_files,
        repeatable_policy=repeatable_policy,
        max_reruns=max_reruns,
        reruns_used=reruns_used,
    )
    return RunStatus(
        producer=input_row.producer,
        run_id=input_row.run_id,
        state=input_row.state,
        observation_ref=input_row.observation_ref,
        artifacts=input_row.artifacts,
        resume_cmd=input_row.resume_cmd,
        updated_at=input_row.updated_at,
        diagnostics=input_row.diagnostics,
        terminal_observation_id=input_row.terminal_observation_id,
        blocking_obligation=blocking_id,
        blocking_obligation_resolve_cmd=blocking_cmd,
        rerun_allowed=rerun,
    )


def list_run_statuses(
    root: Path,
    *,
    policy_bound: bool = False,
    verdict_files: Mapping[str, Path] | None = None,
    repeatable_policy: Mapping[str, bool] | None = None,
    max_reruns: int = 0,
    reruns_used: int = 0,
) -> list[RunStatus]:
    """Aggregate and sort every source's status rows deterministically.

    Sorting is by producer (``_SOURCE_ORDER``) then run id. The same assembly
    inputs are supplied to every row; the blocking obligation resolves from
    each row's OWN requirement ids.
    """
    root = Path(root)
    rows: list[RunStatusInput] = list(iter_source_inputs(root))
    rows.sort(key=lambda row: (_SOURCE_ORDER.index(row.producer), row.run_id))
    return [
        _assemble(
            root,
            row,
            policy_bound=policy_bound,
            verdict_files=verdict_files or {},
            repeatable_policy=repeatable_policy or {},
            max_reruns=max_reruns,
            reruns_used=reruns_used,
        )
        for row in rows
    ]