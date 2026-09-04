"""Git commit range -> evidence manifest (SR-049/AC-2).

The ONLY module in the review path that reads git, and it reads it through
``substrate.vcs.CommitReader`` rather than opening a second subprocess
convention: ``factory.orchestrator.git_ops.SubprocessGitOps`` exposes the same
reads on the ``GitOps`` protocol by delegating to the same ``substrate.vcs``
functions, so either object can be passed here and there is one implementation
of each git command. (``coherence.register`` may not import ``factory.*`` --
``tests/unit/requirements/test_coherence_parity.py`` enforces that layering.)

Everything downstream -- ``coherence.register.review``, the gate, the fidelity
packet -- continues to read evidence manifests exactly as before, preserving
the constraint documented in
``coherence.register.review.unaccounted_changed_files``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coherence.register.claims import (
    ClaimsConfig,
    exempting_glob,
    load_claims_config,
    parse_sr_trailer,
)
from substrate.evidence.model import validate_run_manifest
from substrate.evidence.read import list_run_manifests
from substrate.vcs import CommitReader, SubprocessCommitReader

# sha256 of the empty byte string. An ingestion run records no patch of its own
# -- the commits it ingests are the artifact, and each already carries its own
# diff in git -- but the manifest schema requires a patch blob, so the empty
# digest states "no patch" honestly rather than inventing a hash.
EMPTY_PATCH_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class DivergedRangeError(RuntimeError):
    """The recorded start commit is not an ancestor of HEAD.

    A branch switch, or history rewritten after a manifest was written. There
    is no meaningful range, so ingestion reports and ingests nothing rather
    than guessing a merge base.
    """


@dataclass(frozen=True)
class IngestedCommit:
    sha: str
    subject: str
    sr_ids: tuple[str, ...]
    changed_files: tuple[str, ...]
    exempted: tuple[tuple[str, str], ...]  # (path, exempting glob)


def ingest_range(
    root: Path,
    git: CommitReader,
    start_commit: str,
    end_commit: str,
    config: ClaimsConfig,
) -> tuple[IngestedCommit, ...]:
    """Every commit in (start, end], with its claims and exemption facts."""
    if not git.is_ancestor(root, start_commit, end_commit):
        raise DivergedRangeError(
            f"{start_commit[:12]} is not an ancestor of {end_commit[:12]}; "
            "history diverged since the last manifest -- ingesting nothing"
        )
    out: list[IngestedCommit] = []
    for sha, subject, body in git.commits_between(root, start_commit, end_commit):
        changed = tuple(git.changed_files_in_commit(root, sha))
        exempted = tuple(
            (path, glob)
            for path in changed
            if (glob := exempting_glob(config, path)) is not None
        )
        out.append(
            IngestedCommit(
                sha=sha,
                subject=subject,
                sr_ids=parse_sr_trailer(f"{subject}\n\n{body}"),
                changed_files=changed,
                exempted=exempted,
            )
        )
    return tuple(out)


def _newest_result_commit(root: Path) -> str | None:
    """The result commit of the newest manifest already on disk, if any.

    ``list_run_manifests`` takes the evidence *directory* and looks inside its
    ``runs/`` subdirectory itself, and returns newest-first -- so the first
    manifest carrying a result commit is where the last ingestion (or run)
    left off.
    """
    for manifest in list_run_manifests(root / "evidence"):
        commit = manifest.get("result_commit")
        if isinstance(commit, str) and commit:
            return commit
    return None


def _range_start(root: Path, ops: CommitReader, config: ClaimsConfig) -> str | None:
    """Where ingestion resumes from.

    In order: the newest manifest's result commit (the normal case, so each run
    ingests only what is new); the configured epoch (adoption, before any
    manifest records a commit range); the repository's root commit (a
    repository with neither). Never a synthesised sha.
    """
    recorded = _newest_result_commit(root)
    if recorded:
        return recorded
    if config.epoch:
        return config.epoch
    return ops.root_commit(root)


def ingest(
    root: Path, *, git: CommitReader | None = None, now: datetime | None = None
) -> Path | None:
    """Ingest the range since the newest manifest; return the manifest path.

    Returns None when there is nothing to ingest. Writes a NEW manifest --
    never mutates an existing one -- with the tmp-then-replace pattern the rest
    of the codebase already uses.

    No ``task_id``/``inputs.task`` is recorded: an ingestion run outside a
    governed task has no task, and synthesising one would fabricate provenance.
    """
    ops = git or SubprocessCommitReader()
    config = load_claims_config(root)
    head = ops.head_commit(root)
    start = _range_start(root, ops, config)
    commits = ingest_range(root, ops, start, head, config) if start else ()
    if not commits:
        return None
    timestamp = now or datetime.now(UTC)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    iso = timestamp.isoformat().replace("+00:00", "Z")
    run_id = f"ingest-{stamp}"
    changed: list[str] = []
    for commit in commits:
        for path in commit.changed_files:
            if path not in changed:
                changed.append(path)
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "started_at": iso,
        "ended_at": iso,
        "start_commit": start,
        "result_commit": head,
        "outcome": "completed",
        "inputs": {"requirements": [], "factory_config_sha256": "0" * 64},
        "dependencies": [
            {
                "name": "candidate-tree",
                "kind": "git-tree",
                "digest": f"git-tree:{head}",
                "source": head,
            }
        ],
        "implementation": {
            "changed_files": changed,
            "patch": {"sha256": EMPTY_PATCH_SHA, "size": 0, "media_type": "text/x-diff"},
        },
        "commits": [
            {
                "sha": c.sha,
                "subject": c.subject,
                "sr_ids": list(c.sr_ids),
                "changed_files": list(c.changed_files),
                "exempted": [{"path": p, "glob": g} for p, g in c.exempted],
            }
            for c in commits
        ],
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    validate_run_manifest(manifest)
    out = root / "evidence" / "runs" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out


__all__ = [
    "EMPTY_PATCH_SHA",
    "DivergedRangeError",
    "IngestedCommit",
    "ingest",
    "ingest_range",
]
