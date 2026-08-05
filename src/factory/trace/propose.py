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
class Proposal:
    gap: Gap
    node_title: str
    node_excerpt: str
    pending_total: int
    candidates: list[Candidate]


def _terms(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _summary_of(node: Node) -> str:
    # An SR's statement is the thing a reader actually needs in order to judge a
    # match; for everything else the first prose line is the closest equivalent.
    try:
        post = frontmatter.load(str(node.path))
        statement = post.metadata.get("statement")
        if statement:
            return str(statement)[:_SUMMARY_CHARS]
        body = post.content
    except Exception:
        body = _read(node.path)
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:_SUMMARY_CHARS]
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


def next_gap(root: Path) -> Proposal | None:
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    for gap in pending:
        node = by_id.get(gap.node_id)
        if node is None:
            continue
        return Proposal(
            gap=gap,
            node_title=node.title,
            node_excerpt=_read(node.path)[:_EXCERPT_CHARS],
            pending_total=len(pending),
            candidates=_candidates_for(gap, node, graph.nodes),
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
