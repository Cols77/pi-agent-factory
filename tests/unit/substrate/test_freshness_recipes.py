from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from substrate.freshness.recipes import (
    CompiledRecipes,
    FingerprinterRegistry,
    FreshnessLimits,
    FreshnessRecipe,
    ResolutionClass,
    ResolverRegistry,
    compile_recipes,
)


pytestmark = pytest.mark.unit


def _fingerprinter(_inputs: object) -> object:
    return "fingerprint"


def _resolver(_recipe: object, _candidate: object) -> object:
    return "resolved"


def _registries(
    *,
    fingerprinter: object = _fingerprinter,
    resolver: object = _resolver,
) -> tuple[FingerprinterRegistry, ResolverRegistry]:
    return (
        FingerprinterRegistry({"codemap/v1": fingerprinter}),
        ResolverRegistry({"codemap.ensure-fresh/v1": resolver}),
    )


def _declaration(
    output_kind: str = "code-map",
    *,
    inputs: list[str] | None = None,
    **overrides: object,
) -> dict[str, object]:
    declaration: dict[str, object] = {
        "schema": 1,
        "output_kind": output_kind,
        "inputs": inputs if inputs is not None else ["project-profile", "source-set"],
        "fingerprinter": "codemap/v1",
        "resolver": "codemap.ensure-fresh/v1",
        "resolution_class": "derived_auto",
        "limits": {"attempts": 1, "timeout_s": 30},
    }
    declaration.update(overrides)
    return declaration


def test_resolution_class_has_exact_authority_values() -> None:
    assert {member.value for member in ResolutionClass} == {
        "derived_auto",
        "repeatable_policy",
        "authoritative_gate",
        "provenance_blocked",
    }


def test_registry_supports_explicit_name_registration_and_lookup() -> None:
    fingerprinter = FingerprinterRegistry()
    resolver = ResolverRegistry()

    fingerprinter.register("codemap/v1", _fingerprinter)
    resolver.register("codemap.ensure-fresh/v1", _resolver)

    assert fingerprinter.lookup("codemap/v1") is _fingerprinter
    assert fingerprinter["codemap/v1"] is _fingerprinter
    assert resolver.lookup("codemap.ensure-fresh/v1") is _resolver
    assert resolver["codemap.ensure-fresh/v1"] is _resolver
    assert fingerprinter.lookup("missing/v1") is None
    assert resolver.lookup("missing/v1") is None

    with pytest.raises(ValueError, match="already registered"):
        fingerprinter.register("codemap/v1", _fingerprinter)
    with pytest.raises(ValueError, match="already registered"):
        resolver.register("codemap.ensure-fresh/v1", _resolver)


def test_recipe_models_preserve_declaration_values_and_limits() -> None:
    recipe = FreshnessRecipe.from_dict(_declaration())

    assert recipe == FreshnessRecipe(
        schema=1,
        output_kind="code-map",
        inputs=("project-profile", "source-set"),
        fingerprinter="codemap/v1",
        resolver="codemap.ensure-fresh/v1",
        resolution_class=ResolutionClass.derived_auto,
        limits=FreshnessLimits(attempts=1, timeout_s=30),
    )
    assert recipe.inputs == ("project-profile", "source-set")
    assert recipe.limits.attempts == 1
    assert recipe.limits.timeout_s == 30


def test_compile_returns_stable_topological_order_and_compiled_registries() -> None:
    fingerprinters, resolvers = _registries()
    declarations = [
        _declaration("projection", inputs=["trace-index"]),
        _declaration("trace-index", inputs=["code-map"]),
        _declaration("code-map", inputs=["source-set"]),
        _declaration("source-index", inputs=["source-set"]),
    ]

    compiled = compile_recipes(declarations, fingerprinters, resolvers)

    assert isinstance(compiled, CompiledRecipes)
    assert compiled.order == (
        "code-map",
        "source-index",
        "trace-index",
        "projection",
    )
    assert compiled.topological_order == compiled.order
    assert tuple(recipe.output_kind for recipe in compiled.ordered_recipes) == compiled.order
    assert tuple(recipe.output_kind for recipe in compiled.recipes) == compiled.order
    assert compiled.fingerprinters is fingerprinters
    assert compiled.resolvers is resolvers


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema", 2, "unsupported schema"),
        ("output_kind", "", "output_kind"),
        ("inputs", "source-set", "inputs"),
        ("fingerprinter", "", "fingerprinter"),
        ("resolver", "", "resolver"),
        ("resolution_class", "not-a-class", "resolution_class"),
        ("limits", {"attempts": 1, "timeout_s": 30, "extra": True}, "limits.extra"),
    ],
)
def test_compile_rejects_unsupported_or_invalid_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    fingerprinters, resolvers = _registries()
    declaration = _declaration(**{field: value})

    with pytest.raises((TypeError, ValueError), match=message):
        compile_recipes([declaration], fingerprinters, resolvers)


def test_compile_rejects_unknown_top_level_fields() -> None:
    fingerprinters, resolvers = _registries()
    declaration = _declaration(unexpected=True)

    with pytest.raises(ValueError, match="unexpected"):
        compile_recipes([declaration], fingerprinters, resolvers)


def test_compile_rejects_missing_required_fields() -> None:
    fingerprinters, resolvers = _registries()
    declaration = _declaration()
    del declaration["resolver"]

    with pytest.raises(ValueError, match="resolver"):
        compile_recipes([declaration], fingerprinters, resolvers)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fingerprinter", "unknown/v1", "unknown fingerprinter"),
        ("resolver", "unknown/v1", "unknown resolver"),
    ],
)
def test_compile_rejects_unknown_registered_implementations(
    field: str,
    value: object,
    message: str,
) -> None:
    fingerprinters, resolvers = _registries()
    declaration = _declaration(**{field: value})

    with pytest.raises(ValueError, match=message):
        compile_recipes([declaration], fingerprinters, resolvers)


def test_compile_rejects_duplicate_output_kind_ownership() -> None:
    fingerprinters, resolvers = _registries()

    with pytest.raises(ValueError, match="duplicate output_kind.*code-map"):
        compile_recipes(
            [_declaration("code-map"), _declaration("code-map", inputs=["parser-engine"])],
            fingerprinters,
            resolvers,
        )


def test_compile_rejects_duplicate_input_selectors() -> None:
    fingerprinters, resolvers = _registries()

    with pytest.raises(ValueError, match="duplicate input selector.*source-set"):
        compile_recipes(
            [_declaration(inputs=["source-set", "source-set"])],
            fingerprinters,
            resolvers,
        )


def test_compile_rejects_attempts_other_than_one() -> None:
    fingerprinters, resolvers = _registries()

    with pytest.raises(ValueError, match=r"limits\.attempts.*1"):
        compile_recipes(
            [_declaration(limits={"attempts": 2, "timeout_s": 30})],
            fingerprinters,
            resolvers,
        )


def test_compile_rejects_input_that_feeds_its_own_output() -> None:
    fingerprinters, resolvers = _registries()

    with pytest.raises(ValueError, match="feeds its own output.*code-map"):
        compile_recipes(
            [_declaration("code-map", inputs=["code-map"])],
            fingerprinters,
            resolvers,
        )


def test_compile_rejects_cycles_among_output_selectors() -> None:
    fingerprinters, resolvers = _registries()

    with pytest.raises(ValueError, match="cycle among output selectors"):
        compile_recipes(
            [
                _declaration("alpha", inputs=["beta"]),
                _declaration("beta", inputs=["alpha"]),
            ],
            fingerprinters,
            resolvers,
        )


def test_compiler_does_not_execute_implementations_read_files_or_mutate_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"fingerprinter": 0, "resolver": 0}

    def bomb_fingerprinter(_inputs: object) -> object:
        calls["fingerprinter"] += 1
        raise AssertionError("fingerprinter must not run during compilation")

    def bomb_resolver(_recipe: object, _candidate: object) -> object:
        calls["resolver"] += 1
        raise AssertionError("resolver must not run during compilation")

    fingerprinters, resolvers = _registries(
        fingerprinter=bomb_fingerprinter,
        resolver=bomb_resolver,
    )
    before_fingerprinters = fingerprinters.names
    before_resolvers = resolvers.names

    def fail_read_text(_self: Path, *_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("compiler must not read files")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    compiled = compile_recipes(
        [_declaration("code-map", inputs=["project-profile"])],
        fingerprinters,
        resolvers,
    )

    assert compiled.order == ("code-map",)
    assert calls == {"fingerprinter": 0, "resolver": 0}
    assert fingerprinters.names == before_fingerprinters
    assert resolvers.names == before_resolvers


def test_registry_constructors_do_not_mutate_source_mappings() -> None:
    fingerprinters: Mapping[str, object] = {"codemap/v1": _fingerprinter}
    resolvers: Mapping[str, object] = {"codemap.ensure-fresh/v1": _resolver}

    fp_registry = FingerprinterRegistry(fingerprinters)
    resolver_registry = ResolverRegistry(resolvers)

    assert dict(fingerprinters) == {"codemap/v1": _fingerprinter}
    assert dict(resolvers) == {"codemap.ensure-fresh/v1": _resolver}
    assert fp_registry.names == ("codemap/v1",)
    assert resolver_registry.names == ("codemap.ensure-fresh/v1",)
