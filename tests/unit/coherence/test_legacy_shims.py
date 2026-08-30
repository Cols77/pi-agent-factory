from __future__ import annotations

import importlib
import sys
import warnings
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.unit


@contextmanager
def _isolated_legacy_import(module_name: str):
    prefixes = (
        "factory.requirements",
        "coherence.register",
        "factory.doctor",
        "coherence.doctor",
        "factory.coverage",
        "coherence.audit",
        "factory.validation",
        "coherence.measurement",
    )
    names_to_track = set()
    for name in (module_name, *prefixes):
        parts = name.split(".")
        names_to_track.update(".".join(parts[:index]) for index in range(1, len(parts) + 1))

    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name in names_to_track
        or any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    original_attributes = {}
    for name in names_to_track | set(original_modules):
        parent_name, _, child_name = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            original_attributes[(parent, child_name)] = (
                child_name in vars(parent),
                getattr(parent, child_name, None),
            )

    sys.modules.pop(module_name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name in names_to_track or any(
                name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes
            ):
                parent_name, _, child_name = name.rpartition(".")
                parent = sys.modules.get(parent_name)
                if parent is not None and (parent, child_name) not in original_attributes:
                    if child_name in vars(parent):
                        delattr(parent, child_name)
        for name in list(sys.modules):
            if name in names_to_track or any(
                name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes
            ):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)
        for (parent, child_name), (had_attribute, original_attribute) in original_attributes.items():
            if had_attribute:
                setattr(parent, child_name, original_attribute)
            elif hasattr(parent, child_name):
                delattr(parent, child_name)


@pytest.mark.parametrize(
    "module_name,canonical_name",
    [
        ("factory.requirements.register", "coherence.register.register"),
        ("factory.requirements.closure", "coherence.register.closure"),
        ("factory.requirements.write", "coherence.register.write"),
        ("factory.requirements.cli", "coherence.register.cli"),
    ],
)
def test_legacy_register_modules_warn_and_reexport(module_name: str, canonical_name: str):
    with _isolated_legacy_import(module_name):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module(module_name)

        assert any("factory.requirements" in str(item.message) for item in caught)
        canonical = importlib.import_module(canonical_name)
        assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
        for name in canonical.__dict__["__all__"]:
            assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_module_entrypoint_forwards_to_canonical_cli():
    with _isolated_legacy_import("factory.requirements.__main__"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module("factory.requirements.__main__")

        assert any("factory.requirements" in str(item.message) for item in caught)
        assert legacy.main.__module__ == "coherence.register.cli"


def test_legacy_register_import_can_warn_again_after_a_previous_import():
    module_name = "factory.requirements.register"
    with _isolated_legacy_import("factory.requirements.register"):
        with warnings.catch_warnings(record=True) as first_caught:
            warnings.simplefilter("always", DeprecationWarning)
            importlib.import_module(module_name)
        assert any("factory.requirements" in str(item.message) for item in first_caught)

    with _isolated_legacy_import("factory.requirements.register"):
        with warnings.catch_warnings(record=True) as second_caught:
            warnings.simplefilter("always", DeprecationWarning)
            importlib.import_module("factory.requirements.register")
        assert any("factory.requirements" in str(item.message) for item in second_caught)


@pytest.mark.parametrize(
    "module_name,canonical_name",
    [
        ("factory.doctor.context", "coherence.doctor.context"),
        ("factory.doctor.write", "coherence.doctor.write"),
        ("factory.doctor.cli", "coherence.doctor.cli"),
    ],
)
def test_legacy_doctor_modules_warn_and_reexport(module_name: str, canonical_name: str):
    with _isolated_legacy_import(module_name):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module(module_name)

        assert any("factory.doctor" in str(item.message) for item in caught)
        canonical = importlib.import_module(canonical_name)
        assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
        for name in canonical.__dict__["__all__"]:
            assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_doctor_module_entrypoint_forwards_to_canonical_cli():
    with _isolated_legacy_import("factory.doctor.__main__"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module("factory.doctor.__main__")

        assert any("factory.doctor" in str(item.message) for item in caught)
        assert legacy.main.__module__ == "coherence.doctor.cli"


@pytest.mark.parametrize(
    "module_name,canonical_name",
    [
        ("factory.coverage.scope", "coherence.audit.scope"),
        ("factory.coverage.audit", "coherence.audit.audit"),
        ("factory.coverage.gate", "coherence.audit.gate"),
        ("factory.coverage.report", "coherence.audit.report"),
        ("factory.coverage.runner", "coherence.audit.runner"),
        ("factory.coverage.cli", "coherence.audit.cli"),
    ],
)
def test_legacy_coverage_modules_warn_and_reexport(module_name: str, canonical_name: str):
    with _isolated_legacy_import(module_name):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module(module_name)

        assert any("factory.coverage" in str(item.message) for item in caught)
        canonical = importlib.import_module(canonical_name)
        assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
        for name in canonical.__dict__["__all__"]:
            assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_coverage_module_entrypoint_forwards_to_canonical_cli():
    with _isolated_legacy_import("factory.coverage.__main__"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module("factory.coverage.__main__")

        assert any("factory.coverage" in str(item.message) for item in caught)
        assert legacy.main.__module__ == "coherence.audit.cli"


@pytest.mark.parametrize(
    "module_name,canonical_name",
    [
        ("factory.validation.harness", "coherence.measurement.harness"),
        ("factory.validation.sim_harness", "coherence.measurement.sim_harness"),
        ("factory.validation.playwright_harness", "coherence.measurement.playwright_harness"),
        ("factory.validation.pipeline", "coherence.measurement.pipeline"),
        ("factory.validation.report", "coherence.measurement.report"),
        ("factory.validation.scorer_registry", "coherence.measurement.scorer_registry"),
        ("factory.validation.assertions", "coherence.measurement.assertions"),
        ("factory.validation.cli", "coherence.measurement.cli"),
    ],
)
def test_legacy_validation_modules_warn_and_reexport(module_name: str, canonical_name: str):
    with _isolated_legacy_import(module_name):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module(module_name)

        assert any("factory.validation" in str(item.message) for item in caught)
        canonical = importlib.import_module(canonical_name)
        assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
        for name in canonical.__dict__["__all__"]:
            assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_report_identity_survives_a_preceding_pipeline_import():
    from factory.polish import config as _factory_config  # noqa: F401

    with _isolated_legacy_import("factory.validation.pipeline"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            importlib.import_module("factory.validation.pipeline")
        assert any("factory.validation" in str(item.message) for item in caught)

    with _isolated_legacy_import("factory.validation.report"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module("factory.validation.report")

        assert any("factory.validation" in str(item.message) for item in caught)
        canonical = importlib.import_module("coherence.measurement.report")
        assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
        for name in canonical.__dict__["__all__"]:
            assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_validation_module_entrypoint_forwards_to_canonical_cli():
    with _isolated_legacy_import("factory.validation.__main__"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            legacy = importlib.import_module("factory.validation.__main__")

        assert any("factory.validation" in str(item.message) for item in caught)
        assert legacy.main.__module__ == "coherence.measurement.cli"
