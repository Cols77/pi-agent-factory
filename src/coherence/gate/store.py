"""Atomic, validated persistence for explicit gate decisions.

A `DecisionFile` has ``schema=1`` and is stored at
``<run_dir>/gate-decisions/<gate_id>.json``. Both `write_decision` and
`load_decision` flow through `DecisionFile` validation, so a file the store
writes is always valid and a file the store reads that validates is always
accepted; a non-validating or malformed file raises the typed
`CorruptDecisionFile` diagnostic on read (never a silent ``{}``).

`write_decision` refuses any non-validating content *before* writing and
writes atomically (same-directory temporary file + ``os.replace``), so a
concurrent reader never observes a partial file.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from coherence.gate.model import CorruptDecisionFile, DecisionFile, validate_decisions


def decision_path(run_dir: Path | str, gate_id: str) -> Path:
    """The canonical on-disk path for one gate's decision file.

    The gate id (e.g. ``coverage:FEAT-001``) is used to name the file, but a
    windows-unsafe ``:`` in the id is substituted in the *filename* only; the
    canonical gate id always lives verbatim inside the JSON content, so
    round-trip fidelity is preserved on every platform.
    """
    return Path(run_dir) / "gate-decisions" / f"{_filename_safe(gate_id)}.json"


def _filename_safe(gate_id: str) -> str:
    """Make a gate id safe to use as a filename on Windows/Unix.

    Colons (and any other path-unsafe character) are replaced so the file can
    be written and atomically replaced on every platform; the gate id is
    stored verbatim in the JSON payload.
    """
    return "".join(
        char if char.isalnum() or char in "._-" else "-" for char in gate_id
    )


def write_decision(run_dir: Path | str, file: DecisionFile) -> Path:
    """Validate `file` then persist it atomically to its gate path.

    Content that fails validation is refused before any write. Returns the
    path written.
    """
    # Re-validate at the store boundary so non-validating content is refused
    # before any write touches disk. (Construction already validates, but the
    # store re-checks to make that contract explicit and defence-in-depth.)
    validate_decisions(file.decisions)
    path = decision_path(run_dir, file.gate_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(file.to_dict(), indent=2) + "\n"
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        # Remove any temp residue if the write or rename raised mid-way.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


def load_decision(path: Path | str) -> "DecisionFile":
    """Load and validate a decision file.

    A malformed or non-validating file raises the typed `CorruptDecisionFile`
    diagnostic (never a bare ``JSONDecodeError`` and never a silent empty
    set / ``{}``). A missing file is also reported as corrupt: there is no
    decision to short-circuit on.
    """
    p = Path(path)
    if not p.is_file():
        raise CorruptDecisionFile(f"no decision file at {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorruptDecisionFile(f"cannot read decision file {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CorruptDecisionFile(f"decision file {p} is not a JSON object")
    return DecisionFile.from_dict(raw)