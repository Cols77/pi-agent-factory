from __future__ import annotations

import json

import pytest

from coherence.planning.model_policy import (
    ModelCatalogEntry,
    ModelPolicyError,
    load_model_policy,
    persist_model_selection,
    select_classifier,
    select_reviewer,
)

pytestmark = pytest.mark.unit


def policy_payload() -> dict[str, object]:
    return {
        "schema": 1,
        "no_secrets": True,
        "classifier": {"provider": "openai", "model": "gpt-mini"},
        "reviewer_candidates": [
            {"provider": "openai", "model": "gpt-review", "quality_tier": "high", "local": False, "cost_class": "low", "free": False},
            {"provider": "ollama", "model": "llama-review", "quality_tier": "standard", "local": True, "cost_class": "free", "free": True},
        ],
    }


def catalog() -> tuple[ModelCatalogEntry, ...]:
    return tuple(ModelCatalogEntry(**entry) for entry in policy_payload()["reviewer_candidates"]) + (
        ModelCatalogEntry("openai", "gpt-mini", "standard", False, "low", False),
    )


def test_policy_loads_in_stable_provider_model_order(tmp_path):
    path = tmp_path / ".factory" / "planning" / "models.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(policy_payload()), encoding="utf-8")
    policy = load_model_policy(tmp_path)
    assert [entry.key for entry in policy.reviewer_candidates] == ["ollama:llama-review", "openai:gpt-review"]
    assert select_classifier(policy, catalog()).key == "openai:gpt-mini"


def test_duplicate_and_secret_shaped_values_are_rejected(tmp_path):
    payload = policy_payload()
    payload["reviewer_candidates"] = list(payload["reviewer_candidates"]) + [payload["reviewer_candidates"][0]]
    path = tmp_path / ".factory" / "planning" / "models.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelPolicyError, match="duplicate"):
        load_model_policy(tmp_path)

    payload = policy_payload()
    payload["classifier"] = {"provider": "openai", "model": "sk-api-key-secret"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ModelPolicyError, match="secret"):
        load_model_policy(tmp_path)


def test_missing_catalog_or_configured_model_fails_closed():
    policy = load_model_policy_from_payload(policy_payload())
    with pytest.raises(ModelPolicyError, match="catalog"):
        select_classifier(policy, ())
    with pytest.raises(ModelPolicyError, match="configured"):
        select_reviewer(policy, (ModelCatalogEntry("other", "model", "standard", True, "free", True),), "ollama:llama-review")


def test_selection_is_persisted_once_and_reused(tmp_path):
    policy = load_model_policy_from_payload(policy_payload())
    entries = catalog()
    first = persist_model_selection(tmp_path, "run-1", select_classifier(policy, entries), select_reviewer(policy, entries, "ollama:llama-review"))
    second = persist_model_selection(tmp_path, "run-1", entries[-1], entries[0])
    assert first == second
    assert json.loads(first.read_text(encoding="utf-8"))["reviewer"]["provider"] == "ollama"


def load_model_policy_from_payload(payload: dict[str, object]):
    from coherence.planning.model_policy import parse_model_policy

    return parse_model_policy(payload)
