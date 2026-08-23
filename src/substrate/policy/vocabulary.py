"""Profile vocabulary: seven policy dimensions, presets, and the three-level
override resolution the guide's precedence rule describes (artifact/requirement
> feature/bundle > path/component > project default). Pure and repo-root-only
-- this module never imports coherence.trace; feature/bundle-level resolution
that needs the trace graph lives in `coherence.policy.compiler`.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

import frontmatter
import yaml

from substrate.validators.schema import SCHEMA_DIR, validate

DIMENSIONS = (
    "maturity", "consequence", "reversibility", "volatility",
    "verification_cost", "exposure", "collaboration",
)

# Every preset name the schema accepts. Only COMPILED_PRESETS actually compile
# obligations (D16) -- exploration/product are declared but untested until a
# real use case needs them.
KNOWN_PRESETS = ("exploration", "prototype", "product", "high_assurance")
COMPILED_PRESETS = ("prototype", "high_assurance")

DEFAULT_PRESET = "prototype"

_CONFIG_REL = (".factory", "factory.yaml")
_PROFILE_OVERRIDES_REL = (".factory", "profile.yaml")
_PROFILE_SCHEMA = SCHEMA_DIR / "profile.schema.json"


class UncompiledPresetError(ValueError):
    """A profile names a real preset (in KNOWN_PRESETS) that is not yet compiled."""


class InvalidProfileError(ValueError):
    """A profile string is not even a known preset name (contrast
    UncompiledPresetError: a REAL, known-but-uncompiled preset like
    `exploration`). Raised here, in substrate, at resolution time -- a
    configuration error, never a silent fallback (spec §13, guide §9.3)."""


class ProfileConflictError(ValueError):
    """Two path/component overrides of equal specificity disagree (never silently ordered)."""


def _validate_profile_value(value: str, *, source: str) -> str:
    errors = validate({"profile": value}, _PROFILE_SCHEMA)
    if errors:
        raise InvalidProfileError(
            f"{source}: {value!r} is not a known preset (have {KNOWN_PRESETS}): {'; '.join(errors)}"
        )
    return value


def project_default_profile(root: Path) -> str:
    path = root.joinpath(*_CONFIG_REL)
    if not path.exists():
        return DEFAULT_PRESET
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    value = str(data.get("profile") or DEFAULT_PRESET)
    return _validate_profile_value(value, source=f"{path}: profile")


def _path_overrides(root: Path) -> list[tuple[str, str]]:
    path = root.joinpath(*_PROFILE_OVERRIDES_REL)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        (
            str(entry["path"]),
            _validate_profile_value(
                str(entry["profile"]), source=f"{path}: overrides[{i}].profile"
            ),
        )
        for i, entry in enumerate(data.get("overrides") or [])
    ]


def _specificity(glob: str) -> int:
    return len([p for p in glob.split("/") if p])


def path_override_profile(root: Path, rel_path: str) -> str | None:
    """Most-specific matching path/component override, or None.

    Ties in specificity between overrides naming DIFFERENT profiles raise
    ProfileConflictError rather than picking one arbitrarily.
    """
    matches = [(g, p) for g, p in _path_overrides(root) if fnmatch.fnmatch(rel_path, g)]
    if not matches:
        return None
    best_spec = max(_specificity(g) for g, _ in matches)
    best = [(g, p) for g, p in matches if _specificity(g) == best_spec]
    profiles = {p for _, p in best}
    if len(profiles) > 1:
        raise ProfileConflictError(
            f"{rel_path}: equal-specificity path overrides disagree: {sorted(profiles)}"
        )
    return best[0][1]


def artifact_profile_override(path: Path) -> str | None:
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError):
        return None
    value = post.metadata.get("profile")
    if not value:
        return None
    return _validate_profile_value(str(value), source=f"{path}: profile")
