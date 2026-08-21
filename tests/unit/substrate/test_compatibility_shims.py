from __future__ import annotations

import ast
import importlib
import sys
import warnings
from pathlib import Path

import pytest


PUBLIC_SURFACE = {
    "model": (
        "DependencyFingerprint",
        "FreshnessSeverity",
        "FreshnessIssue",
        "FreshnessReport",
        "GATE_FAILING_SEVERITIES",
    ),
    "fingerprint": (
        "sha256_bytes",
        "fingerprint_file",
        "fingerprint_value",
        "fingerprint_tool",
        "fingerprint_git_tree",
    ),
    "evaluate": ("compare_dependencies",),
}
SUBSTRATE_MODULES = (
    "substrate.freshness",
    *(f"substrate.freshness.{module_name}" for module_name in PUBLIC_SURFACE),
)

pytestmark = pytest.mark.unit


def _import_fresh(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _warning_messages(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(item.message) for item in caught if item.category is DeprecationWarning]


def test_substrate_freshness_package_imports_without_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _import_fresh("substrate.freshness")

    assert _warning_messages(caught) == []


@pytest.mark.parametrize("module_name", SUBSTRATE_MODULES)
def test_substrate_freshness_modules_do_not_import_factory_or_coherence(module_name: str):
    module = _import_fresh(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_roots = {
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_roots.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imported_roots.isdisjoint({"factory", "coherence"})


@pytest.mark.parametrize("module_name,symbols", PUBLIC_SURFACE.items())
def test_substrate_freshness_exports_the_frozen_public_surface(module_name: str, symbols: tuple[str, ...]):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        module = _import_fresh(f"substrate.freshness.{module_name}")

    assert _warning_messages(caught) == []
    assert all(hasattr(module, symbol) for symbol in symbols)


@pytest.mark.parametrize("module_name,symbols", PUBLIC_SURFACE.items())
def test_factory_freshness_shim_warns_once_and_preserves_identity(
    module_name: str, symbols: tuple[str, ...]
):
    old_name = f"factory.freshness.{module_name}"
    substrate_name = f"substrate.freshness.{module_name}"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        old_module = _import_fresh(old_name)

    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert str(caught[0].message) == (
        f"{old_name} is deprecated; import {substrate_name}"
    )
    assert old_module.__all__ == list(symbols)

    substrate_module = importlib.import_module(substrate_name)
    assert all(getattr(old_module, symbol) is getattr(substrate_module, symbol) for symbol in symbols)


def test_substrate_model_preserves_enum_values_and_report_serialization():
    model = importlib.import_module("substrate.freshness.model")
    issue = model.FreshnessIssue(
        code="dependency_changed",
        severity=model.FreshnessSeverity.BLOCKING,
        subject="T-001",
        dependency="source",
        expected="old",
        actual="new",
        detail="dependency source changed after evidence was recorded",
    )
    report = model.FreshnessReport([issue])

    assert {severity.value for severity in model.FreshnessSeverity} == {
        "integrity",
        "blocking",
        "warning",
    }
    assert model.GATE_FAILING_SEVERITIES == frozenset(
        {model.FreshnessSeverity.INTEGRITY, model.FreshnessSeverity.BLOCKING}
    )
    assert report.ok is False
    assert report.to_dict() == {
        "ok": False,
        "issues": [
            {
                "code": "dependency_changed",
                "severity": model.FreshnessSeverity.BLOCKING,
                "subject": "T-001",
                "dependency": "source",
                "expected": "old",
                "actual": "new",
                "detail": "dependency source changed after evidence was recorded",
                "repair": None,
            }
        ],
    }
