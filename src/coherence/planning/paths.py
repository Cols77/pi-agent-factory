from __future__ import annotations

import os
from pathlib import Path

_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    except FileNotFoundError:
        return False
    except (OSError, RuntimeError, ValueError):
        return True
    return False


def has_reparse_component(root: Path, path: Path) -> bool:
    """Return whether a lexical path component is a link/reparse point.

    The check is deliberately lexical and happens before ``Path.resolve()`` so
    an in-project alias cannot hide a symlink or junction behind a canonical
    path.  The project root itself is included in the check because callers
    may pass a stored run directory as the root argument.
    """
    try:
        lexical_root = root.absolute()
        lexical_path = path.absolute()
        lexical_path.relative_to(lexical_root)
        anchor = Path(lexical_path.anchor)
        relative_parts = lexical_path.relative_to(anchor).parts
    except (OSError, RuntimeError, ValueError):
        return True

    current = anchor
    for part in relative_parts:
        current /= part
        try:
            if _is_reparse_point(current):
                return True
            if current.exists() and current.resolve() != current.absolute():
                return True
        except (OSError, RuntimeError, ValueError):
            return True
    return False


def safe_resolve(root: Path, path: Path) -> Path | None:
    """Resolve a path only when no lexical component is a link/reparse point."""
    if has_reparse_component(root, path):
        return None
    try:
        resolved_root = root.absolute().resolve()
        resolved = path.absolute().resolve()
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def safe_root(path: Path) -> Path | None:
    """Return a canonical project root only when its lexical path is safe."""
    return safe_resolve(path, path)


__all__ = ["has_reparse_component", "safe_resolve", "safe_root"]
