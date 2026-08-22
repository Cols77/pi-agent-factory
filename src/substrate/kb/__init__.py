# src/substrate/kb/__init__.py
"""Pure KB reader/index: parse and select frontmatter-based knowledge-base
entries by touched files or canonical failure signatures, and build the
on-disk index summary. No module here determines a gate outcome -- that
stays factory's job."""
from __future__ import annotations

from substrate.kb.index import build_index, build_index_payload
from substrate.kb.retrieval import list_kb_titles, load_entries, select_entries
from substrate.kb.signatures import canonical_failure_signatures

__all__ = [
    "build_index",
    "build_index_payload",
    "canonical_failure_signatures",
    "list_kb_titles",
    "load_entries",
    "select_entries",
]
