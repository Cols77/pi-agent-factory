from __future__ import annotations

import ast
import re
from pathlib import Path

from factory.evidence.registry import Registry
from factory.evidence.types import CheckResult, EvidenceContext

_MD_SUFFIXES = {".md", ".markdown"}


def symbol_in_file(path: Path, symbol: str) -> bool:
    """True if `symbol` is defined in `path`. Python files are parsed with `ast`
    (top-level or nested def/class/assignment names); markdown matches a heading
    whose text contains the symbol; any other file falls back to a word-boundary
    regex search."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return bool(re.search(rf"\b{re.escape(symbol)}\b", text))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                return True
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == symbol:
                return True
        return False
    if suffix in _MD_SUFFIXES:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and symbol in stripped.lstrip("#").strip():
                return True
        return False
    return bool(re.search(rf"\b{re.escape(symbol)}\b", text))


class FilesExist:
    kind = "files_exist"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["paths"], "additionalProperties": False,
        "properties": {"paths": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        missing = [p for p in args["paths"] if not (ctx.repo_root / p).exists()]
        if missing:
            return CheckResult(False, f"missing: {', '.join(missing)}")
        return CheckResult(True, f"all present: {', '.join(args['paths'])}")


class FileContains:
    kind = "file_contains"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["path", "pattern", "mode"], "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
            "mode": {"enum": ["regex", "literal"]},
        },
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        target = ctx.repo_root / args["path"]
        if not target.exists():
            return CheckResult(False, f"file not found: {args['path']}")
        text = target.read_text(encoding="utf-8", errors="replace")
        pattern, mode = args["pattern"], args["mode"]
        found = (pattern in text) if mode == "literal" else bool(re.search(pattern, text))
        if found:
            return CheckResult(True, f"{args['path']} matches {mode} /{pattern}/")
        return CheckResult(False, f"{args['path']} does not match {mode} /{pattern}/")


class SymbolDefined:
    kind = "symbol_defined"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["path", "symbol"], "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "symbol": {"type": "string"}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        target = ctx.repo_root / args["path"]
        if not target.exists():
            return CheckResult(False, f"file not found: {args['path']}")
        if symbol_in_file(target, args["symbol"]):
            return CheckResult(True, f"{args['symbol']} defined in {args['path']}")
        return CheckResult(False, f"{args['symbol']} not defined in {args['path']}")


class AnchorResolves:
    kind = "anchor_resolves"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["ref"], "additionalProperties": False,
        "properties": {"ref": {"type": "string"}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        ref = args["ref"]
        path_part, _, anchor = ref.partition("#")
        target = ctx.repo_root / path_part
        if not target.exists():
            return CheckResult(False, f"file not found: {path_part}")
        if not anchor:
            return CheckResult(True, f"{path_part} exists")
        if symbol_in_file(target, anchor):
            return CheckResult(True, f"{anchor} resolves in {path_part}")
        return CheckResult(False, f"anchor '{anchor}' not found in {path_part}")


DEFAULT_REGISTRY = Registry()
for _connector in (FilesExist(), FileContains(), SymbolDefined(), AnchorResolves()):
    DEFAULT_REGISTRY.register(_connector)
