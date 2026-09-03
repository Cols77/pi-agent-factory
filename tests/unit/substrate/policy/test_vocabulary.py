import pytest

from substrate.policy.vocabulary import (
    DEFAULT_PRESET,
    InvalidProfileError,
    ProfileConflictError,
    artifact_profile_override,
    path_override_profile,
    project_default_profile,
)

pytestmark = pytest.mark.unit


def test_project_default_absent_config(tmp_path):
    assert project_default_profile(tmp_path) == DEFAULT_PRESET == "prototype"


def test_project_default_from_config(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: high_assurance\n", encoding="utf-8")
    assert project_default_profile(tmp_path) == "high_assurance"


def test_artifact_override_from_frontmatter(tmp_path):
    (tmp_path / "requirements").mkdir()
    p = tmp_path / "requirements" / "SR-001.md"
    p.write_text("---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\nprofile: high_assurance\n---\n", encoding="utf-8")
    assert artifact_profile_override(p) == "high_assurance"


@pytest.mark.sr("SR-008")
def test_path_override_most_specific_wins(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/*'\n  profile: prototype\n"
        "- path: 'src/critical/*'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    assert path_override_profile(tmp_path, "src/critical/x.py") == "high_assurance"
    assert path_override_profile(tmp_path, "src/other/x.py") == "prototype"


@pytest.mark.sr("SR-008")
def test_path_override_equal_specificity_conflict_raises(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/a/*'\n  profile: prototype\n"
        "- path: 'src/b/*'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    # Both globs have equal specificity (2 segments) and would match a
    # differently-named file only if both patterns matched the same path --
    # construct that case directly:
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/*'\n  profile: prototype\n"
        "- path: '*/shared.py'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileConflictError):
        path_override_profile(tmp_path, "src/shared.py")


@pytest.mark.sr("SR-008")
def test_unknown_preset_name_raises_invalid_profile_error(tmp_path):
    # "nonsense" is not in KNOWN_PRESETS at all -- a configuration error, never
    # a silent fallback (spec §13, guide §9.3). Contrast UncompiledPresetError,
    # raised by coherence.policy.compiler for a REAL, known-but-uncompiled
    # preset like "exploration" -- that error lives in coherence, not here.
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: nonsense\n", encoding="utf-8")
    with pytest.raises(InvalidProfileError):
        project_default_profile(tmp_path)


@pytest.mark.sr("SR-008")
def test_invalid_profile_error_is_not_an_uncompiled_preset_error():
    from substrate.policy.vocabulary import InvalidProfileError, UncompiledPresetError

    assert not issubclass(InvalidProfileError, UncompiledPresetError)
    assert not issubclass(UncompiledPresetError, InvalidProfileError)
