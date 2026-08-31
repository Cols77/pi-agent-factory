"""Conservative classification of changed repository paths into CI campaigns."""
from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable


# These are routing identifiers owned by this module.  They intentionally do not
# expand the Coherence CLI or the project's gate vocabulary.
CAMPAIGN_ORDER: tuple[str, ...] = (
    "unit",
    "integration",
    "e2e",
    "extensions",
    "static",
    "structural",
    "full",
)
FULL_CAMPAIGN = "full"

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:/")


def _normalize_path(value: object) -> str | None:
    """Return a safe repository-relative POSIX path, or ``None`` if invalid."""
    if not isinstance(value, str):
        return None
    path = value.replace("\\", "/")
    if "\x00" in path or any(part == ".." for part in path.split("/")):
        return None
    while path.startswith("./"):
        path = path[2:]
    if (
        not path
        or path in {".", ".."}
        or path.startswith("/")
        or _WINDOWS_ABSOLUTE.match(path)
    ):
        return None
    path = posixpath.normpath(path)
    if path == ".." or path.startswith("../"):
        return None
    return path


def _has_component(path: str, *names: str) -> bool:
    return bool(set(path.split("/")) & set(names))


def _classify_path(path: str) -> tuple[str, ...]:
    """Classify one already-normalized path before global ordering is applied."""
    parts = path.split("/")
    name = parts[-1].lower()
    shared_name = any(word in name for word in ("compiler", "fixture", "loader", "policy"))

    # Configuration, policy, compiler, loader, fixture, and script changes are
    # shared validation inputs. Check these before narrower source/test buckets.
    if (
        parts[0] in {".factory", "scripts"}
        or path in {"pyproject.toml", "uv.lock"}
        or _has_component(path, "schema", "schemas", "fixture", "fixtures", "policy")
        or shared_name
    ):
        return (FULL_CAMPAIGN,)

    # Test infrastructure is not safely attributable to one runtime bucket.
    if parts[0] == "tests":
        if _has_component(path, "fixture", "fixtures") or name == "conftest.py":
            return (FULL_CAMPAIGN,)
        if len(parts) > 1 and parts[1] in {"unit", "integration", "e2e"}:
            return (parts[1],)
        return (FULL_CAMPAIGN,)

    if parts[0] == "pi-ext":
        # Extension changes are exercised by the direct extension gates and by
        # the Python integration boundary that consumes the extension bridge.
        return ("integration", "extensions")

    if parts[0] == "src":
        prefix = "/".join(parts[:2]) if len(parts) >= 2 else path
        if prefix == "src/coherence":
            return ("unit", "integration", "static")
        factory_prefix = "/".join(parts[:3]) if len(parts) >= 3 else path
        if factory_prefix in {"src/factory/orchestrator", "src/factory/polish"}:
            return ("unit", "integration", "e2e", "static")
        if prefix == "src/substrate":
            return ("unit", "integration", "static")

    if parts[0] in {"docs", "requirements", "plans"}:
        return ("structural",)

    return (FULL_CAMPAIGN,)


def classify_changed_paths(paths: Iterable[str] | None) -> tuple[str, ...]:
    """Return stable, duplicate-free campaign IDs for changed paths.

    ``None`` and an empty iterable represent unavailable or empty diff input and
    intentionally fail closed to ``("full",)``. Any invalid, unclassifiable, or
    shared path does the same. A full campaign subsumes every narrower campaign.
    """
    if paths is None or isinstance(paths, (str, bytes)):
        return (FULL_CAMPAIGN,)

    try:
        raw_paths = list(paths)
    except Exception:
        return (FULL_CAMPAIGN,)
    if not raw_paths:
        return (FULL_CAMPAIGN,)

    selected: set[str] = set()
    for raw_path in raw_paths:
        path = _normalize_path(raw_path)
        if path is None:
            return (FULL_CAMPAIGN,)
        campaigns = _classify_path(path)
        if FULL_CAMPAIGN in campaigns:
            return (FULL_CAMPAIGN,)
        selected.update(campaigns)

    return tuple(campaign for campaign in CAMPAIGN_ORDER if campaign in selected)
