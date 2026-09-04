"""Deterministic, non-secret model policy for planning reviews.

Provider discovery remains a host responsibility.  This module only validates the
project's declared metadata and intersects it with a native host catalog.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_POLICY_RELATIVE_PATH = Path(".factory/planning/models.json")
_SECRET_RE = re.compile(r"(?i)(?:api[_-]?key|secret|password|passwd|token|bearer|sk-[A-Za-z0-9])")
_QUALITY = {"basic", "standard", "high", "frontier"}
_COST = {"free", "low", "moderate", "high", "unknown"}


class ModelPolicyError(ValueError):
    """A policy or host catalog cannot safely satisfy planning model selection."""


@dataclass(frozen=True, order=True)
class ModelCatalogEntry:
    provider: str
    model: str
    quality_tier: str
    local: bool
    cost_class: str
    free: bool

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "quality_tier": self.quality_tier,
            "local": self.local,
            "cost_class": self.cost_class,
            "free": self.free,
        }


@dataclass(frozen=True)
class ModelPolicy:
    schema: int
    no_secrets: bool
    classifier: ModelCatalogEntry
    reviewer_candidates: tuple[ModelCatalogEntry, ...]

    @property
    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        return self.reviewer_candidates


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelPolicyError(f"malformed {field} metadata")
    if _SECRET_RE.search(value):
        raise ModelPolicyError(f"secret-shaped {field} value rejected")
    return value


def _entry(value: object, field: str) -> ModelCatalogEntry:
    if not isinstance(value, dict):
        raise ModelPolicyError(f"malformed {field} metadata")
    required = {"provider", "model", "quality_tier", "local", "cost_class", "free"}
    if set(value) != required:
        raise ModelPolicyError(f"malformed {field} metadata")
    provider = _text(value["provider"], f"{field}.provider")
    model = _text(value["model"], f"{field}.model")
    quality = _text(value["quality_tier"], f"{field}.quality_tier")
    cost = _text(value["cost_class"], f"{field}.cost_class")
    if quality not in _QUALITY or cost not in _COST or type(value["local"]) is not bool or type(value["free"]) is not bool:
        raise ModelPolicyError(f"malformed {field} metadata")
    if value["free"] != (cost == "free"):
        raise ModelPolicyError(f"malformed {field}.free metadata")
    return ModelCatalogEntry(provider, model, quality, value["local"], cost, value["free"])


def parse_model_policy(payload: object) -> ModelPolicy:
    if not isinstance(payload, dict) or set(payload) != {"schema", "no_secrets", "classifier", "reviewer_candidates"}:
        raise ModelPolicyError("malformed model policy")
    if payload["schema"] != 1 or payload["no_secrets"] is not True:
        raise ModelPolicyError("model policy schema/no-secret policy is invalid")
    classifier_payload = payload["classifier"]
    # Classifier identity is configured explicitly; metadata is optional because
    # the host is the authority for its native capability catalog.
    if isinstance(classifier_payload, dict) and set(classifier_payload) == {"provider", "model"}:
        classifier_payload = {
            **classifier_payload,
            "quality_tier": "standard",
            "local": False,
            "cost_class": "unknown",
            "free": False,
        }
    classifier = _entry(classifier_payload, "classifier")
    raw_candidates = payload["reviewer_candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ModelPolicyError("reviewer_candidates must be a non-empty list")
    candidates = tuple(sorted((_entry(item, "reviewer candidate") for item in raw_candidates), key=lambda e: e.key))
    keys = [entry.key for entry in (classifier, *candidates)]
    if len(keys) != len(set(keys)):
        raise ModelPolicyError("duplicate provider/model entries")
    return ModelPolicy(1, True, classifier, candidates)


def load_model_policy(root: Path, path: Path | None = None) -> ModelPolicy:
    policy_path = path or (root / _POLICY_RELATIVE_PATH)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelPolicyError("model policy is missing or invalid") from exc
    return parse_model_policy(payload)


def _catalog(entries: Iterable[ModelCatalogEntry]) -> dict[str, ModelCatalogEntry]:
    result: dict[str, ModelCatalogEntry] = {}
    for entry in entries:
        if not isinstance(entry, ModelCatalogEntry):
            raise ModelPolicyError("native model catalog metadata is malformed")
        if entry.key in result:
            raise ModelPolicyError("duplicate native provider/model entries")
        result[entry.key] = entry
    return result


def select_classifier(policy: ModelPolicy, catalog: Iterable[ModelCatalogEntry]) -> ModelCatalogEntry:
    available = _catalog(catalog)
    if not available:
        raise ModelPolicyError("native model catalog is unavailable")
    selected = available.get(policy.classifier.key)
    if selected is None:
        raise ModelPolicyError("configured classifier is unavailable")
    return selected


def select_reviewer(policy: ModelPolicy, catalog: Iterable[ModelCatalogEntry], key: str) -> ModelCatalogEntry:
    available = _catalog(catalog)
    allowed = {entry.key for entry in policy.reviewer_candidates}
    if key not in allowed:
        raise ModelPolicyError("reviewer choice is not configured")
    selected = available.get(key)
    if selected is None:
        raise ModelPolicyError("configured reviewer is unavailable")
    return selected


def persist_model_selection(root: Path, run_id: str, classifier: ModelCatalogEntry, reviewer: ModelCatalogEntry) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ModelPolicyError("invalid planning run id")
    destination = root / ".factory" / "planning" / run_id / "model-selection.json"
    payload = {"schema": 1, "classifier": classifier.to_dict(), "reviewer": reviewer.to_dict()}
    # The host catalog is untrusted input at this boundary too: selection files
    # must remain non-secret even when a caller bypasses policy parsing.
    _entry(payload["classifier"], "classifier")
    _entry(payload["reviewer"], "reviewer")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
            if (
                not isinstance(existing, dict)
                or existing.get("schema") != 1
                or set(existing) != {"schema", "classifier", "reviewer"}
            ):
                raise ModelPolicyError("persisted model selection is invalid")
            _entry(existing["classifier"], "persisted classifier")
            _entry(existing["reviewer"], "persisted reviewer")
            # A run's reviewer is immutable.  Never replace it with a later
            # checkpoint's proposal; callers reuse the persisted metadata.
            return destination
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ModelPolicyError("persisted model selection is invalid") from exc
    fd, temporary = tempfile.mkstemp(prefix=".model-selection-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


__all__ = ["ModelCatalogEntry", "ModelPolicy", "ModelPolicyError", "load_model_policy", "parse_model_policy", "persist_model_selection", "select_classifier", "select_reviewer"]
