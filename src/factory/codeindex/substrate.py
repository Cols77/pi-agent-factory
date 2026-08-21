"""Composition adapter for guarded reads of the existing code index."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import cast

from factory.codeindex.build import discover_source_files, fingerprint_for
from factory.codeindex.model import CodeIndex
from factory.codeindex.sigs import extract_signatures, preferred_engine
from factory.codeindex.store import ensure_fresh, load_latest
from substrate.artifacts import ProducerRef, SnapshotInputRef, SnapshotRef
from substrate.freshness.fingerprint import fingerprint_value
from substrate.freshness.recipes import (
    FingerprinterRegistry,
    FreshnessLimits,
    FreshnessRecipe,
    ResolutionClass,
    ResolverRegistry,
)


CODEMAP_FINGERPRINTER = "codemap/v1"
CODEMAP_RESOLVER = "codemap.ensure-fresh/v1"

CODEMAP_RECIPE = FreshnessRecipe(
    schema=1,
    output_kind="code-map",
    inputs=("project-profile", "source-set", "parser-engine"),
    fingerprinter=CODEMAP_FINGERPRINTER,
    resolver=CODEMAP_RESOLVER,
    resolution_class=ResolutionClass.derived_auto,
    limits=FreshnessLimits(attempts=1, timeout_s=cast(Real, 30)),
)


@dataclass(frozen=True)
class CodeMapInputs:
    """Repository context supplied by the factory composition boundary."""

    repo_root: Path
    files: tuple[str, ...] | None = None


def code_map_inputs(repo_root: Path, files: Sequence[str] | None = None) -> CodeMapInputs:
    """Bind the repository and optional source set used by the code-map adapter."""

    return CodeMapInputs(repo_root=repo_root, files=None if files is None else tuple(files))


def _context_from_inputs(inputs: Sequence[object] | CodeMapInputs) -> CodeMapInputs:
    if isinstance(inputs, CodeMapInputs):
        return inputs
    values = tuple(inputs)
    if len(values) == 1 and isinstance(values[0], CodeMapInputs):
        return values[0]
    if len(values) == 1 and isinstance(values[0], Path):
        return code_map_inputs(values[0])
    if len(values) == 2 and isinstance(values[0], Path):
        files = values[1]
        if files is None:
            return code_map_inputs(values[0])
        if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
            return code_map_inputs(values[0], cast(Sequence[str], files))
    raise TypeError("code-map inputs must contain a repository Path and optional source files")


def _source_files(context: CodeMapInputs) -> list[str]:
    return list(context.files) if context.files else discover_source_files(context.repo_root)


def _snapshot_fingerprint(
    source_fingerprint: str, engine: str, source_files: Sequence[str]
) -> str:
    return fingerprint_value(
        "code-map-inputs",
        {
            "parser-engine": engine,
            "source-set": source_fingerprint,
            "source-files": sorted(source_files),
        },
    ).digest


def _engine_for_files(repo_root: Path, files: Sequence[str]) -> str:
    """Mirror build_index's persisted engine selection using its extractor."""

    if not files:
        return "stdlib-ast"
    try:
        source = (repo_root / files[0]).read_text(encoding="utf-8", errors="replace")
        engine, _ = extract_signatures(Path(files[0]), source)
        return engine
    except OSError:
        return "stdlib-ast"


def code_map_fingerprinter(inputs: Sequence[object] | CodeMapInputs) -> str:
    """Fingerprint the same source set and parser engine used by ensure_fresh."""

    context = _context_from_inputs(inputs)
    files = _source_files(context)
    if not files:
        return "no-files"
    return _snapshot_fingerprint(
        fingerprint_for(files, context.repo_root),
        _engine_for_files(context.repo_root, files),
        files,
    )


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snapshot_inputs(index: CodeIndex) -> tuple[SnapshotInputRef, ...]:
    source_ref = "source-set:no-files" if index.fingerprint == "no-files" else f"source-set:{index.fingerprint}"
    source_hash = None if index.fingerprint == "no-files" else index.fingerprint
    engine_hash = fingerprint_value("parser-engine", index.engine).digest
    return (
        SnapshotInputRef(ref=source_ref, content_hash=source_hash),
        SnapshotInputRef(ref=f"parser-engine:{index.engine}", content_hash=engine_hash),
    )


def _snapshot_from_index(
    index: CodeIndex,
    supersedes: str | None = None,
    source_files: Sequence[str] | None = None,
) -> SnapshotRef:
    files = tuple(index.files) if source_files is None else tuple(source_files)
    fingerprint = (
        "no-files"
        if index.fingerprint == "no-files"
        else _snapshot_fingerprint(index.fingerprint, index.engine, files)
    )
    return SnapshotRef(
        schema=1,
        kind="code-map",
        ref=f"snapshot:code-map:{fingerprint}",
        fingerprint=fingerprint,
        producer=ProducerRef(name="factory.codeindex", version=1, engine=index.engine),
        inputs=_snapshot_inputs(index),
        generated_at=index.generated_at or _now_str(),
        supersedes=supersedes,
    )


def load_code_map_candidate(
    repo_root: Path, files: Sequence[str] | None = None
) -> SnapshotRef:
    """Load the latest stored index as a metadata-only snapshot candidate."""

    context = code_map_inputs(repo_root, files)
    source_files = _source_files(context)
    latest = load_latest(repo_root)
    if latest is not None:
        return _snapshot_from_index(latest, source_files=source_files)

    if not source_files:
        return _snapshot_from_index(
            CodeIndex(engine=preferred_engine(), generated_at=_now_str(), fingerprint="no-files")
        )

    engine = _engine_for_files(repo_root, source_files)
    return SnapshotRef(
        schema=1,
        kind="code-map",
        ref="snapshot:code-map:missing",
        fingerprint="missing",
        producer=ProducerRef(name="factory.codeindex", version=1, engine=engine),
        inputs=(
            SnapshotInputRef(ref="source-set:missing"),
            SnapshotInputRef(
                ref=f"parser-engine:{engine}",
                content_hash=fingerprint_value("parser-engine", engine).digest,
            ),
        ),
        generated_at=_now_str(),
    )


def resolve_code_map(context: CodeMapInputs, candidate: SnapshotRef) -> SnapshotRef:
    """Resolve through the existing ensure_fresh store and return metadata only."""

    files = None if context.files is None else list(context.files)
    source_files = _source_files(context)
    return _snapshot_from_index(
        ensure_fresh(context.repo_root, files=files),
        supersedes=candidate.ref,
        source_files=source_files,
    )


def register_code_map_adapter(
    fingerprinters: FingerprinterRegistry,
    resolvers: ResolverRegistry,
    repo_root: Path,
    files: Sequence[str] | None = None,
) -> CodeMapInputs:
    """Register the code-map adapter at the factory composition boundary."""

    context = code_map_inputs(repo_root, files)
    fingerprinters.register(CODEMAP_FINGERPRINTER, code_map_fingerprinter)

    def resolver(recipe: FreshnessRecipe, candidate: object) -> SnapshotRef:
        if not isinstance(candidate, SnapshotRef):
            raise TypeError("code-map resolver candidate must be a SnapshotRef")
        return resolve_code_map(context, candidate)

    resolvers.register(CODEMAP_RESOLVER, resolver)
    return context


fingerprint_code_map_inputs = code_map_fingerprinter
load_latest_candidate = load_code_map_candidate
register_code_map = register_code_map_adapter


__all__ = [
    "CODEMAP_FINGERPRINTER",
    "CODEMAP_RESOLVER",
    "CODEMAP_RECIPE",
    "CodeMapInputs",
    "code_map_fingerprinter",
    "code_map_inputs",
    "fingerprint_code_map_inputs",
    "load_code_map_candidate",
    "load_latest_candidate",
    "register_code_map",
    "register_code_map_adapter",
    "resolve_code_map",
]
