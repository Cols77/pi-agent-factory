"""Audit's own worker-concurrency policy.

``factory.config.FactoryConfig`` is a cross-domain dataclass (playgrounds,
harnesses, gates) shared across the whole factory codebase and this
increment's file-structure list does not put it in this task's hands to
modify -- see the Increment 4 Task 3 controller ruling ("do not add an
``audit:`` section there; that risks the shared-file ownership rule"). Audit
instead reads its own ``audit.max_workers`` key directly from the raw
``.factory/factory.yaml`` YAML, matching the file path
``factory.config.load_config`` already uses, without depending on
``FactoryConfig`` at all.
"""

from __future__ import annotations

from pathlib import Path

import yaml

__all__ = ["DEFAULT_MAX_WORKERS", "audit_max_workers"]

DEFAULT_MAX_WORKERS = 4


def audit_max_workers(root: Path) -> int:
    """Return the configured ``audit.max_workers`` policy value.

    Falls back to :data:`DEFAULT_MAX_WORKERS` when ``.factory/factory.yaml``
    is absent, unreadable, malformed, has no ``audit:`` section, has no
    ``max_workers`` key, or the value found there is not a positive integer.
    """
    config_path = root / ".factory" / "factory.yaml"
    if not config_path.is_file():
        return DEFAULT_MAX_WORKERS
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return DEFAULT_MAX_WORKERS
    if not isinstance(raw, dict):
        return DEFAULT_MAX_WORKERS
    audit_section = raw.get("audit")
    if not isinstance(audit_section, dict):
        return DEFAULT_MAX_WORKERS
    value = audit_section.get("max_workers", DEFAULT_MAX_WORKERS)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return DEFAULT_MAX_WORKERS
    return value
