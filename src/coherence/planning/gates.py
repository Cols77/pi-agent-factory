from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from coherence.planning.anchors import authority_anchor_matches
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_frontmatter_loads, strict_json_loads

_REQUIRED_FEATURE_ID = "FEAT-017"
_CONSENT_KEYS = frozenset({"schema", "run_id", "decision", "reviewer", "reason", "requirements"})


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or "\\" in value:
        return False
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        return False
    return not any(part in {"", ".", ".."} for part in value.split("/"))


def _inside(root: Path, path: Path) -> bool:
    return safe_resolve(root, path) is not None


def _read_metadata(path: Path) -> dict[str, Any] | None:
    try:
        post = strict_frontmatter_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        return None
    return dict(post.metadata)


def _source_matches(root: Path, source: object, spec_path: Path) -> bool:
    if not isinstance(source, str) or "#" not in source:
        return False
    source_path, anchor = source.split("#", 1)
    if not _safe_relative(source_path) or not anchor.strip():
        return False
    try:
        safe_source = safe_resolve(root, root / source_path)
        safe_spec = safe_resolve(root, spec_path)
        if safe_source is None or safe_spec is None or safe_source != safe_spec:
            return False
        spec_body = strict_frontmatter_loads(spec_path.read_text(encoding="utf-8")).content
        return authority_anchor_matches(spec_body, anchor)
    except (OSError, RuntimeError, ValueError, yaml.YAMLError):
        return False


def validate_requirement_consent(
    root: Path,
    run_id: str,
    spec_path: Path,
) -> tuple[bool, str]:
    """Validate FEAT-017 registration and explicit external SR consent.

    This is read-only. The planning workflow never creates or modifies the
    dossier, bundle, requirements, or consent decision.
    """
    project_root = safe_root(root)
    if project_root is None:
        return False, "project root contains a symlink or reparse point"
    feature_path = project_root / "docs" / "features" / f"{_REQUIRED_FEATURE_ID}.md"
    bundle_path = project_root / "bundles" / f"{_REQUIRED_FEATURE_ID}.json"
    requirements_dir = project_root / "requirements"
    safe_feature_path = safe_resolve(project_root, feature_path)
    safe_bundle_path = safe_resolve(project_root, bundle_path)
    if safe_feature_path is None or not safe_feature_path.is_file():
        return False, "FEAT-017 feature dossier is missing"
    if safe_bundle_path is None or not safe_bundle_path.is_file():
        return False, "FEAT-017 bundle is missing"
    metadata = _read_metadata(safe_feature_path)
    if metadata is None or metadata.get("id") != _REQUIRED_FEATURE_ID:
        return False, "FEAT-017 feature dossier is malformed"
    raw_ids = metadata.get("requirements")
    if not isinstance(raw_ids, list) or not raw_ids or not all(isinstance(item, str) for item in raw_ids):
        return False, "FEAT-017 feature dossier has no valid requirement list"
    requirement_ids = sorted(raw_ids)
    if len(requirement_ids) != len(set(requirement_ids)) or not all(
        item.startswith("SR-") and _safe_relative(item) for item in requirement_ids
    ):
        return False, "FEAT-017 feature dossier has invalid requirement identifiers"

    try:
        bundle = strict_json_loads(safe_bundle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False, "FEAT-017 bundle is invalid JSON"
    if not isinstance(bundle, dict) or bundle.get("id") != _REQUIRED_FEATURE_ID:
        return False, "FEAT-017 bundle has an invalid id"
    members = bundle.get("members")
    expected_members = {"feat:FEAT-017", *(f"sr:{req_id}" for req_id in requirement_ids)}
    if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
        return False, "FEAT-017 bundle has invalid members"
    if len(members) != len(set(members)) or set(members) != expected_members:
        return False, "FEAT-017 bundle is not closed over the feature requirements"

    for req_id in requirement_ids:
        req_path = requirements_dir / f"{req_id}.md"
        safe_req_path = safe_resolve(project_root, req_path)
        if safe_req_path is None or not safe_req_path.is_file():
            return False, f"{req_id} requirement escapes the project root"
        req_metadata = _read_metadata(safe_req_path)
        if req_metadata is None:
            return False, f"{req_id} requirement is missing or malformed"
        if any(
            not isinstance(req_metadata.get(field), str) or not str(req_metadata[field]).strip()
            for field in ("id", "title", "statement", "domain")
        ):
            return False, f"{req_id} requirement has incomplete canonical fields"
        upstream = req_metadata.get("upstream")
        if not isinstance(upstream, list) or any(not isinstance(item, str) for item in upstream):
            return False, f"{req_id} requirement has invalid upstream metadata"
        if req_metadata.get("id") != req_id or not _source_matches(project_root, req_metadata.get("source"), spec_path):
            return False, f"{req_id} requirement is not sourced from the authority spec"

    consent_path = project_root / ".factory" / "planning" / run_id / "requirement-consent.json"
    if not _inside(project_root, consent_path):
        return False, "requirement consent path escapes the project root"
    try:
        consent = strict_json_loads(consent_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False, "explicit human requirement consent is missing or invalid"
    if not isinstance(consent, dict) or set(consent) != _CONSENT_KEYS:
        return False, "explicit human requirement consent has an invalid schema"
    if type(consent.get("schema")) is not int or consent.get("schema") != 1:
        return False, "explicit human requirement consent schema must equal 1"
    if consent.get("run_id") != run_id or consent.get("decision") != "approve" or consent.get("reviewer") != "human":
        return False, "explicit human requirement consent is not approved by a human"
    reason = consent.get("reason")
    consent_ids = consent.get("requirements")
    if not isinstance(reason, str) or not reason.strip() or consent_ids != requirement_ids:
        return False, "explicit human requirement consent does not cover the exact requirement set"
    return True, "requirement consent and FEAT-017 registration are current"


__all__ = ["validate_requirement_consent"]
