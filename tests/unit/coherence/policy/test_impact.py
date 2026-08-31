from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from coherence.policy.ci import campaign_ci_commands, required_ci_commands
from coherence.policy.impact import CAMPAIGN_ORDER, classify_changed_paths
from scripts.ci import changed_campaigns

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["src/coherence/trace/model.py"], ("unit", "integration", "static")),
        (["src/coherence/policy/compiler.py"], ("full",)),
        (["src/factory/orchestrator/runner.py"], ("unit", "integration", "e2e", "static")),
        (["src/factory/polish/worker.py"], ("unit", "integration", "e2e", "static")),
        (["src/substrate/paths.py"], ("unit", "integration", "static")),
        (["tests/unit/coherence/test_trace.py"], ("unit",)),
        (["tests/integration/test_trace.py"], ("integration",)),
        (["tests/e2e/test_pipeline.py"], ("e2e",)),
        (["tests/conftest.py"], ("full",)),
        (["tests/fixtures/seed.yaml"], ("full",)),
        (["pi-ext/scope-guard/index.ts"], ("integration", "extensions")),
        ([".factory/factory.yaml"], ("full",)),
        (["pyproject.toml"], ("full",)),
        (["uv.lock"], ("full",)),
        (["scripts/ci/changed_campaigns.py"], ("full",)),
        (["schemas/evidence.json"], ("full",)),
        (["docs/design.md"], ("structural",)),
        (["requirements/SR-001.md"], ("structural",)),
        (["plans/next.md"], ("structural",)),
        (["README.md"], ("full",)),
    ],
)
def test_classifies_every_initial_path_bucket(paths, expected):
    assert classify_changed_paths(paths) == expected


def test_mixed_paths_are_unioned_in_stable_order_without_duplicates():
    paths = [
        "src/factory/orchestrator/runner.py",
        "src/substrate/paths.py",
        "pi-ext/scope-guard/index.ts",
        "docs/design.md",
        "src/factory/orchestrator/runner.py",
    ]

    assert classify_changed_paths(paths) == (
        "unit",
        "integration",
        "e2e",
        "extensions",
        "static",
        "structural",
    )


def test_full_is_the_only_campaign_when_any_path_requires_broad_validation():
    assert classify_changed_paths(["src/coherence/trace/model.py", "README.md"]) == ("full",)


@pytest.mark.parametrize("paths", [None, [], (), iter(())])
def test_empty_or_unavailable_diff_fails_closed_to_full(paths):
    assert classify_changed_paths(paths) == ("full",)


@pytest.mark.parametrize(
    "path",
    [
        r".\src\factory\orchestrator\runner.py",
        r"src\factory\polish\worker.py",
        r".\docs\design.md",
    ],
)
def test_windows_separators_and_dot_prefix_are_normalized(path):
    assert classify_changed_paths([path]) in {
        ("unit", "integration", "e2e", "static"),
        ("structural",),
    }


def test_unclassifiable_and_shared_paths_fail_closed():
    assert classify_changed_paths([".github/workflows/ci.yml"]) == ("full",)
    assert classify_changed_paths(["src/shared/common.py"]) == ("full",)
    assert classify_changed_paths([""]) == ("full",)


def test_campaign_order_is_explicit_and_contains_only_internal_identifiers():
    assert CAMPAIGN_ORDER == (
        "unit",
        "integration",
        "e2e",
        "extensions",
        "static",
        "structural",
        "full",
    )


def _seed(root: Path) -> None:
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "    - { cmd: \"{python} -m pytest -m unit -q\" }\n"
        "  integration:\n"
        "    - { cmd: \"{python} -m pytest tests/integration/ -q -m integration\" }\n"
        "  full:\n"
        "    - { cmd: \"{python} -m ruff check .\" }\n"
        "    - { cmd: \"{python} -m pyright\" }\n"
        "    - { cmd: \"{python} -m pytest -m unit -q\" }\n"
        "    - { cmd: \"{python} scripts/gates/ext.py\" }\n"
        "    - { cmd: \"{python} scripts/gates/watch_ext.py\" }\n",
        encoding="utf-8",
    )


def test_full_campaign_projection_is_exactly_the_existing_all_command_list(tmp_path):
    _seed(tmp_path)

    assert campaign_ci_commands(tmp_path, ("full",)) == required_ci_commands(tmp_path)


def test_narrow_projection_uses_declared_commands_and_keeps_extension_scripts_direct(tmp_path):
    _seed(tmp_path)

    assert campaign_ci_commands(tmp_path, ("unit",)) == [
        f"{sys.executable} -m pytest -m unit -q",
    ]
    assert campaign_ci_commands(tmp_path, ("integration",)) == [
        f"{sys.executable} -m pytest tests/integration/ -q -m integration",
    ]
    assert campaign_ci_commands(tmp_path, ("static",)) == [
        f"{sys.executable} -m ruff check .",
        f"{sys.executable} -m pyright",
    ]
    assert campaign_ci_commands(tmp_path, ("extensions",)) == [
        f"{sys.executable} scripts/gates/ext.py",
        f"{sys.executable} scripts/gates/watch_ext.py",
    ]
    assert campaign_ci_commands(tmp_path, ("structural",)) == [
        "coherence trace check",
        "coherence register check",
    ]


def test_unavailable_narrow_campaign_falls_back_to_full_instead_of_passing_empty(tmp_path):
    _seed(tmp_path)

    full = required_ci_commands(tmp_path)
    assert campaign_ci_commands(tmp_path, ("e2e",)) == full
    assert campaign_ci_commands(tmp_path, ()) == full
    assert campaign_ci_commands(tmp_path, ("not-an-internal-campaign",)) == full


def test_projection_deduplicates_commands_and_preserves_all_command_parity(tmp_path):
    _seed(tmp_path)

    selected = campaign_ci_commands(tmp_path, ("unit", "static", "extensions"))
    assert selected == [
        f"{sys.executable} -m pytest -m unit -q",
        f"{sys.executable} scripts/gates/ext.py",
        f"{sys.executable} scripts/gates/watch_ext.py",
        f"{sys.executable} -m ruff check .",
        f"{sys.executable} -m pyright",
    ]
    assert all(command in required_ci_commands(tmp_path) for command in selected)
    assert len(selected) == len(set(selected))


def test_projection_result_is_json_serializable_for_workflow_matrix(tmp_path):
    _seed(tmp_path)

    encoded = json.dumps(list(classify_changed_paths(["src/substrate/paths.py"])))
    assert json.loads(encoded) == ["unit", "integration", "static"]


@pytest.mark.parametrize(
    ("event", "environment", "expected_endpoints"),
    [
        (
            "pull_request",
            {"GITHUB_BASE_SHA": "base", "GITHUB_HEAD_SHA": "head"},
            ("base", "head"),
        ),
        (
            "push",
            {"GITHUB_BEFORE_SHA": "before", "GITHUB_AFTER_SHA": "after"},
            ("before", "after"),
        ),
    ],
)
def test_ci_adapter_uses_provider_endpoints_only_at_the_adapter_boundary(
    monkeypatch, event, environment, expected_endpoints
):
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    for key in (
        "GITHUB_BASE_SHA",
        "GITHUB_HEAD_SHA",
        "GITHUB_BEFORE_SHA",
        "GITHUB_AFTER_SHA",
        "GITHUB_SHA",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    observed = []

    def fake_diff(_root, base, head):
        observed.append((base, head))
        return ["src/coherence/trace/model.py"]

    monkeypatch.setattr(changed_campaigns, "_committed_diff", fake_diff)

    assert changed_campaigns.acquire_paths(Path(".")) == ["src/coherence/trace/model.py"]
    assert observed == [expected_endpoints]


def test_ci_adapter_supports_explicit_local_working_tree_input(monkeypatch):
    monkeypatch.setattr(
        changed_campaigns,
        "_working_tree_diff",
        lambda _root: ["tests/unit/coherence/test_trace.py"],
    )

    assert changed_campaigns.acquire_paths(Path("."), working_tree=True) == [
        "tests/unit/coherence/test_trace.py"
    ]
