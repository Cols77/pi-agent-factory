"""IDE presentation adapter (spec §22, D2).

Builds a sanitized editor URI (``vscode://file/...?line=N``) for a file path
that resolves inside the repo root. The path-traversal guard lives in
``resolve_repo_file`` — a ``../../…`` style path resolves to ``None`` and is
never turned into a shell/URI call. This adapter only *builds* the link; the
caller's cockpit opener performs the actual open (this file never shells out).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def resolve_repo_file(repo_root: Path, raw: str) -> tuple[Path | None, str | None]:
    """Traversal-guarded absolute path for ``raw`` under ``repo_root``.

    Returns ``(abs_path, None)`` on success and ``(None, reason)`` when the
    path is rejected. Absolute inputs and any relative input whose resolved
    location escapes the repo root are rejected; a path that does not exist is
    rejected as well (nothing to open).
    """
    if not raw or not raw.strip():
        return None, "empty file path"
    path = Path(raw)
    if path.is_absolute():
        return None, "absolute file path is not allowed"
    root = repo_root.resolve()
    try:
        target = (root / path).resolve()
    except (RuntimeError, OSError):
        return None, "invalid file path"
    if target != root and not target.is_relative_to(root):
        return None, "file path escapes repo root (traversal blocked)"
    if not target.is_file():
        return None, f"file not found: {raw}"
    return target, None


def build_ide_uri(abs_path: Path, line: int | None = None) -> str:
    """Build a ``vscode://file/<path>?line=N`` URI for an absolute path.

    ``line`` must be a positive integer when given; anything else is ignored
    (a URI for the file alone is still valid). The result is deterministic and
    requires no subprocess.
    """
    p = str(abs_path).replace("\\", "/")
    uri = f"vscode://file/{quote(p, safe='/:')}"
    if line is not None:
        try:
            lineno = int(line)
        except (TypeError, ValueError):
            lineno = 0
        if lineno > 0:
            uri = f"{uri}?line={lineno}"
    return uri

