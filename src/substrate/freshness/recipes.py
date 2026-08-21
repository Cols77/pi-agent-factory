"""Declarative freshness recipes and their deterministic compiler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Protocol, Self, cast


SUPPORTED_RECIPE_SCHEMA = 1


class ResolutionClass(str, Enum):
    """Authority class controlling how a stale output may be resolved."""

    derived_auto = "derived_auto"
    repeatable_policy = "repeatable_policy"
    authoritative_gate = "authoritative_gate"
    provenance_blocked = "provenance_blocked"


class Fingerprinter(Protocol):
    """Callable used to calculate recipe input fingerprints."""

    def __call__(self, inputs: Sequence[object]) -> object: ...


class Resolver(Protocol):
    """Callable used to resolve a stale recipe output."""

    def __call__(self, recipe: FreshnessRecipe, candidate: object) -> object: ...


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value


def _reject_unknown_fields(raw: Mapping[object, object], allowed: set[str], context: str) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        paths = ", ".join(f"{context}.{field}" for field in unknown)
        raise ValueError(f"{context} contains unknown field(s): {paths}")


def _required(raw: Mapping[str, object], field: str, context: str) -> object:
    if field not in raw:
        raise ValueError(f"{context}.{field} is required")
    return raw[field]


def _callable(value: object, field: str) -> Fingerprinter | Resolver:
    if not callable(value):
        raise TypeError(f"{field} must be callable")
    return cast(Fingerprinter | Resolver, value)


class FingerprinterRegistry:
    """Explicit name-to-fingerprinter mapping owned by the composition boundary."""

    def __init__(self, fingerprinters: Mapping[str, object] | None = None) -> None:
        self._by_name: dict[str, Fingerprinter] = {}
        if fingerprinters is not None:
            for name, fingerprinter in fingerprinters.items():
                self.register(name, cast(Fingerprinter, _callable(fingerprinter, "fingerprinter")))

    def register(self, name: str, fingerprinter: Fingerprinter) -> None:
        _nonblank(name, "fingerprinter name")
        _callable(fingerprinter, "fingerprinter")
        if name in self._by_name:
            raise ValueError(f"fingerprinter already registered: {name}")
        self._by_name[name] = fingerprinter

    def lookup(self, name: str) -> Fingerprinter | None:
        return self._by_name.get(name)

    def __getitem__(self, name: str) -> Fingerprinter:
        return self._by_name[name]

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name)


class ResolverRegistry:
    """Explicit name-to-resolver mapping owned by the composition boundary."""

    def __init__(self, resolvers: Mapping[str, object] | None = None) -> None:
        self._by_name: dict[str, Resolver] = {}
        if resolvers is not None:
            for name, resolver in resolvers.items():
                self.register(name, cast(Resolver, _callable(resolver, "resolver")))

    def register(self, name: str, resolver: Resolver) -> None:
        _nonblank(name, "resolver name")
        _callable(resolver, "resolver")
        if name in self._by_name:
            raise ValueError(f"resolver already registered: {name}")
        self._by_name[name] = resolver

    def lookup(self, name: str) -> Resolver | None:
        return self._by_name.get(name)

    def __getitem__(self, name: str) -> Resolver:
        return self._by_name[name]

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name)


@dataclass(frozen=True)
class FreshnessLimits:
    """Resource bounds declared for one freshness resolution attempt."""

    attempts: int
    timeout_s: Real

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("limits.attempts must be an integer")
        if self.attempts < 1:
            raise ValueError("limits.attempts must be positive")
        if isinstance(self.timeout_s, bool) or not isinstance(self.timeout_s, Real):
            raise TypeError("limits.timeout_s must be a number")
        if not isfinite(float(self.timeout_s)) or self.timeout_s <= 0:
            raise ValueError("limits.timeout_s must be positive and finite")

    @classmethod
    def from_dict(cls, data: Mapping[object, object]) -> Self:
        _reject_unknown_fields(data, {"attempts", "timeout_s"}, "limits")
        raw = cast(Mapping[str, object], data)
        attempts = _required(raw, "attempts", "limits")
        timeout_s = _required(raw, "timeout_s", "limits")
        return cls(attempts=attempts, timeout_s=timeout_s)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, int | Real]:
        return {"attempts": self.attempts, "timeout_s": self.timeout_s}


@dataclass(frozen=True)
class FreshnessRecipe:
    """Validated declaration of one freshness-producing output."""

    schema: int
    output_kind: str
    inputs: tuple[str, ...]
    fingerprinter: str
    resolver: str
    resolution_class: ResolutionClass
    limits: FreshnessLimits

    def __post_init__(self) -> None:
        if isinstance(self.schema, bool) or not isinstance(self.schema, int):
            raise TypeError("schema must be an integer")
        _nonblank(self.output_kind, "output_kind")
        if isinstance(self.inputs, (str, bytes)) or not isinstance(self.inputs, Sequence):
            raise TypeError("inputs must be a sequence of selectors")
        selectors: list[str] = []
        for index, selector in enumerate(self.inputs):
            selectors.append(_nonblank(selector, f"inputs[{index}]"))
        object.__setattr__(self, "inputs", tuple(selectors))
        _nonblank(self.fingerprinter, "fingerprinter")
        _nonblank(self.resolver, "resolver")

        resolution_class = self.resolution_class
        if isinstance(resolution_class, str) and not isinstance(resolution_class, ResolutionClass):
            try:
                resolution_class = ResolutionClass(resolution_class)
            except ValueError as exc:
                raise ValueError(f"resolution_class is invalid: {resolution_class!r}") from exc
            object.__setattr__(self, "resolution_class", resolution_class)
        elif not isinstance(resolution_class, ResolutionClass):
            raise TypeError("resolution_class must be a ResolutionClass")

        if isinstance(self.limits, Mapping):
            object.__setattr__(self, "limits", FreshnessLimits.from_dict(self.limits))
        elif not isinstance(self.limits, FreshnessLimits):
            raise TypeError("limits must be a FreshnessLimits mapping")

    @classmethod
    def from_dict(cls, data: Mapping[object, object]) -> Self:
        allowed = {
            "schema",
            "output_kind",
            "inputs",
            "fingerprinter",
            "resolver",
            "resolution_class",
            "limits",
        }
        _reject_unknown_fields(data, allowed, "recipe")
        raw = cast(Mapping[str, object], data)
        return cls(
            schema=_required(raw, "schema", "recipe"),  # type: ignore[arg-type]
            output_kind=_required(raw, "output_kind", "recipe"),  # type: ignore[arg-type]
            inputs=_required(raw, "inputs", "recipe"),  # type: ignore[arg-type]
            fingerprinter=_required(raw, "fingerprinter", "recipe"),  # type: ignore[arg-type]
            resolver=_required(raw, "resolver", "recipe"),  # type: ignore[arg-type]
            resolution_class=_required(raw, "resolution_class", "recipe"),  # type: ignore[arg-type]
            limits=_required(raw, "limits", "recipe"),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "output_kind": self.output_kind,
            "inputs": list(self.inputs),
            "fingerprinter": self.fingerprinter,
            "resolver": self.resolver,
            "resolution_class": self.resolution_class.value,
            "limits": self.limits.to_dict(),
        }


@dataclass(frozen=True)
class CompiledRecipes:
    """Recipes ordered by dependencies with the registries used by their names."""

    recipes: tuple[FreshnessRecipe, ...]
    order: tuple[str, ...]
    fingerprinters: FingerprinterRegistry
    resolvers: ResolverRegistry

    @property
    def topological_order(self) -> tuple[str, ...]:
        return self.order

    @property
    def ordered(self) -> tuple[FreshnessRecipe, ...]:
        return self.recipes

    @property
    def ordered_recipes(self) -> tuple[FreshnessRecipe, ...]:
        return self.recipes

    @property
    def recipes_by_output_kind(self) -> Mapping[str, FreshnessRecipe]:
        return {recipe.output_kind: recipe for recipe in self.recipes}

    def recipe_for(self, output_kind: str) -> FreshnessRecipe:
        for recipe in self.recipes:
            if recipe.output_kind == output_kind:
                return recipe
        raise KeyError(output_kind)

    def __getitem__(self, output_kind: str) -> FreshnessRecipe:
        return self.recipe_for(output_kind)


def _registry(
    value: FingerprinterRegistry | ResolverRegistry | Mapping[str, object] | None,
    registry_type: type[FingerprinterRegistry] | type[ResolverRegistry],
    field: str,
) -> FingerprinterRegistry | ResolverRegistry:
    if value is None:
        return registry_type()
    if isinstance(value, registry_type):
        return value
    if isinstance(value, Mapping):
        return registry_type(value)
    raise TypeError(f"{field} must be a registry or mapping")


def _find_cycle(
    output_kinds: Sequence[str], dependencies: Mapping[str, tuple[str, ...]], remaining: set[str]
) -> tuple[str, ...]:
    position = {kind: index for index, kind in enumerate(output_kinds)}
    visiting: list[str] = []
    active: set[str] = set()

    def visit(kind: str) -> tuple[str, ...] | None:
        visiting.append(kind)
        active.add(kind)
        for dependency in sorted(dependencies[kind], key=position.__getitem__):
            if dependency not in remaining:
                continue
            if dependency in active:
                start = visiting.index(dependency)
                return tuple(visiting[start:] + [dependency])
            result = visit(dependency)
            if result is not None:
                return result
        active.remove(kind)
        visiting.pop()
        return None

    for kind in output_kinds:
        if kind in remaining and kind not in active:
            result = visit(kind)
            if result is not None:
                return result
    return tuple(sorted(remaining, key=position.__getitem__))


def compile_recipes(
    declarations: Sequence[Mapping[object, object] | FreshnessRecipe],
    fingerprinters: FingerprinterRegistry | Mapping[str, object] | None = None,
    resolvers: ResolverRegistry | Mapping[str, object] | None = None,
) -> CompiledRecipes:
    """Validate and dependency-order recipe declarations without executing them."""

    if isinstance(declarations, (str, bytes)) or not isinstance(declarations, Sequence):
        raise TypeError("recipe declarations must be a sequence")

    compiled_fingerprinters = cast(
        FingerprinterRegistry,
        _registry(fingerprinters, FingerprinterRegistry, "fingerprinters"),
    )
    compiled_resolvers = cast(
        ResolverRegistry,
        _registry(resolvers, ResolverRegistry, "resolvers"),
    )

    recipes: list[FreshnessRecipe] = []
    for index, declaration in enumerate(declarations):
        context = f"recipe[{index}]"
        if isinstance(declaration, FreshnessRecipe):
            recipe = declaration
        elif isinstance(declaration, Mapping):
            recipe = FreshnessRecipe.from_dict(declaration)
        else:
            raise TypeError(f"{context} must be a mapping or FreshnessRecipe")

        if recipe.schema != SUPPORTED_RECIPE_SCHEMA:
            raise ValueError(
                f"{context}.schema unsupported schema {recipe.schema!r}; "
                f"supported schema is {SUPPORTED_RECIPE_SCHEMA}"
            )
        if compiled_fingerprinters.lookup(recipe.fingerprinter) is None:
            raise ValueError(
                f"{context} '{recipe.output_kind}' references unknown fingerprinter "
                f"'{recipe.fingerprinter}'"
            )
        if compiled_resolvers.lookup(recipe.resolver) is None:
            raise ValueError(
                f"{context} '{recipe.output_kind}' references unknown resolver "
                f"'{recipe.resolver}'"
            )
        if recipe.limits.attempts != 1:
            raise ValueError(
                f"{context} '{recipe.output_kind}' limits.attempts must be 1, "
                f"got {recipe.limits.attempts}"
            )
        seen: set[str] = set()
        duplicate: str | None = None
        for selector in recipe.inputs:
            if selector in seen:
                duplicate = selector
                break
            seen.add(selector)
        if duplicate is not None:
            raise ValueError(
                f"{context} '{recipe.output_kind}' has duplicate input selector '{duplicate}'"
            )
        recipes.append(recipe)

    output_positions: dict[str, int] = {}
    for index, recipe in enumerate(recipes):
        previous = output_positions.get(recipe.output_kind)
        if previous is not None:
            raise ValueError(
                f"duplicate output_kind '{recipe.output_kind}' at recipe[{index}]; "
                f"already owned by recipe[{previous}]"
            )
        output_positions[recipe.output_kind] = index

    output_kinds = tuple(recipe.output_kind for recipe in recipes)
    output_set = set(output_kinds)
    dependencies: dict[str, tuple[str, ...]] = {}
    for recipe in recipes:
        if recipe.output_kind in recipe.inputs:
            raise ValueError(
                f"recipe '{recipe.output_kind}' input selector feeds its own output "
                f"'{recipe.output_kind}'"
            )
        dependencies[recipe.output_kind] = tuple(
            selector for selector in recipe.inputs if selector in output_set
        )

    indegree = {kind: len(recipe_dependencies) for kind, recipe_dependencies in dependencies.items()}
    dependents: dict[str, list[str]] = {kind: [] for kind in output_kinds}
    for kind, recipe_dependencies in dependencies.items():
        for dependency in recipe_dependencies:
            dependents[dependency].append(kind)

    ready = [kind for kind in output_kinds if indegree[kind] == 0]
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if len(order) != len(output_kinds):
        remaining = set(output_kinds) - set(order)
        cycle = _find_cycle(output_kinds, dependencies, remaining)
        raise ValueError(
            "cycle among output selectors: " + " -> ".join(cycle)
        )

    by_output_kind = {recipe.output_kind: recipe for recipe in recipes}
    ordered_recipes = tuple(by_output_kind[output_kind] for output_kind in order)
    return CompiledRecipes(
        recipes=ordered_recipes,
        order=tuple(order),
        fingerprinters=compiled_fingerprinters,
        resolvers=compiled_resolvers,
    )


__all__ = [
    "CompiledRecipes",
    "Fingerprinter",
    "FingerprinterRegistry",
    "FreshnessLimits",
    "FreshnessRecipe",
    "ResolutionClass",
    "Resolver",
    "ResolverRegistry",
    "compile_recipes",
]
