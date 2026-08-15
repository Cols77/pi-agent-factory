from __future__ import annotations

import ast
from pathlib import Path

# Signature extraction engine for the durable code index. Tree-sitter is the
# preferred parser (accurate multi-language AST); tree-sitter-languages wheels
# are often ABI-mismatched with the top-level tree-sitter binding, and the
# package is an OPTIONAL accelerator, so anything that fails to import/parse
# degrades to the deterministic stdlib `ast` extractor. `engine` reports which
# path actually ran.

_TS_LANG_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
}


def detect_language(path: Path) -> str | None:
    """Return the language name for a file extension (tree-sitter name for code,
    'python' etc.), else None for non-code files."""
    ext = path.suffix.lower()
    return _TS_LANG_BY_EXT.get(ext)


def _first_line(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().splitlines()
    return first[0].strip() if first else ""


# ---------------------------------------------------------------------------
# stdlib (always available) extractor
# ---------------------------------------------------------------------------
def _stdlib_sigs(source: str, max_sigs: int) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[dict] = []

    def _sig(node: ast.AST) -> str:
        try:
            seg = ast.get_source_segment(source, node) or ""
        except Exception:
            seg = ""
        first = seg.splitlines()
        return first[0] if first else getattr(node, "name", "")

    def _collect(body: list[ast.stmt], class_depth: int) -> None:
        for node in body:
            if len(out) >= max_sigs:
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else (
                    "method" if class_depth > 0 else "function"
                )
                out.append(
                    {
                        "kind": kind,
                        "name": getattr(node, "name", ""),
                        "signature": _sig(node),
                        "line": getattr(node, "lineno", 0),
                        "summary": _first_line(ast.get_docstring(node)),
                    }
                )
                if len(out) >= max_sigs:
                    return
                if isinstance(node, ast.ClassDef):
                    _collect(node.body, class_depth + 1)

    _collect(tree.body, 0)
    return out


# ---------------------------------------------------------------------------
# tree-sitter (optional) extractor
# ---------------------------------------------------------------------------
def _ts_sigs(source: str, language: str, max_sigs: int) -> list[dict]:
    try:
        from tree_sitter_languages import get_parser

        parser = get_parser(language)
    except Exception:
        raise _Unable()
    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        raise _Unable()

    out: list[dict] = []

    def _line(col: int) -> int:
        # tree-sitter point rows are 0-indexed; we report 1-indexed lines.
        return col + 1

    def _walk(node) -> None:
        if len(out) >= max_sigs:
            return
        if node.type in ("function_definition", "class_definition"):
            kind = "class" if node.type == "class_definition" else "function"
            name_node = next(
                (c for c in node.children if c.type in ("identifier", "name")), None
            )
            # Strip the body (the last child) so we render only the signature.
            first_line_st = node.start_point[0]
            end_row = node.end_point[0]
            start = node.start_byte
            segment = source[start : lines_end_byte(source, end_row)]
            sig = segment.splitlines()[0] if segment else (name_node.type if name_node else "")
            out.append(
                {
                    "kind": kind,
                    "name": name_node.text.decode("utf-8", "replace") if name_node else "",
                    "signature": sig,
                    "line": _line(first_line_st),
                    "summary": "",
                }
            )
            if len(out) >= max_sigs:
                return
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return out


class _Unable(Exception):
    pass


def lines_end_byte(source: str, end_row: int) -> int:
    i = 0
    for _ in range(end_row):
        nl = source.find("\n", i)
        if nl == -1:
            return len(source)
        i = nl + 1
    return len(source)


def extract_signatures(
    path: Path, source: str, max_sigs: int = 40, max_chars: int = 200000
) -> tuple[str, list[dict]]:
    """Return (engine, signatures). Prefers tree-sitter; falls back to stdlib.
    `max_chars` guards the tree-sitter parse cost on pathological inputs."""
    language = detect_language(path)
    if language is not None and len(source) <= max_chars:
        try:
            return "tree-sitter", _ts_sigs(source, language, max_sigs)
        except _Unable:
            pass
        except Exception:
            pass
    # Python has a richer stdlib extractor; non-python has none, so empty.
    if path.suffix.lower() in (".py", ".pyi"):
        return "stdlib-ast", _stdlib_sigs(source, max_sigs)
    return "stdlib-ast", []
