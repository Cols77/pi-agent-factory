from __future__ import annotations

import json
import math
import re
from typing import Any

import frontmatter
import yaml

_FRONTMATTER_RE = re.compile(
    r"^-{3,}[ \t]*\r?\n(?P<header>.*?)(?:\r?\n)(?:-{3,}|\.\.\.)[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)
_JSON_FRONTMATTER_RE = re.compile(
    r"^\{[ \t]*\r?\n(?P<header>.*?)(?:\r?\n)\}[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number is not allowed")
    if isinstance(value, list):
        for item in value:
            _reject_nonfinite(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item)


def strict_json_loads(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite numbers."""
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    _reject_nonfinite(value)
    return value


def strict_json_dumps(value: object) -> str:
    """Serialize JSON without non-finite values or implementation-dependent spacing."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def strict_frontmatter_loads(text: str) -> frontmatter.Post:
    """Parse frontmatter after rejecting duplicate YAML mapping keys."""
    match = _FRONTMATTER_RE.match(text)
    if match is not None:
        metadata = yaml.load(match.group("header"), Loader=_UniqueKeyLoader)
        _reject_nonfinite(metadata)
        if metadata is not None and not isinstance(metadata, dict):
            raise yaml.YAMLError("frontmatter must be a mapping")
    else:
        json_match = _JSON_FRONTMATTER_RE.match(text)
        if json_match is not None:
            metadata = strict_json_loads("{\n" + json_match.group("header") + "\n}")
            if not isinstance(metadata, dict):
                raise ValueError("frontmatter must be a mapping")
    return frontmatter.loads(text)


__all__ = ["strict_frontmatter_loads", "strict_json_dumps", "strict_json_loads"]
