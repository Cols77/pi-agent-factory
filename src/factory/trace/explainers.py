from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter

from factory.freshness.fingerprint import fingerprint_value

EXPLAINER_RELDIR = ("docs", "visual-explain")


@dataclass(frozen=True)
class Explainer:
    id: str  # path.name of the .md, e.g. "drone-architecture.md"
    path: Path
    title: str
    explains: list[str]  # SR ids this explainer depicts (declared)
    fingerprints: dict[str, str]  # sr_id -> recorded content digest


def load_explainers(root: Path) -> list[Explainer]:
    """Load `docs/visual-explain/*.md` explainers from declared frontmatter.

    A malformed file degrades to being skipped rather than crashing the graph,
    matching the trace model's contract. `explains` and `dep_fingerprint` are
    the only fields consumed; anything else is left to the renderer/Obsidian.
    """
    directory = root.joinpath(*EXPLAINER_RELDIR)
    if not directory.is_dir():
        return []
    out: list[Explainer] = []
    for path in sorted(directory.glob("*.md")):
        try:
            post = frontmatter.load(str(path))
        except Exception:
            continue
        meta = post.metadata or {}
        explains_raw = meta.get("explains")
        if isinstance(explains_raw, str):
            explains = [explains_raw]
        elif isinstance(explains_raw, list):
            explains = [str(x) for x in explains_raw if x is not None]
        else:
            explains = []
        fp_raw = meta.get("dep_fingerprint")
        fingerprints: dict[str, str] = {}
        if isinstance(fp_raw, dict):
            fingerprints = {str(k): v for k, v in fp_raw.items() if isinstance(v, str)}
        out.append(
            Explainer(
                id=path.name,
                path=path,
                title=str(meta.get("title", path.stem)),
                explains=[s for s in explains if s],
                fingerprints=fingerprints,
            )
        )
    return out


def _sr_content_digest(root: Path, sr_id: str) -> str | None:
    """Deterministic digest of the current content of a declared SR, or None."""
    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return None
    for path in sorted(req_dir.glob("SR-*.md")):
        try:
            post = frontmatter.load(str(path))
            if str(post.metadata.get("id")) == sr_id:
                return fingerprint_value(sr_id, path.read_text(encoding="utf-8")).digest
        except Exception:
            continue
    return None


def list_fresh_explainers(root: Path, sr_ids: list[str]) -> list[Explainer]:
    """Explainers reusable for the given SRs: relevant AND fully up-to-date.

    An explainer is considered fresh only when:
      - it declares `explains:` overlapping `sr_ids`, and
      - EVERY target in its `explains:` has a recorded `dep_fingerprint` that
        matches the target SR's current content.

    An explainer with no `explains:` or missing/divergent fingerprints is NOT
    fresh (the grill then falls back to generating one). Freshness is derived
    from the fingerprint engine (`factory.freshness`), never guessed.
    """
    wanted = set(sr_ids)
    fresh: list[Explainer] = []
    for exp in load_explainers(root):
        if not exp.explains or not (set(exp.explains) & wanted):
            continue
        up_to_date = True
        for sr_id in exp.explains:
            recorded = exp.fingerprints.get(sr_id)
            current = _sr_content_digest(root, sr_id)
            if recorded is None or current is None or recorded != current:
                up_to_date = False
                break
        if up_to_date:
            fresh.append(exp)
    return fresh
