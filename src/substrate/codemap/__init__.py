"""Durable code map: CodeIndex/IndexFile/IndexSignature, the discover/build/
persist pipeline, and signature extraction (tree-sitter with a stdlib `ast`
fallback), shared across factory capabilities."""
from __future__ import annotations

from substrate.codemap.build import (
    build_index,
    discover_source_files,
    file_signatures,
    fingerprint_for,
    is_fresh,
    render_index_slice,
)
from substrate.codemap.model import CodeIndex, IndexFile, IndexSignature
from substrate.codemap.sigs import detect_language, extract_signatures, preferred_engine
from substrate.codemap.store import ensure_fresh, load_latest, save_index

__all__ = [
    "build_index",
    "discover_source_files",
    "ensure_fresh",
    "file_signatures",
    "fingerprint_for",
    "is_fresh",
    "render_index_slice",
    "load_latest",
    "save_index",
    "CodeIndex",
    "IndexFile",
    "IndexSignature",
    "detect_language",
    "extract_signatures",
    "preferred_engine",
]
