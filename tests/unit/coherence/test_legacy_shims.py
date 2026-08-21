from __future__ import annotations

import importlib
import sys
import warnings

import pytest

pytestmark = pytest.mark.unit


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
    sys.modules.pop(module_name, None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        legacy = importlib.import_module(module_name)

    assert any("factory.requirements" in str(item.message) for item in caught)
    canonical = importlib.import_module(canonical_name)
    assert legacy.__dict__["__all__"] == canonical.__dict__["__all__"]
    for name in canonical.__dict__["__all__"]:
        assert getattr(legacy, name) is getattr(canonical, name)


def test_legacy_module_entrypoint_forwards_to_canonical_cli():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        legacy = importlib.import_module("factory.requirements.__main__")

    assert any("factory.requirements" in str(item.message) for item in caught)
    assert legacy.main.__module__ == "coherence.register.cli"
