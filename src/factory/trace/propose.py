from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import frontmatter

from factory.trace.gaps import Gap
from factory.trace.graph import build_graph
from factory.trace.model import Node

_WORD_RE = re.compile(r"[a-z]{4,}")

_STOPWORDS = frozenset({
    "shall", "must", "with", "when", "that", "this", "then", "from", "into",
    "than", "them", "they", "will", "have", "been", "were", "some", "such",
    "task", "plan", "spec", "should", "which", "while", "after", "before",
})

_EXCERPT_CHARS = 1200
_SUMMARY_CHARS = 400

# Which node kind can close which gap.
_POOL_KIND: dict[str, str] = {
    "task_no_sr": "sr",
    "task_no_plan": "plan",
    "plan_no_spec": "spec",
    "sr_unsatisfied": "task",
}


@dataclass(frozen=True)
class Candidate:
    id: str
    title: str
    summary: str
    shared_terms: list[str]
    score: int


@dataclass(frozen=True)
class PendingGap:
    node_id: str
    kind: str
    detail: str


@dataclass(frozen=True)
class Proposal:
    gap: Gap
    node_title: str
    node_excerpt: str
    pending_total: int
    candidates: list[Candidate]
    pending: list[PendingGap]


class UnknownGapError(ValueError):
    pass


def _terms(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _clip(text: str, limit: int, path: Path) -> str:
    """Clip, and say so.

    A clipped excerpt that looks complete is how a task's dod block silently
    stops being part of the judgement.
    """
    if len(text) <= limit:
        return text
    return (
        f"{text[:limit]}...[truncated at {limit} chars "
        f"-- read {path.as_posix()} for the full text]"
    )


def _summary_of(node: Node) -> str:
    # An SR's statement is the thing a reader actually needs in order to judge a
    # match; for everything else the first prose line is the closest equivalent.
    try:
        post = frontmatter.load(str(node.path))
        statement = post.metadata.get("statement")
        if statement:
            return _clip(str(statement), _SUMMARY_CHARS, node.path)
        body = post.content
    except Exception:
        body = _read(node.path)
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return _clip(stripped, _SUMMARY_CHARS, node.path)
    return node.title


def _candidates_for(gap: Gap, node: Node, nodes: list[Node]) -> list[Candidate]:
    pool_kind = _POOL_KIND.get(gap.kind)
    if pool_kind is None:
        return []
    pool = [n for n in nodes if n.kind == pool_kind and n.id != node.id]

    source_terms = _terms(f"{node.title}\n{_read(node.path)}")
    candidates: list[Candidate] = []
    for other in pool:
        shared = sorted(source_terms & _terms(f"{other.title}\n{_read(other.path)}"))
        candidates.append(
            Candidate(
                id=other.id,
                title=other.title,
                summary=_summary_of(other),
                shared_terms=shared,
                score=len(shared),
            )
        )
    # Ranking only ORDERS the list. It is never truncated: a lexical heuristic must
    # not get to decide which links are reachable, or a correct match phrased in
    # different vocabulary becomes unpickable.
    # Deterministic: score descending, then id ascending. Never a random tiebreak.
    candidates.sort(key=lambda c: (-c.score, c.id))
    return candidates


def next_gap(root: Path, node_id: str | None = None) -> Proposal | None:
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    if not pending:
        return None
    listing = [PendingGap(g.node_id, g.kind, g.detail) for g in pending]

    if node_id is not None:
        chosen = next((g for g in pending if g.node_id == node_id), None)
        if chosen is None:
            raise UnknownGapError(f"no pending gap for {node_id!r}")
        candidates = [chosen]
    else:
        # _KIND_ORDER then node id is a DEFAULT, not a queue. The whole pending
        # set travels with the proposal so a constant never decides what the
        # caller may consider -- the same reason _candidates_for never truncates.
        candidates = pending

    for gap in candidates:
        node = by_id.get(gap.node_id)
        if node is None:
            continue
        return Proposal(
            gap=gap,
            node_title=node.title,
            node_excerpt=_clip(_read(node.path), _EXCERPT_CHARS, node.path),
            pending_total=len(pending),
            candidates=_candidates_for(gap, node, graph.nodes),
            pending=listing,
        )
    return None


def proposal_to_dict(proposal: Proposal) -> dict:
    return {
        "gap": asdict(proposal.gap),
        "node_title": proposal.node_title,
        "node_excerpt": proposal.node_excerpt,
        "pending_total": proposal.pending_total,
        "candidates": [asdict(c) for c in proposal.candidates],
    }
