# src/factory/kb/retrieval.py
from __future__ import annotations

import warnings

from substrate.kb.retrieval import list_kb_titles, load_entries, select_entries

warnings.warn(
    "factory.kb.retrieval is deprecated; import substrate.kb.retrieval",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["list_kb_titles", "load_entries", "select_entries"]
