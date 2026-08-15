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
# Per-language grammar packages that the tree-sitter org ships in lockstep with
# the top-level binding (so they are ABI-matched to it). `tree_sitter_languages`
# is a monolithic bundle locked to a specific tree-sitter ABI, so its wheels are
# frequently incompatible with whatever top-level `tree-sitter` is installed --
# prefer the per-language packages and fall back to the bundle only if present.
# Either way a failure degrades to `_Unable` (the caller falls back to stdlib).

_TS_PER_LANG = {
    "python": ("tree_sitter_python", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "javascript": ("tree_sitter_javascript", "language"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "java": ("tree_sitter_java", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "php": ("tree_sitter_php", "language"),
    "bash": ("tree_sitter_bash", "language"),
}


def _make_parser(language):
    """Wrap a Language in a Parser across the 0.25/0.26+ API split."""
    from tree_sitter import Parser

    try:
        return Parser(language)  # API <=0.25: Parser(language)
    except (TypeError, Exception):
        parser = Parser()  # API >=0.26: assign .language afterwards
        parser.language = language
        return parser


def _get_parser(language: str):
    """Return a tree-sitter Parser for the language, or raise _Unable."""
    from tree_sitter import Language

    mod_fn = _TS_PER_LANG.get(language)
    if mod_fn:
        mod_name, fn_name = mod_fn
        try:
            module = __import__(mod_name, fromlist=[fn_name])
            return _make_parser(Language(getattr(module, fn_name)()))
        except Exception:
            pass  # per-language pkg absent or ABI-incompatible: try the bundle
    try:
        from tree_sitter_languages import get_parser

        return get_parser(language)
    except Exception:
        raise _Unable()


def _ts_sigs(source: str, language: str, max_sigs: int) -> list[dict]:
    try:
        parser = _get_parser(language)
    except Exception:
        raise _Unable()
    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        raise _Unable()

    # Node types that hold a declaration name (the tree-sitter org keeps these
    # stable-ish per language; the {identifier,type_identifier,property_identifier}
    # name set covers python + the TS/JS family, go, rust, java, c/cpp, etc.).
    _FUNC_TYPES = {
        "function_definition",  # python
        "function_declaration",  # ts/js, go happens to share the name
        "generator_function_declaration",  # ts/js
        "method_definition",  # ts/js class body
        "method_declaration",  # go
        "func_declaration",  # go (top-level thu ts)
        "function_item",  # rust
    }
    _CLASS_TYPES = {
        "class_definition",  # python
        "class_declaration",  # ts/js
        "class_specifier",  # c/cpp (class Foo { ... })
        "interface_declaration",  # ts
        "type_declaration",  # go/ts
        "struct_item",  # rust
        "struct_specifier",  # c/cpp (struct X { ... })
        "trait_item",  # rust
    }
    _NAME_TYPES = {"identifier", "type_identifier", "property_identifier", "name"}

    out: list[dict] = []

    def _line(col: int) -> int:
        # tree-sitter point rows are 0-indexed; we report 1-indexed lines.
        return col + 1

    def _name_of(node) -> str:
        """Find the declaration name. C/C++ nest it one level down inside a
        `function_declarator`/`pointer_declarator`, so descend through
        declarator wrappers when the direct children carry no name."""
        for c in node.children:
            if c.is_named and c.type in _NAME_TYPES and c.text:
                return c.text.decode("utf-8", "replace")
        for c in node.children:
            if c.is_named and c.type in ("function_declarator", "pointer_declarator", "declarator"):
                name = _name_of(c)
                if name:
                    return name
        return ""

    def _walk(node, class_depth: int) -> None:
        if len(out) >= max_sigs:
            return
        if node.type in _FUNC_TYPES or node.type in _CLASS_TYPES:
            is_class = node.type in _CLASS_TYPES
            kind = "class" if is_class else ("method" if class_depth > 0 else "function")
            name = _name_of(node)
            end_row = node.end_point[0]
            start = node.start_byte
            segment = source[start : lines_end_byte(source, end_row)]
            sig = segment.splitlines()[0] if segment else name
            # Skip keyword-only / anonymous nodes (e.g. no name) to stay in shape
            # with the stdlib extractor's named declarations.
            if name:
                out.append(
                    {
                        "kind": kind,
                        "name": name,
                        "signature": sig,
                        "line": _line(node.start_point[0]),
                        "summary": "",
                    }
                )
            child_depth = class_depth + (1 if is_class else 0)
            for child in node.children:
                _walk(child, child_depth)
            if len(out) >= max_sigs:
                return
        else:
            for child in node.children:
                _walk(child, class_depth)

    _walk(tree.root_node, 0)
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
