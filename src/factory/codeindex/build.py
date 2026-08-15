from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from factory.codeindex.model import CodeIndex, IndexFile, IndexSignature
from factory.codeindex.sigs import detect_language, extract_signatures
from factory.freshness.fingerprint import fingerprint_value

# Directory that holds the durable index, relative to repo root. gitignored by
# the factory (runtime artifact, like sessions/).
INDEX_DIR = Path(".factory") / "code-index"
LATEST_STEM = "latest.json"

_CODE_EXTS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".rb", ".php", ".sh",
}

_MAX_FILE_CHARS = int(os.environ.get("FACTORY_INDEX_MAX_FILE_CHARS", "200000"))


def index_dir(repo_root: Path) -> Path:
    return repo_root / INDEX_DIR


def discover_source_files(repo_root: Path, source_dirs: list[str] | None = None) -> list[str]:
    """Code files under the given (or default) source dirs, relative to the root."""
    dirs = source_dirs or ["src"]
    out: list[str] = []
    for d in dirs:
        base = repo_root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in _CODE_EXTS:
                rel = p.relative_to(repo_root).as_posix()
                out.append(rel)
    return out


def fingerprint_for(files: list[str], repo_root: Path) -> str:
    """Hash the CURRENT content of the source set. Reuses the existing fingerprint
    engine (factory.freshness) rather than building a parallel checksum."""
    import hashlib

    digests: dict[str, str] = {}
    for rel in files:
        p = repo_root / rel
        try:
            digests[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            digests[rel] = "missing"
    # fingerprint_value json-serializes + sha256s with stable ordering.
    return fingerprint_value("code-index", digests).digest


def _parse_one(repo_root: Path, rel: str) -> IndexFile | None:
    path = repo_root / rel
    try:
        if path.stat().st_size > _MAX_FILE_CHARS:
            return None
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not source.strip():
        return IndexFile(language=detect_language(path) or "", module_doc="")
    engine, sigs = extract_signatures(path, source)
    module_doc = ""
    if engine == "stdlib-ast":
        import ast

        try:
            doc = ast.get_docstring(ast.parse(source))
            module_doc = doc.strip().splitlines()[0] if doc else ""
        except SyntaxError:
            module_doc = ""
    return IndexFile(
        language=detect_language(path) or "",
        module_doc=module_doc,
        signatures=[IndexSignature(**s) for s in sigs],
    )


def build_index(repo_root: Path, files: list[str] | None = None, engine_note: str = "") -> CodeIndex:
    files = files or discover_source_files(repo_root)
    entries: dict[str, IndexFile] = {}
    for rel in files:
        f = _parse_one(repo_root, rel)
        if f is not None:
            entries[rel] = f
    # Determine engine by re-parsing one file if needed (kept simple: report the
    # engine the extractor picked on the first file).
    engine = "stdlib-ast"
    if files:
        try:
            source = (repo_root / files[0]).read_text(encoding="utf-8", errors="replace")
            engine, _ = extract_signatures(Path(files[0]), source)
        except OSError:
            engine = "stdlib-ast"
    if engine_note:
        engine = engine_note
    return CodeIndex(
        engine=engine,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fingerprint=fingerprint_for(files, repo_root),
        files=entries,
    )


def is_fresh(index: CodeIndex, repo_root: Path) -> bool:
    """True iff the index's fingerprint still matches current source content.
    Callers never trust a stale index; they fall back to stdlib extraction."""
    files = sorted(index.files.keys())
    return bool(files) and index.fingerprint == fingerprint_for(files, repo_root)


def file_signatures(index: CodeIndex, rel: str) -> list[dict] | None:
    f = index.files.get(rel)
    if f is None:
        return None
    return [
        {"kind": s.kind, "name": s.name, "signature": s.signature, "line": s.line, "summary": s.summary}
        for s in f.signatures
    ]


def render_index_slice(
    index: CodeIndex, paths: list[str], cap: int = int(os.environ.get("FACTORY_INDEX_SLICE_CAP", "24000"))
) -> str:
    lines: list[str] = []
    used = 0

    def push(s: str) -> None:
        nonlocal used
        if used >= cap:
            return
        lines.append(s)
        used += len(s)

    for rel in paths:
        if used >= cap:
            break
        f = index.files.get(rel)
        if f is None:
            continue
        push(f"### REFERENCE (indexed) — {rel}")
        if f.signatures:
            for s in f.signatures:
                if used >= cap:
                    break
                push(f"- L{s.line} {s.signature}{(' — ' + s.summary) if s.summary else ''}")
        else:
            push("_(no extractable signatures)_")
        push("")
    return "\n".join(lines)
