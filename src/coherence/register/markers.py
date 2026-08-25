from __future__ import annotations

import ast
from pathlib import Path

# Collect ``@pytest.mark.sr("SR-0001")`` marker ids from a Python source file
# WITHOUT importing or executing it. Static, AST-based collection means a test
# module's runtime side effects (network, fixtures, slow imports) never run when
# we merely need to know which SR ids it claims to target.


def _decorator_dotted(dec: ast.AST) -> str | None:
    """Return the dotted attribute name of a decorator (e.g. ``pytest.mark.sr``).

    Handles both the bare form (``@pytest.mark.sr``) and the call form used to
    pass the marker id (``@pytest.mark.sr("SR-0001")``).
    """
    node = dec.func if isinstance(dec, ast.Call) else dec
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts)) if parts else None


class MarkerCollectionError(RuntimeError):
    """Raised when a resolved test file cannot be read or parsed as Python.

    Distinct from ``SyntaxError``/``OSError`` themselves so callers can tell a
    file that failed static inspection apart from a file that genuinely lacks
    the marker. Carries the underlying failure in the message.
    """


def collect_markers(path: Path) -> set[str]:
    """Collect the exact sr marker id strings declared across a test module.

    Returns a deduplicated set: multiple distinct markers on one function and
    duplicate marker text across functions both collapse to a single entry per
    id. Marker text is matched exactly as written -- no case folding or
    normalisation -- so ``SR-0001`` and ``sr-0001`` stay distinct, mirroring the
    requirement-side id comparison.

    Only ``@...mark.sr(...)`` decorators are considered; unrelated decorators
    (``skip``, ``parametrize``, a different ``.sr`` symbol) are ignored.

    Raises :class:`MarkerCollectionError` - never the raw IO/parse exception -
    when the file cannot be read (non-UTF8, permission/IO error -- the latter
    subsumes ``PermissionError``) or parsed (malformed Python). Callers that
    cannot tolerate an unreadable fixture must catch it.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, PermissionError) as exc:
        raise MarkerCollectionError(f"cannot read or parse {path}: {exc}") from exc
    markers: set[str] = set()
    for node in ast.walk(tree):
        decorators = getattr(node, "decorator_list", None)
        if not decorators:
            continue
        for decorator in decorators:
            dotted = _decorator_dotted(decorator)
            if dotted is None or (dotted != "mark.sr" and not dotted.endswith(".mark.sr")):
                continue
            for arg in getattr(decorator, "args", []):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    markers.add(arg.value)
    return markers


__all__ = ["MarkerCollectionError", "collect_markers"]