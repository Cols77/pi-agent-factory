"""SR-058/AC-1 + AC-2: cross-FEAT/SR semantic overlap detection at scale.

Scope, v1 (deliberate, see requirements/SR-058.md's body addendum): this
detects plausible OVERLAP/near-duplicate requirements only -- it never tries
to distinguish "these two requirements conflict" from "these two requirements
overlap". A candidate pair either looks like a plausible overlap or it
doesn't; telling those two apart is explicitly out of scope here.

AC-1 -- narrowing without O(N^2) pair-level judgement
======================================================
The similarity mechanism below is a deliberately simple v1 choice: a
TF-IDF-style bag-of-words cosine similarity over each requirement's
``statement`` + acceptance-criteria text, implemented in pure Python with no
new dependency (no ``sentence-transformers``/``torch``, no network/API
embedding calls -- see ``pyproject.toml``, which has neither before or after
this module). This is explicitly NOT real embeddings. If recall proves
insufficient at real corpus scale, upgrading to real embeddings or a
RAG-style retrieval approach is flagged, explicit, FUTURE work -- this module
is not meant to be the final answer, only an honest, cheap first cut.

Per-SR term-frequency vectors are cached (`SrVector`, keyed by
`content_fingerprint` -- a hash of the exact text the vector was built from)
so a re-run only re-tokenizes SRs whose statement/acceptance text actually
changed, mirroring `substrate.freshness`'s "recompute only what changed"
philosophy (see `substrate/freshness/fingerprint.py`). What is NOT cached is
IDF/cosine weighting: those depend on the whole corpus's current membership,
are cheap (an O(N) pass over already-tokenized vectors, no re-tokenization),
and must reflect whichever SRs are in scope for *this* run -- caching them
would silently stale the moment any other SR in the corpus changed.

AC-1's own literal claim is about the shape of what a narrowing step hands to
any *pair-level judgement* (model or human): `generate_candidates` computes
a bounded, `k`-per-SR nearest-neighbour set (`k` defaults to 10) and NEVER
returns the full O(N^2) pairwise matrix -- candidate count grows with
`O(N*k)`, not `O(N^2)`. The pairwise cosine comparisons this narrowing step
performs internally to find each SR's neighbours are themselves cheap
(no model call, no I/O) and, per this SR's source seed doc
(docs/superpowers/specs/2026-09-03-cross-feat-semantic-overlap-detection-seed.md),
comfortably an in-memory, millisecond-scale operation at the "hundreds to low
thousands of SRs" scale this system targets -- no specialised vector
database or ANN index is needed at this scale, and this module makes no
claim about the narrowing step's own internal complexity, only about what it
hands onward.

Layer-1 intersection: `generate_candidates` also drops any candidate pair
that carries a DECLARED relation from either SR's `upstream` or
`relates_to`, in either direction (SR-057's two "declared relation" fields).
A pair that is similar AND declared is expected and fine -- not a candidate.
A pair that is dissimilar and undeclared is just two unrelated SRs -- also
not a candidate. Only the intersection (similar AND undeclared) survives to
AC-2's model verification.

AC-2 -- model verification + human decision capture
=====================================================
`verify_candidates` hands each surviving candidate to an injected `judge`
callable (dependency injection, same shape as
`coherence.register.fidelity.review_fidelity`'s `judge` parameter) for
adversarial judgement. A judge that raises, or returns a malformed shape,
NEVER silently reads as "no overlap" -- it produces an explicit
`status="unavailable"` result, distinct from `"dismissed"` (the judge ran and
said this isn't a real overlap) and from `"confirmed"` (the judge ran and
says it is). Only `"confirmed"` candidates ever become a gate item a human
must resolve; `"dismissed"` candidates never reach a human, and
`"unavailable"` ones are reported as exactly that -- "wasn't actually
checked" -- never conflated with either.

A human's resolution of a confirmed candidate is captured through the
EXISTING `coherence.gate` `DecisionFile` mechanism (SR-050/AC-3's
`human_review` pattern) -- see `gate_item_id`/`gate_id_for_run` below and
`run_overlap_check`'s use of `coherence.gate.service.resolve_gate`. This
module never auto-declares a relation, never auto-merges requirements, and
never invents a second, parallel consent mechanism: `accept`'s `reason` is
where a human records the relation they judge the pair needs (per SR-058's
own criterion text, "confirming ... the relation it needs" is information
CAPTURED by the decision, never auto-written into either SR's frontmatter).

Layering: this file lives under `src/coherence/register/`, which
deliberately imports NOTHING from `factory.*`
(`tests/unit/requirements/test_coherence_parity.py` enforces this). The real,
`PiAgentBackend`-dispatch judge lives at
`coherence.audit.overlap_dispatch.default_judge` instead, exactly mirroring
how SR-050/T5's fidelity judge is split across
`coherence.register.fidelity`/`coherence.audit.fidelity_dispatch` for the
identical reason -- see that module pair's own docstrings.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from coherence.gate.model import CorruptDecisionFile, DecisionFile
from coherence.gate.service import resolve_gate
from coherence.gate.store import decision_path, load_decision
from coherence.register.register import Requirement, load_register

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A short, generic English stopword list -- not a language-detection or NLP
# concern, just enough to keep near-universal filler words (which would
# otherwise dominate every SR's vector and swamp the real signal) out of the
# term-frequency counts. Deliberately small and hand-picked, not an imported
# corpus -- consistent with the "no new dependency" scoping call above.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is",
        "are", "shall", "with", "that", "this", "as", "by", "be", "when",
        "it", "its", "from", "system", "requirement", "not", "no", "any",
        "all", "each", "which", "at", "if", "then", "than", "such", "into",
        "will", "may", "must", "can", "these", "those", "other", "one",
        "via", "per",
    }
)

DEFAULT_K = 10

_VECTOR_CACHE_DIR = (".factory", "overlap-index")


# ---------------------------------------------------------------------------
# AC-1: lexical representation + narrowing
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2]


def _requirement_text(req: Requirement) -> str:
    parts = [req.statement]
    parts.extend(ac.criterion for ac in req.acceptance)
    return "\n".join(parts)


def content_fingerprint(req: Requirement) -> str:
    """A hash of exactly the text `_tokenize`/vectorization reads (statement
    + every acceptance criterion's text) -- the cache key `SrVector` is
    stored under. Changing anything else about the SR (title, domain,
    upstream, body prose, verification refs) never invalidates the cache;
    only a change to the text this module actually vectorizes does."""
    digest = hashlib.sha256(_requirement_text(req).strip().encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class SrVector:
    """One SR's cached term-frequency representation.

    ``term_counts`` is a raw token->count map over the tokenized statement +
    acceptance text; ``length`` is the total token count (for TF
    normalization). Neither IDF nor cosine weighting is baked in here -- see
    the module docstring for why those are recomputed fresh each run instead
    of cached.
    """

    sr_id: str
    fingerprint: str
    term_counts: dict[str, int]
    length: int


def compute_vectors(
    reqs: list[Requirement], cache: dict[str, SrVector] | None = None
) -> dict[str, SrVector]:
    """Build every requirement's `SrVector`, reusing a cached vector whose
    `fingerprint` still matches -- the "recompute only what changed" step.
    An SR present in `cache` but no longer in `reqs` is simply dropped from
    the result (this function returns a `{sr_id: SrVector}` map scoped to
    exactly the given `reqs`, not a superset accumulated across runs)."""
    cache = cache or {}
    result: dict[str, SrVector] = {}
    for req in reqs:
        fp = content_fingerprint(req)
        cached = cache.get(req.id)
        if cached is not None and cached.fingerprint == fp:
            result[req.id] = cached
            continue
        tokens = _tokenize(_requirement_text(req))
        result[req.id] = SrVector(
            sr_id=req.id,
            fingerprint=fp,
            term_counts=dict(Counter(tokens)),
            length=len(tokens),
        )
    return result


def _tfidf_weights(vectors: dict[str, SrVector]) -> dict[str, dict[str, float]]:
    """Fresh, corpus-wide TF-IDF weights over the given (possibly cached)
    per-SR term-frequency vectors -- see the module docstring for why this
    layer is never itself cached."""
    n = len(vectors)
    df: Counter[str] = Counter()
    for vector in vectors.values():
        for term in vector.term_counts:
            df[term] += 1
    weights: dict[str, dict[str, float]] = {}
    for sr_id, vector in vectors.items():
        if vector.length == 0:
            weights[sr_id] = {}
            continue
        w: dict[str, float] = {}
        for term, count in vector.term_counts.items():
            tf = count / vector.length
            idf = math.log((n + 1) / (df[term] + 1)) + 1
            w[term] = tf * idf
        weights[sr_id] = w
    return weights


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def has_declared_relation(a: Requirement, b: Requirement) -> bool:
    """True when EITHER SR names the other in EITHER `upstream` or
    `relates_to` -- a relation need not be declared from both sides (SR-057
    landed both fields as one-directional declarations)."""
    return (
        b.id in a.upstream
        or b.id in a.relates_to
        or a.id in b.upstream
        or a.id in b.relates_to
    )


def pair_id(a: str, b: str) -> str:
    """A deterministic, order-independent id for the unordered pair {a, b}."""
    lo, hi = sorted((a, b))
    return f"{lo}__{hi}"


@dataclass(frozen=True)
class OverlapCandidate:
    """One candidate pair that survived AC-1's narrowing + declared-relation
    intersection: lexically similar, and no declared relation either way.
    `sr_a`/`sr_b` are always in sorted order (`sr_a < sr_b`), matching
    `pair_id`."""

    pair_id: str
    sr_a: str
    sr_b: str
    score: float
    sr_a_statement: str
    sr_b_statement: str


def generate_candidates(
    reqs: list[Requirement],
    *,
    k: int = DEFAULT_K,
    cache: dict[str, SrVector] | None = None,
) -> tuple[list[OverlapCandidate], dict[str, SrVector]]:
    """AC-1's full narrowing pipeline: vectorize (reusing `cache` for
    unchanged SRs), compute each SR's top-`k` nearest neighbours by cosine
    similarity, then keep only the pairs that ALSO carry no declared relation
    (Layer-1 intersection). Returns `(candidates, vectors)` -- `vectors` is
    the fresh `{sr_id: SrVector}` map the caller should persist as the next
    run's cache (this function performs no I/O itself).

    Candidate count is bounded by `O(N*k)` -- each SR contributes at most `k`
    neighbours before the declared-relation filter (which only ever removes
    candidates, never adds any) -- never the full `O(N^2)` pairwise set,
    regardless of how large or uniformly similar the corpus is. Sorted by
    descending score (ties broken by `pair_id`) for a stable, deterministic
    output order.
    """
    vectors = compute_vectors(reqs, cache)
    weights = _tfidf_weights(vectors)
    reqs_by_id = {r.id: r for r in reqs}
    ids = sorted(weights)

    seen_pairs: set[str] = set()
    candidates: list[OverlapCandidate] = []
    for sr_id in ids:
        scored: list[tuple[str, float]] = []
        for other_id in ids:
            if other_id == sr_id:
                continue
            score = _cosine(weights[sr_id], weights[other_id])
            if score <= 0.0:
                continue
            scored.append((other_id, score))
        scored.sort(key=lambda t: (-t[1], t[0]))
        for other_id, score in scored[:k]:
            pid = pair_id(sr_id, other_id)
            if pid in seen_pairs:
                continue
            seen_pairs.add(pid)
            req_a, req_b = reqs_by_id[sr_id], reqs_by_id[other_id]
            if has_declared_relation(req_a, req_b):
                continue
            a_id, b_id = sorted((sr_id, other_id))
            candidates.append(
                OverlapCandidate(
                    pair_id=pid,
                    sr_a=a_id,
                    sr_b=b_id,
                    score=round(score, 6),
                    sr_a_statement=reqs_by_id[a_id].statement,
                    sr_b_statement=reqs_by_id[b_id].statement,
                )
            )
    candidates.sort(key=lambda c: (-c.score, c.pair_id))
    return candidates, vectors


# ---------------------------------------------------------------------------
# AC-1 cache persistence (`.factory/overlap-index/vectors.json`, mirroring
# `.factory/code-index/` -- a derived, disposable, rebuildable-from-source
# cache, never a second system of record; see the seed doc's "On 'SQL
# perhaps?'" section).
# ---------------------------------------------------------------------------


def vector_cache_path(root: Path) -> Path:
    return root.joinpath(*_VECTOR_CACHE_DIR, "vectors.json")


def load_vector_cache(root: Path) -> dict[str, SrVector]:
    """The previously persisted `{sr_id: SrVector}` cache, or `{}` when no
    cache file exists, it is unreadable, or its content does not validate --
    a missing/corrupt cache degrades to "recompute everything", never a
    crash (this is a derived cache, always safely rebuildable)."""
    path = vector_cache_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    cache: dict[str, SrVector] = {}
    for sr_id, entry in raw.items():
        try:
            cache[sr_id] = SrVector(
                sr_id=str(sr_id),
                fingerprint=str(entry["fingerprint"]),
                term_counts={str(t): int(c) for t, c in entry["term_counts"].items()},
                length=int(entry["length"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return cache


def save_vector_cache(root: Path, vectors: dict[str, SrVector]) -> Path:
    """Persist `vectors` atomically (tmp-file + replace, this repo's usual
    write pattern -- see e.g. `coherence.gate.store.write_decision`)."""
    path = vector_cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        sr_id: {
            "fingerprint": v.fingerprint,
            "term_counts": v.term_counts,
            "length": v.length,
        }
        for sr_id, v in vectors.items()
    }
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# AC-2: model verification
# ---------------------------------------------------------------------------


class OverlapJudgeUnavailable(RuntimeError):
    """Raised internally (never propagated past `verify_candidates`) when a
    judge call could not produce a trustworthy verdict -- the failure is
    always turned into an explicit `status="unavailable"` `OverlapVerification`
    instead."""


_VERIFICATION_STATUSES = ("confirmed", "dismissed", "unavailable")


@dataclass(frozen=True)
class OverlapVerification:
    """The model-verification outcome for one `OverlapCandidate`.

    `status`:
    - `"confirmed"`: the judge independently agrees this is a plausible
      overlap -- becomes a gate item a human must resolve.
    - `"dismissed"`: the judge ran and determined this is not a real
      overlap -- NEVER surfaced to a human.
    - `"unavailable"`: the judge failed, timed out, or returned a shape this
      function could not validate -- explicitly distinct from `"dismissed"`;
      "wasn't actually checked" must never read as "checked, found nothing".
    """

    candidate: OverlapCandidate
    status: str
    rationale: str = ""
    suggested_relation: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "pair_id": self.candidate.pair_id,
            "sr_a": self.candidate.sr_a,
            "sr_b": self.candidate.sr_b,
            "score": self.candidate.score,
            "status": self.status,
            "rationale": self.rationale,
            "suggested_relation": self.suggested_relation,
            "error": self.error,
        }


def verify_candidates(
    candidates: list[OverlapCandidate],
    judge: Callable[[OverlapCandidate], dict],
) -> list[OverlapVerification]:
    """Run AC-2's model-verification step over every surviving candidate.

    `judge(candidate)` must return a dict with a boolean `"confirmed"` key
    (required), plus optional `"rationale"` and `"suggested_relation"`
    strings. ANY failure -- the judge raises, or returns something that does
    not validate -- produces `status="unavailable"` for that candidate only
    (unlike `review_fidelity`'s whole-packet all-or-nothing posture, each
    candidate here is judged independently, so one candidate's judge failure
    never hides another candidate's real verdict). A `False` `"confirmed"`
    produces `status="dismissed"`; a genuinely-dismissed candidate is never
    given a gate item and never reaches a human.
    """
    results: list[OverlapVerification] = []
    for candidate in candidates:
        try:
            raw = judge(candidate)
        except Exception as exc:  # noqa: BLE001 - a judge failure must never propagate or silently pass
            results.append(
                OverlapVerification(
                    candidate=candidate, status="unavailable", error=f"judge failed: {exc}"
                )
            )
            continue

        if not isinstance(raw, dict) or "confirmed" not in raw:
            results.append(
                OverlapVerification(
                    candidate=candidate,
                    status="unavailable",
                    error=f"judge output missing a 'confirmed' key: {str(raw)[:200]}",
                )
            )
            continue

        confirmed = raw.get("confirmed")
        if not isinstance(confirmed, bool):
            results.append(
                OverlapVerification(
                    candidate=candidate,
                    status="unavailable",
                    error=f"judge 'confirmed' must be a bool, got {confirmed!r}",
                )
            )
            continue

        rationale = str(raw.get("rationale") or "").strip()
        suggested_raw = raw.get("suggested_relation")
        suggested_relation = str(suggested_raw).strip() if suggested_raw else None
        results.append(
            OverlapVerification(
                candidate=candidate,
                status="confirmed" if confirmed else "dismissed",
                rationale=rationale,
                suggested_relation=suggested_relation,
            )
        )
    return results


# ---------------------------------------------------------------------------
# AC-2: human decision capture via the existing gate/DecisionFile mechanism
# ---------------------------------------------------------------------------


def gate_id_for_run(run_id: str) -> str:
    return f"overlap:{run_id}"


def gate_item_id(run_id: str, candidate_pair_id: str) -> str:
    """Mirrors `coherence.audit.runner._gate_item_ids`'s
    ``coverage:<run_id>:proposal:<id>`` shape."""
    return f"overlap:{run_id}:candidate:{candidate_pair_id}"


def run_overlap_check(
    root: Path,
    run_dir: Path,
    *,
    run_id: str,
    judge: Callable[[OverlapCandidate], dict],
    k: int = DEFAULT_K,
    unattended: bool = False,
    no_gates: bool = False,
) -> dict:
    """The full AC-1 -> AC-2 pipeline for one run: load the register,
    narrow to candidates (reusing the persisted vector cache), verify each
    surviving candidate with `judge`, and -- for any `"confirmed"` result --
    resolve (or report the need to author) a human decision through the
    existing `coherence.gate` mechanism.

    Returns a JSON-able dict: `"candidates"` (every verification, confirmed/
    dismissed/unavailable alike) and `"gate"` (`None` when nothing was
    confirmed; otherwise the gate's resolution state -- `"blocked"` with a
    `decision_path` and the still-needed `item ids` when no decision file
    exists yet and a human is available to author one, `"blocked_unattended"`
    when no human is available either, `"skipped"` under `no_gates`, or the
    resolved action (`"accept"`/`"reject"`/`"defer"`) plus the full decision
    file once one exists).

    Never auto-declares a relation, never auto-resolves a gate, never treats
    a missing decision as accepted -- exactly `coherence.audit.runner.run`'s
    own discipline for its `coverage:<run_id>` gate.
    """
    reqs = load_register(root / "requirements")
    cache = load_vector_cache(root)
    candidates, vectors = generate_candidates(reqs, k=k, cache=cache)
    save_vector_cache(root, vectors)

    verifications = verify_candidates(candidates, judge)
    confirmed = [v for v in verifications if v.status == "confirmed"]

    result: dict = {
        "run_id": run_id,
        "candidates": [v.to_dict() for v in verifications],
        "gate": None,
    }
    if not confirmed:
        return result

    gate_id = gate_id_for_run(run_id)
    items = [gate_item_id(run_id, v.candidate.pair_id) for v in confirmed]

    if no_gates:
        result["gate"] = {"status": "skipped", "items": items}
        return result

    resolved = resolve_gate(run_dir, gate_id, unattended=unattended)
    if resolved is None:
        result["gate"] = {
            "status": "blocked",
            "decision_path": str(decision_path(run_dir, gate_id)),
            "items": items,
        }
        return result
    if resolved == "blocked":
        result["gate"] = {
            "status": "blocked_unattended",
            "decision_path": str(decision_path(run_dir, gate_id)),
            "items": items,
        }
        return result

    decision_file: DecisionFile
    try:
        decision_file = load_decision(decision_path(run_dir, gate_id))
    except CorruptDecisionFile as exc:
        result["gate"] = {"status": "corrupt", "error": str(exc), "items": items}
        return result

    result["gate"] = {"status": resolved, "decisions": decision_file.to_dict(), "items": items}
    return result


__all__ = [
    "DEFAULT_K",
    "OverlapCandidate",
    "OverlapJudgeUnavailable",
    "OverlapVerification",
    "SrVector",
    "compute_vectors",
    "content_fingerprint",
    "gate_id_for_run",
    "gate_item_id",
    "generate_candidates",
    "has_declared_relation",
    "load_vector_cache",
    "pair_id",
    "run_overlap_check",
    "save_vector_cache",
    "vector_cache_path",
    "verify_candidates",
]
