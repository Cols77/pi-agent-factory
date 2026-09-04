from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from substrate.codemap.model import CodeIndex, IndexFile, IndexSignature
from substrate.codemap.sigs import detect_language, extract_signatures
from substrate.freshness.fingerprint import fingerprint_value

# Directory that holds the durable index, relative to repo root. gitignored by
# the factory (runtime artifact, like sessions/).
INDEX_DIR = Path(".factory") / "code-index"
LATEST_STEM = "latest.json"

_CODE_EXTS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".rb", ".php", ".sh",
}

# Directory names that are never project code, even when a source_dir (like
# `pi-ext` or `scripts`) contains them -- vendored/built deps, not the agent's
# deliverable. Skipping these keeps discovery (and /factory-init) fast and
# keeps the injected slice free of third-party noise.
_SKIP_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".factory",
}
_MAX_FILE_CHARS = int(os.environ.get("FACTORY_INDEX_MAX_FILE_CHARS", "200000"))


def index_dir(repo_root: Path) -> Path:
    return repo_root / INDEX_DIR


def discover_source_files(repo_root: Path, source_dirs: list[str] | None = None) -> list[str]:
    """Code files under the given (or default) source dirs, relative to the root.

    `source_dirs` wins when passed; otherwise the factory's own
    `.pi/factory/project-profile.json` (written by /factory-init) supplies the
    discovery set, so a factory-init'd project is indexed over its real source
    tree (src + pi-ext + scripts + ...) instead of a hard-coded `["src"]`.
    Falls back to `["src"]` when no profile exists."""
    dirs = source_dirs or _profile_source_dirs(repo_root) or ["src"]
    out: list[str] = []
    for d in dirs:
        base = repo_root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir():
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            if p.is_file() and p.suffix.lower() in _CODE_EXTS:
                rel = p.relative_to(repo_root).as_posix()
                out.append(rel)
    return out


def is_source_path(
    repo_root: Path, rel_path: str, *, source_dirs: list[str] | None = None,
) -> bool:
    """True when `rel_path` (a repository-relative path, native or POSIX
    separators) is real production/validation source code by this repo's own
    code-map convention: inside a configured source directory
    (`profile_source_dirs`, falling back to `["src"]` exactly like
    `discover_source_files`), not inside a `_SKIP_DIRS` segment
    (vendored/build output), with a `_CODE_EXTS` extension.

    A pure path classifier -- unlike `discover_source_files`, it never
    touches the filesystem and does not require the file to currently exist,
    so it also correctly classifies a path a git diff reports as deleted.
    SR-050 T3's relation-maintenance obligation is the first caller; treat
    this as the one shared classifier for "is this changed path real
    project code" rather than adding a second one.
    """
    candidate = PurePosixPath(rel_path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if any(part in _SKIP_DIRS for part in candidate.parts):
        return False
    if candidate.suffix.lower() not in _CODE_EXTS:
        return False
    dirs = source_dirs or _profile_source_dirs(repo_root) or ["src"]
    return any(
        candidate == PurePosixPath(d) or PurePosixPath(d) in candidate.parents
        for d in dirs
    )


def profile_source_dirs(repo_root: Path) -> list[str] | None:
    """Read the factory project-profile's source_dirs (if any). None when absent."""
    profile = repo_root / ".pi" / "factory" / "project-profile.json"
    try:
        import json

        data = json.loads(profile.read_text(encoding="utf-8"))
        dirs = data.get("source_dirs")
        if isinstance(dirs, list):
            return [str(d) for d in dirs]
    except OSError:
        pass
    except Exception:
        pass
    return None


def _profile_source_dirs(repo_root: Path) -> list[str] | None:
    return profile_source_dirs(repo_root)


def fingerprint_for(files: list[str], repo_root: Path) -> str:
    """Hash the CURRENT content of the source set. Reuses the existing fingerprint
    engine (substrate.freshness) rather than building a parallel checksum."""
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
