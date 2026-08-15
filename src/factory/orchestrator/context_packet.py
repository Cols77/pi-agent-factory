from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from factory.orchestrator.deliverables import parse_deliverables

if TYPE_CHECKING:
    from factory.codeindex.model import CodeIndex
    from factory.orchestrator.ledger import Task

try:
    from factory.codeindex import file_signatures as _idx_file_signatures
    from factory.codeindex import is_fresh as _idx_is_fresh
    from factory.codeindex import load_latest as _idx_load_latest

    _HAS_INDEX = True
except Exception:  # pragma: no cover - defensive; codeindex should import
    _idx_file_signatures = None
    _idx_is_fresh = None
    _idx_load_latest = None
    _HAS_INDEX = False


def _reference_signatures(
    rel: Path, repo_root: Path, max_sigs: int, index: "CodeIndex | None" = None
) -> list[dict]:
    """Use the durable code index for reference-file signatures when a fresh index
    exists; otherwise fall back to the stdlib extractor. A stale index is never
    trusted (is_fresh is recomputed once per packet build, not per file)."""
    if index is not None and _idx_file_signatures is not None:
        try:
            sigs = _idx_file_signatures(index, rel.as_posix())
            if sigs is not None:
                return sigs[:max_sigs]
        except Exception:
            pass
    return signature_summary_for_file(rel, repo_root, max_sigs)


def _resolve_index(repo_root: Path) -> "CodeIndex | None":
    """Load the durable code index once, only when it is fresh (cheap checksum)."""
    if not _HAS_INDEX or _idx_load_latest is None or _idx_is_fresh is None:
        return None
    try:
        index = _idx_load_latest(repo_root)
        if index is not None and _idx_is_fresh(index, repo_root):
            return index
    except Exception:
        pass
    return None

# Env-tunable token-budget caps (mirroring the FACTORY_*_TIMEOUT_S contract).
_PRIMARY_CAP = int(os.environ.get("FACTORY_PACKET_PRIMARY_CAP_CHARS", "12000"))
_REF_MAX_SIGS = int(os.environ.get("FACTORY_PACKET_REF_MAX_SIGS", "40"))
_TOTAL_CAP = int(os.environ.get("FACTORY_PACKET_TOTAL_CAP_CHARS", "60000"))

# Code file extensions we extract signatures for; everything else is either a
# head-slice (text) or left as a pointer (the reference-file budget keeps this
# bounded, and binary/non-text files fall through to "skipped").
_CODE_EXTS = {".py", ".pyi"}
_TEXT_EXTS = {".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".html", ".css"}


@dataclass
class Signature:
    kind: str  # function | class | method
    name: str
    signature: str
    line: int
    summary: str = ""


def _first_line_summary(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().splitlines()
    return first[0].strip() if first else ""


def signature_summary_for_file(
    path: Path, repo_root: Path, max_sigs: int = _REF_MAX_SIGS
) -> list[dict]:
    """Deterministic, stdlib-only signature extraction (function/class/method with
    line numbers + a one-line purpose from the first docstring line). Used for
    reference files; a later tree-sitter index (item 2) can back this via the same
    output shape."""
    try:
        source = (repo_root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
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
                if isinstance(node, ast.ClassDef):
                    kind = "class"
                else:
                    kind = "method" if class_depth > 0 else "function"
                out.append(
                    {
                        "kind": kind,
                        "name": getattr(node, "name", ""),
                        "signature": _sig(node),
                        "line": getattr(node, "lineno", 0),
                        "summary": _first_line_summary(ast.get_docstring(node)),
                    }
                )
                if len(out) >= max_sigs:
                    return
                if isinstance(node, ast.ClassDef):
                    _collect(node.body, class_depth + 1)

    _collect(tree.body, 0)
    return out


def _file_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in _CODE_EXTS:
        return "code"
    if suffix in _TEXT_EXTS:
        return "text"
    return "other"


def primary_paths(task: "Task", manifest: dict) -> set[str]:
    """Modify/Create deliverables (from the task body) that are also present in the
    manifest's source_files — the files the agent must read in full."""
    deliverable = [p for p in parse_deliverables(task.body) if p]
    source = manifest.get("context", {}).get("source_files", [])
    if not isinstance(source, list):
        source = []
    deliverable_set = {str(p) for p in deliverable}
    source_set = {str(p) for p in source}
    return deliverable_set & source_set


def build_context_packet(task: "Task", manifest: dict, repo_root: Path) -> dict:
    source = manifest.get("context", {}).get("source_files", [])
    if not isinstance(source, list):
        source = []
    primary = primary_paths(task, manifest)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index = _resolve_index(repo_root)

    files: dict[str, dict] = {}
    missing: list[str] = []
    truncated = False
    skipped_by_cap: list[str] = []
    total = 0

    for raw in source:
        rel = str(raw)
        if total >= _TOTAL_CAP:
            skipped_by_cap.append(rel)
            truncated = True
            continue
        path = repo_root / rel
        if not path.exists() or path.is_dir():
            missing.append(rel)
            continue

        is_primary = rel in primary
        try:
            size = path.stat().st_size
        except OSError:
            missing.append(rel)
            continue

        if size > _PRIMARY_CAP and is_primary:
            # Over-cap primary -> degrade to signatures, not truncated junk.
            sigs = _reference_signatures(Path(rel), repo_root, _REF_MAX_SIGS, index)
            entry = {
                "primary": True,
                "kind": "signatures",
                "content": None,
                "signatures": sigs,
                "reason": "over-cap primary file",
            }
        elif _file_kind(rel) == "code":
            sigs = _reference_signatures(Path(rel), repo_root, _REF_MAX_SIGS, index)
            if is_primary:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    # Bound a pathological primary even when under cap (safety).
                    content = content[:_PRIMARY_CAP]
                    entry = {
                        "primary": True,
                        "kind": "content",
                        "content": content,
                        "signatures": [],
                        "reason": None,
                    }
                except OSError:
                    missing.append(rel)
                    continue
            else:
                entry = {
                    "primary": False,
                    "kind": "signatures",
                    "content": None,
                    "signatures": sigs,
                    "reason": None,
                }
        elif _file_kind(rel) == "text":
            if is_primary:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")[:_PRIMARY_CAP]
                    entry = {
                        "primary": True,
                        "kind": "content",
                        "content": content,
                        "signatures": [],
                        "reason": None,
                    }
                except OSError:
                    missing.append(rel)
                    continue
            else:
                entry = {
                    "primary": False,
                    "kind": "skipped",
                    "content": None,
                    "signatures": [],
                    "reason": "reference text file left as a pointer",
                }
        else:
            entry = {
                "primary": is_primary,
                "kind": "skipped",
                "content": None,
                "signatures": [],
                "reason": "non-code/non-text file left as a pointer",
            }

        files[rel] = entry
        if entry["content"]:
            total += len(entry["content"])

    return {
        "schema": 1,
        "task_id": task.id,
        "generated_at": now,
        "primary_files": [p for p in source if p in primary],
        "reference_files": [p for p in source if p not in primary],
        "files": files,
        "missing": missing,
        "skipped_by_cap": skipped_by_cap,
        "truncated": truncated,
    }


def _render_entry(rel: str, entry: dict) -> list[str]:
    lines: list[str] = []
    tag = "PRIMARY" if entry.get("primary") else "REFERENCE"
    lines.append(f"### {tag} — {rel}")
    kind = entry.get("kind")
    if kind == "content":
        lines.append("```")
        body = (entry.get("content") or "").rstrip("\n")
        lines.append(body)
        lines.append("```")
    elif kind == "signatures":
        sigs = entry.get("signatures") or []
        if not sigs:
            lines.append("_(no extractable signatures)_")
        for s in sigs:
            note = f" — {s['summary']}" if s.get("summary") else ""
            lines.append(f"- L{s.get('line')} {s.get('signature')}{note}")
    else:
        reason = entry.get("reason") or "skipped"
        lines.append(f"_(skipped: {reason})_")
    return lines


def render_packet(packet: dict) -> str:
    """Deterministic markdown block for prompt embedding. Always closed fences."""
    files = packet.get("files", {})
    lines: list[str] = []
    lines.append("## Context packet (materialized by your context gatherer)")
    for rel in packet.get("reference_files", []):
        if rel in files:
            lines.extend(_render_entry(rel, files[rel]))
            lines.append("")
    for rel in packet.get("primary_files", []):
        if rel in files:
            lines.extend(_render_entry(rel, files[rel]))
            lines.append("")
    if packet.get("missing"):
        lines.append(f"_Note: {len(packet['missing'])} referenced file(s) missing on disk._")
    if packet.get("truncated"):
        lines.append("_Note: packet truncated to the total token budget._")
    return "\n".join(lines).strip() + "\n"


def write_context_packet(packet: dict, transcript_dir: Path) -> Path:
    """Atomically persist the packet next to review-guide.json / validation-report.json."""
    import json

    transcript_dir.mkdir(parents=True, exist_ok=True)
    target = transcript_dir / "context-packet.json"
    tmp = target.with_name(".context-packet.json.tmp")
    tmp.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target


def read_context_packet(transcript_dir: Path) -> dict | None:
    import json

    target = transcript_dir / "context-packet.json"
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
