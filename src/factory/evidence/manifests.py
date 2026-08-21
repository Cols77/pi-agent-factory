from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from substrate.evidence.model import (
    is_spec20_run_manifest,
    validate_run_manifest,
    validate_spec20_manifest,
)

if TYPE_CHECKING:
    # Static-analysis-only: gives pyright the real substrate names for any
    # caller's annotations, without adding a runtime import -- actual
    # runtime access still goes through __getattr__ below, which is what
    # emits the deprecation warning.
    from substrate.evidence.model import MANIFEST_SCHEMA_VERSION as MANIFEST_SCHEMA_VERSION
    from substrate.evidence.read import list_run_manifests as list_run_manifests
    from substrate.evidence.read import load_run_manifest as load_run_manifest

# write_run_manifest is the sole atomic writer and stays here permanently --
# it is NOT deprecated, so importing this module for it alone must not warn.
# load_run_manifest/list_run_manifests/MANIFEST_SCHEMA_VERSION moved to
# substrate.evidence.read/model; they are exposed below as a lazy,
# per-attribute warn-and-reexport shim (PEP 562 module __getattr__) rather
# than the usual whole-module warnings.warn(), specifically so that write
# usage (the canonical, permanent surface, called on every normal run) is
# never spuriously flagged deprecated merely for importing this module.
# (Deliberately not listed in __all__: pyright's static analysis does not
# see names that only exist via __getattr__, and flags a listed-but-absent
# name -- this is a false positive, not a missing export; `from
# factory.evidence.manifests import load_run_manifest` still resolves fine
# at runtime via PEP 562.)
__all__ = ["write_run_manifest"]
_REEXPORT_TARGETS = {
    "MANIFEST_SCHEMA_VERSION": "substrate.evidence.model",
    "load_run_manifest": "substrate.evidence.read",
    "list_run_manifests": "substrate.evidence.read",
}


def __getattr__(name: str) -> Any:
    target_module = _REEXPORT_TARGETS.get(name)
    if target_module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"factory.evidence.manifests.{name} is deprecated; import {target_module}.{name}",
        DeprecationWarning,
        stacklevel=2,
    )
    module = __import__(target_module, fromlist=[name])
    return getattr(module, name)


def _write_json_atomic(path: Path, manifest: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_run_manifest(evidence_dir: Path, manifest: dict) -> Path:
    """Write a run manifest: §20 simulation bundles as RUN-<run>/manifest.json,
    v1 orchestration manifests as flat runs/<run_id>.json. Additive; v1 callers
    and files are unchanged. Shape detection and validation are delegated to
    the substrate normaliser (substrate.evidence.model)."""
    runs = evidence_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    if is_spec20_run_manifest(manifest):
        defaults = {"feature": None, "requirements": [], "commit": None, "result": None}
        normalized = {**defaults, **manifest}
        validate_spec20_manifest(normalized)
        path = runs / normalized["run"] / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, normalized)
        return path
    validate_run_manifest(manifest)
    path = runs / f"{manifest['run_id']}.json"
    _write_json_atomic(path, manifest)
    return path
