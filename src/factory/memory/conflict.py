"""Fingerprint-based conflict surfacing for durable memory (Inc 8, Task 3).

``factory.memory.durable.query_memory`` surfaces STRUCTURAL conflicts — a
``reproduced_by`` run no evidence manifest records, a ``superseded_by`` ADR
nobody declares. This module goes deeper: it compares what a memory note
CITES — code files (``code:<path>`` refs in root_cause/fix/hypothesis
evidence), commits (40-hex SHAs), and runs (``reproduced_by`` / hypothesis
``evidence``) — against the repo's CURRENT state, reusing the same
``factory.freshness`` fingerprint machinery the evidence layer records run
dependencies with. On mismatch it emits the pair {memory claim, current
evidence} and never resolves it (brief §5.6: shows the conflict rather than
choosing; D9).

A note AGREES when the cited artifact's current fingerprint/state matches
what the note relies on; it CONFLICTS when it does not:

- ``code-changed`` — a cited code file's current fingerprint differs from the
  digest a cited run manifest recorded for it (the file changed since the
  run the note relies on; ``fingerprint_file`` may also answer ``missing``
  when the file has vanished);
- ``commit-unreachable`` — a cited commit object is not an ancestor of HEAD
  (the commit the note relies on is no longer reachable);
- ``run-superseded`` — a cited run's recorded evidence no longer matches
  current state: its ``result_commit`` is not HEAD-reachable, or a
  dependency digest it recorded differs from the file's current fingerprint.

Every check degrades deterministically and never guesses: no git baseline,
an unreadable/invalid run manifest, a cited path with no recorded digest, a
40-hex token that is not a commit object — each is skipped, never flagged.
Nothing here writes; conflicts are shown, never silently resolved.

``query_conflicts`` composes ``durable.query_memory`` for scope resolution
(the same ``all`` / ``feat:`` / ``sr:`` / ``goal:`` / ``adr:`` / ``fr:``
refs) and merges the structural conflicts with these fingerprint conflicts,
sorted by (kind, memory id, memory field) — one read, both sides shown.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from factory.delta import git_ops
from factory.evidence import manifests as evidence_manifests
from factory.freshness.fingerprint import fingerprint_file
from factory.memory.durable import _run_ref_detected
from factory.memory.durable import query_memory as _durable_query_memory
from factory.system._claims import evidence_dir as _evidence_dir
from factory.system._claims import fresh as _fresh
from factory.system._claims import manifest_path as _manifest_path
from factory.system.models import to_dict

#: A `code:<path>` citation inside note prose (`code:navigation/preemption.py`).
_CODE_REF = re.compile(r"code:([A-Za-z0-9_./-]+)")
#: A full commit sha candidate inside note prose.
_SHA40 = re.compile(r"\b[0-9a-f]{40}\b")


def _cited_code_paths(*texts: str) -> list[str]:
    """Every distinct ``code:<path>`` ref cited, in first-appearance order."""
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        if not isinstance(text, str):
            continue
        for match in _CODE_REF.finditer(text):
            path = match.group(1)
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def _cited_shas(*texts: str) -> list[str]:
    """Every distinct 40-hex token cited, in first-appearance order."""
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        if not isinstance(text, str):
            continue
        for match in _SHA40.finditer(text.lower()):
            sha = match.group(0)
            if sha not in seen:
                seen.add(sha)
                out.append(sha)
    return out


def _notes(record: dict, hypotheses: list[dict]) -> list[dict]:
    """Every memory note of a record: its own fields plus each rejected
    hypothesis's text fields.

    Each note carries the ``id``/``field``/``citation`` that durable's
    conflict contract uses for the memory side — a hypothesis's conflicts
    name the hosting record (``record``), like durable's missing-run
    conflicts do, so the pair never loses its provenance.
    """
    record_id = record.get("id") or ""
    citation = record.get("citation")
    notes = [
        {
            "id": record_id,
            "field": "reproduced_by",
            "text": record.get("reproduced_by") or "",
            "citation": citation,
        },
        {
            "id": record_id,
            "field": "root_cause",
            "text": record.get("root_cause") or "",
            "citation": citation,
        },
        {
            "id": record_id,
            "field": "fix",
            "text": record.get("fix") or "",
            "citation": citation,
        },
        {
            "id": record_id,
            "field": "regression_link",
            "text": record.get("regression_link") or "",
            "citation": citation,
        },
    ]
    for hypothesis in hypotheses:
        for field in ("hypothesis", "why_rejected", "evidence"):
            notes.append(
                {
                    "id": hypothesis.get("record") or record_id,
                    "field": field,
                    "text": hypothesis.get(field) or "",
                    "citation": hypothesis.get("citation") or citation,
                }
            )
    return notes


def _run_refs_in(note: dict) -> list[str]:
    """Run ids a note's whole value cites, run refs only.

    Uses the same detection durable.py applies to ``reproduced_by`` and
    hypothesis ``evidence``, so the two run-ref fields cannot drift: task
    refs (``task:T-###`` / bare ``T-###``) are never treated as runs.
    """
    text = note["text"]
    if isinstance(text, str) and _run_ref_detected(text):
        run_id = text[len("run:") :] if text.startswith("run:") else text
        return [run_id] if run_id else []
    return []


def _run_ids_of(notes: list[dict]) -> list[str]:
    """Every run id the record's notes cite, in first-appearance order."""
    out: list[str] = []
    for note in notes:
        for run_id in _run_refs_in(note):
            if run_id not in out:
                out.append(run_id)
    return out


def _load_run_manifest(repo_root: Path, run_id: str) -> dict | None:
    """The recorded v1 manifest for ``run_id``, or None when absent/
    unreadable/invalid. A missing run is durable's structural ``missing-run``
    conflict; here it simply means there is no recorded fingerprint to
    compare against."""
    try:
        return evidence_manifests.load_run_manifest(
            _manifest_path(_evidence_dir(repo_root), run_id)
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _recorded_file_digests(manifest: dict | None, path: str) -> list[str]:
    """Digests a manifest recorded for a repo-relative file path (kind
    ``file``, exact source match — never fuzzy)."""
    if manifest is None:
        return []
    out: list[str] = []
    for dep in manifest.get("dependencies", []):
        if not isinstance(dep, dict) or dep.get("kind") != "file":
            continue
        if dep.get("source") == path and isinstance(dep.get("digest"), str):
            if dep["digest"] not in out:
                out.append(dep["digest"])
    return out


def _current_digest(repo_root: Path, path: str) -> str:
    """The repo-relative file's current fingerprint, or ``missing`` when the
    file is absent/unreadable — same ``factory.freshness`` primitive the
    evidence layer uses, never a re-implementation."""
    try:
        return fingerprint_file(f"memory:{path}", repo_root / path, repo_root).digest
    except OSError:
        return "missing"


def _conflict(kind: str, memory: dict, evidence: str, citation: dict) -> dict:
    """One conflict in durable's contract: {kind, memory{id, field, value},
    evidence, citation, freshness}. Both sides, never a resolution."""
    return {
        "kind": kind,
        "memory": memory,
        "evidence": evidence,
        "citation": citation,
        "freshness": to_dict(_fresh()),
    }


def _check_code_changed(
    repo_root: Path,
    notes: list[dict],
    run_ids: list[str],
    manifests: dict[str, dict | None],
) -> list[dict]:
    """A cited code file whose current fingerprint differs from the digest a
    cited run recorded for it is a ``code-changed`` conflict.

    A path with no recorded digest in any cited run cannot be compared and
    is skipped, never guessed; a note that agrees with every recorded digest
    is not flagged.
    """
    conflicts: list[dict] = []
    for note in notes:
        for path in _cited_code_paths(note["text"]):
            recorded: list[tuple[str, str]] = []
            for run_id in run_ids:
                manifest = manifests.get(run_id)
                if manifest is None:
                    continue
                for digest in _recorded_file_digests(manifest, path):
                    recorded.append((run_id, digest))
            if not recorded:
                continue
            current = _current_digest(repo_root, path)
            if current in {digest for _, digest in recorded}:
                continue
            runs = ", ".join(sorted({run for run, _ in recorded}))
            digests = ", ".join(sorted({digest for _, digest in recorded}))
            conflicts.append(
                _conflict(
                    "code-changed",
                    {
                        "id": note["id"],
                        "field": note["field"],
                        "value": f"code:{path}",
                    },
                    f"{path}: recorded {digests} by run(s) {runs}; "
                    f"current fingerprint {current}",
                    note["citation"],
                )
            )
    return conflicts


def _check_commit_unreachable(
    repo_root: Path, notes: list[dict], head: str | None
) -> list[dict]:
    """A cited 40-hex token that resolves to a commit object but is not an
    ancestor of HEAD is a ``commit-unreachable`` conflict.

    Tokens that are not commit objects (blob digests, unknown shas) are
    skipped, never guessed; without a git baseline nothing is checked.
    """
    if head is None:
        return []
    conflicts: list[dict] = []
    for note in notes:
        for sha in _cited_shas(note["text"]):
            if not git_ops.commit_exists(repo_root, sha):
                continue
            if git_ops.is_ancestor(repo_root, sha, "HEAD"):
                continue
            conflicts.append(
                _conflict(
                    "commit-unreachable",
                    {"id": note["id"], "field": note["field"], "value": sha},
                    f"commit {sha} is not an ancestor of HEAD ({head})",
                    note["citation"],
                )
            )
    return conflicts


def _check_run_superseded(
    repo_root: Path,
    notes: list[dict],
    manifests: dict[str, dict | None],
    head: str | None,
) -> list[dict]:
    """A cited run whose recorded evidence no longer matches current state is
    a ``run-superseded`` conflict: its ``result_commit`` is not HEAD-reachable,
    or a recorded file dependency digest differs from the file's current
    fingerprint. A run with no manifest is durable's structural
    ``missing-run`` conflict and is skipped here."""
    conflicts: list[dict] = []
    for note in notes:
        for run_id in _run_refs_in(note):
            manifest = manifests.get(run_id)
            if manifest is None:
                continue
            mismatches: list[str] = []
            result_commit = manifest.get("result_commit")
            if isinstance(result_commit, str) and head is not None:
                if git_ops.commit_exists(repo_root, result_commit) and not git_ops.is_ancestor(
                    repo_root, result_commit, "HEAD"
                ):
                    mismatches.append(
                        f"validated commit {result_commit} is not an ancestor "
                        f"of HEAD ({head})"
                    )
            for dep in manifest.get("dependencies", []):
                if not isinstance(dep, dict) or dep.get("kind") != "file":
                    continue
                source, recorded = dep.get("source"), dep.get("digest")
                if not isinstance(source, str) or not isinstance(recorded, str):
                    continue
                current = _current_digest(repo_root, source)
                if current != recorded:
                    mismatches.append(
                        f"{source}: recorded {recorded}, current fingerprint {current}"
                    )
                    break
            if mismatches:
                conflicts.append(
                    _conflict(
                        "run-superseded",
                        {
                            "id": note["id"],
                            "field": note["field"],
                            "value": note["text"],
                        },
                        f"run {run_id} no longer matches current state; "
                        + "; ".join(mismatches),
                        note["citation"],
                    )
                )
    return conflicts


def query_conflicts(repo_root: Path, scope_ref: str) -> dict:
    """One read of memory conflicts for a scope: durable's structural
    conflicts (missing run/ADR links) merged with the fingerprint conflicts
    (code-changed / commit-unreachable / run-superseded), both sides shown,
    never silently resolved.

    Scope resolution is delegated to ``durable.query_memory`` — the same
    ``all`` / ``feat:`` / ``sr:`` / ``goal:`` / ``adr:`` / ``fr:`` refs with
    the same exact-ref rule, never a re-implementation. Out-of-scope records
    never drag their own conflicts into a scope's read.
    """
    projection = _durable_query_memory(repo_root, scope_ref)
    head = git_ops.head_commit(repo_root)

    conflicts: list[dict] = list(projection["conflicts"])

    hypotheses_by_record: dict[str, list[dict]] = {}
    for hypothesis in projection["rejected_hypotheses"]:
        hypotheses_by_record.setdefault(hypothesis.get("record") or "", []).append(hypothesis)

    for record in projection["failure_records"]:
        record_id = record.get("id") or ""
        notes = _notes(record, hypotheses_by_record.get(record_id, []))
        run_ids = _run_ids_of(notes)
        manifests = {run_id: _load_run_manifest(repo_root, run_id) for run_id in run_ids}
        conflicts.extend(_check_code_changed(repo_root, notes, run_ids, manifests))
        conflicts.extend(_check_commit_unreachable(repo_root, notes, head))
        conflicts.extend(_check_run_superseded(repo_root, notes, manifests, head))

    conflicts.sort(key=lambda c: (c["kind"], c["memory"]["id"], c["memory"].get("field", "")))
    return {"scope": scope_ref, "conflicts": conflicts}
