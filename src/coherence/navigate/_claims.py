"""Shared, low-level helpers for the system navigator query layer.

Centralizes rules that must apply identically wherever a claim is built or a
repo-relative artifact directory/path is resolved -- freshness construction,
the recorded/missing claim shape, sha256 hashing, and the well-known
`tasks/`/`evidence/` directories and per-run manifest path.
`coherence.navigate.queries` and `coherence.navigate.story` both import from here
rather than each keeping its own copy; a future change to freshness or claim
construction must apply everywhere at once, not silently diverge between
modules (the "no parallel rules" constraint this package holds itself to).

Nothing here queries anything -- these are the same small, pure building
blocks `query_brief`/`query_matrix`/`query_timeline`/`query_story` each
compose in their own way.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from coherence.navigate.models import ClaimClass, Freshness, FreshnessState, SystemClaim


def tasks_dir(repo_root: Path) -> Path:
    return repo_root / "tasks"


def evidence_dir(repo_root: Path) -> Path:
    return repo_root / "evidence"


def manifest_path(evidence_dir_path: Path, run_id: str) -> Path:
    """Path to the durable manifest file for `run_id`.

    `evidence/runs/<run_id>.json` is always a *file* (`factory.evidence.
    manifests.write_run_manifest`), never a directory -- this is the one
    place that path is built, so both callers agree on it.
    """
    return evidence_dir_path / "runs" / f"{run_id}.json"


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def fresh(reason: str | None = None) -> Freshness:
    return Freshness(state=FreshnessState.FRESH, reason=reason, dependencies=[])


def missing_claim(text: str, reason: str) -> SystemClaim:
    return SystemClaim(
        kind=ClaimClass.MISSING,
        text=text,
        freshness=Freshness(state=FreshnessState.NA, reason=reason, dependencies=[]),
    )

