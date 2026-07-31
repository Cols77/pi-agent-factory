from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import frontmatter

_REQUIRED = ("id", "title", "statement", "domain", "binding")


@dataclass(frozen=True)
class Binding:
    harness: str
    experiment: str
    metric: str
    assert_expr: str
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
    binding: Binding
    body: str
    path: Path
    checksum: str | None = None


def _parse_binding(raw: dict) -> Binding:
    return Binding(
        harness=str(raw["harness"]),
        experiment=str(raw["experiment"]),
        metric=str(raw["metric"]),
        assert_expr=str(raw["assert"]),
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
    return Requirement(
        id=str(meta["id"]),
        title=str(meta["title"]),
        statement=str(meta["statement"]),
        domain=str(meta["domain"]),
        upstream=[str(u) for u in upstream],  # type: ignore[union-attr]
        binding=_parse_binding(meta["binding"]),  # type: ignore[arg-type]
        body=post.content,
        path=path,
        checksum=str(checksum) if checksum else None,
    )


def content_checksum(req: Requirement) -> str:
    b = req.binding
    canonical = "\n".join(
        [
            req.statement.strip(),
            b.harness,
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
