from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import frontmatter

# `binding` is deliberately absent: a requirement may be agreed in substance
# before its measurement is decided. The absence of a binding IS the proposed
# state -- there is no status field that could disagree with the content.
_REQUIRED = ("id", "title", "statement", "domain")


@dataclass(frozen=True)
class Binding:
    experiment: str
    metric: str
    assert_expr: str
    # A requirement may have a decided measurement before its instrument exists.
    # `None` is the "no harness named yet" state -- a WARNING, never a blocker.
    harness: str | None = None
    trials: int = 1
    window: dict | None = None
    cadence: str = "every_iteration"


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    statement: str
    domain: str
    upstream: list[str]
    binding: Binding | None
    body: str
    path: Path
    checksum: str | None = None
    source: str | None = None


def _parse_binding(raw: dict) -> Binding:
    harness = raw.get("harness")
    return Binding(
        experiment=str(raw["experiment"]),
        metric=str(raw["metric"]),
        assert_expr=str(raw["assert"]),
        harness=str(harness) if harness else None,
        trials=int(raw.get("trials", 1)),
        window=raw.get("window"),
        cadence=str(raw.get("cadence", "every_iteration")),
    )


def parse_requirement(path: Path) -> Requirement:
    post = frontmatter.load(str(path))
    meta = post.metadata
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {missing}")
    upstream = meta.get("upstream") or []
    if isinstance(upstream, str):
        upstream = [upstream]
    checksum = meta.get("checksum")
    source = meta.get("source")
    return Requirement(
        id=str(meta["id"]),
        title=str(meta["title"]),
        statement=str(meta["statement"]),
        domain=str(meta["domain"]),
        upstream=[str(u) for u in upstream],  # type: ignore[union-attr]
        binding=_parse_binding(meta["binding"]) if "binding" in meta else None,  # type: ignore[arg-type]
        body=post.content,
        path=path,
        checksum=str(checksum) if checksum else None,
        source=str(source) if source else None,
    )


def content_checksum(req: Requirement) -> str:
    # cadence is intentionally excluded: it is scheduling (how often the SR runs),
    # not a metric input, so changing it must not stale the requirement.
    b = req.binding
    if b is None:
        raise ValueError(f"{req.id}: proposed requirement has no binding to checksum")
    canonical = "\n".join(
        [
            req.statement.strip(),
            b.harness or "",
            b.experiment,
            b.metric,
            b.assert_expr,
            str(b.trials),
            repr(b.window),
        ]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_checksum_current(req: Requirement) -> bool:
    # A proposed requirement has no binding, so there is nothing for a checksum to
    # go stale against. Returning False would print STALE forever.
    if req.binding is None:
        return True
    return req.checksum is not None and req.checksum == content_checksum(req)


def load_register(requirements_dir: Path) -> list[Requirement]:
    if not requirements_dir.exists():
        return []
    return sorted(
        (parse_requirement(p) for p in requirements_dir.glob("SR-*.md")),
        key=lambda r: r.id,
    )


def get_requirement(reqs: list[Requirement], req_id: str) -> Requirement | None:
    return next((r for r in reqs if r.id == req_id), None)


__all__ = [
    "Binding",
    "Requirement",
    "content_checksum",
    "get_requirement",
    "is_checksum_current",
    "load_register",
    "parse_requirement",
]
