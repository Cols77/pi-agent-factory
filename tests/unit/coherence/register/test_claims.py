from __future__ import annotations

import pytest

from coherence.register.claims import (
    ClaimsConfig,
    check_commit,
    exempting_glob,
    glob_match,
    load_claims_config,
    parse_sr_trailer,
    registered_ids,
)

pytestmark = pytest.mark.unit

# Proposed SR-062: commit-level requirement attribution as evidence provenance.
# The `sr` markers below claim SR-062, which is NOT yet in `requirements/` --
# authoring it is gated on explicit human consent (SR-044). Until that consent
# lands the markers are a forward declaration, not a binding.


@pytest.mark.sr("SR-062")
def test_parses_a_single_sr_trailer():
    assert parse_sr_trailer("feat: thing\n\nSR: SR-050\n") == ("SR-050",)


@pytest.mark.sr("SR-062")
def test_parses_a_multi_sr_trailer_preserving_order():
    assert parse_sr_trailer("feat: thing\n\nSR: SR-050, SR-023\n") == ("SR-050", "SR-023")


@pytest.mark.sr("SR-062")
def test_a_message_with_no_trailer_yields_no_ids():
    assert parse_sr_trailer("feat: thing\n\nno trailer here\n") == ()


@pytest.mark.sr("SR-062")
def test_an_sr_mention_in_the_body_is_not_a_trailer():
    assert parse_sr_trailer("feat: relates to SR-050 somehow\n\nbody\n") == ()


@pytest.mark.sr("SR-062")
def test_double_star_glob_matches_nested_paths():
    assert glob_match("docs/**", "docs/a/b/c.md") is True


@pytest.mark.sr("SR-062")
def test_single_star_glob_does_not_cross_a_separator():
    assert glob_match("src/*.py", "src/a/b.py") is False


@pytest.mark.sr("SR-062")
def test_an_absent_config_file_yields_the_empty_default(tmp_path):
    assert load_claims_config(tmp_path) == ClaimsConfig(epoch=None, exempt=())


@pytest.mark.sr("SR-062")
def test_a_config_file_supplies_epoch_and_exempt_globs(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "trace-claims.yaml").write_text(
        'epoch: "abc123"\nexempt:\n  - "docs/**"\n  - "**/*.md"\n', encoding="utf-8"
    )
    config = load_claims_config(tmp_path)
    assert config.epoch == "abc123"
    assert config.exempt == ("docs/**", "**/*.md")


@pytest.mark.sr("SR-062")
def test_exempting_glob_reports_the_pattern_that_matched(tmp_path):
    config = ClaimsConfig(exempt=("docs/**", "**/*.md"))
    assert exempting_glob(config, "docs/a/b.md") == "docs/**"
    assert exempting_glob(config, "src/a.py") is None


# --- the commit-time check -------------------------------------------------


def _register(root, *sr_ids):
    """Create `requirements/` holding a file per id, the register's own naming
    convention -- `registered_ids` reads names, never frontmatter."""
    (root / "requirements").mkdir(exist_ok=True)
    for sr_id in sr_ids:
        (root / "requirements" / f"{sr_id}.md").write_text(
            f"---\nid: {sr_id}\n---\n", encoding="utf-8"
        )


@pytest.mark.sr("SR-062")
def test_registered_ids_reads_requirement_filenames(tmp_path):
    _register(tmp_path, "SR-050", "SR-023")
    assert registered_ids(tmp_path) == frozenset({"SR-050", "SR-023"})


@pytest.mark.sr("SR-062")
def test_a_commit_touching_only_exempt_paths_needs_no_trailer(tmp_path):
    _register(tmp_path)
    config = ClaimsConfig(exempt=("docs/**",))
    assert check_commit(tmp_path, "docs: tweak\n", ["docs/a.md"], config=config) == ()


@pytest.mark.sr("SR-062")
def test_a_commit_touching_a_non_exempt_path_without_a_trailer_is_rejected(tmp_path):
    _register(tmp_path)
    config = ClaimsConfig(exempt=("docs/**",))
    errors = check_commit(tmp_path, "feat: thing\n", ["src/a.py"], config=config)
    assert len(errors) == 1
    assert "src/a.py" in errors[0]


@pytest.mark.sr("SR-062")
def test_a_mixed_commit_needs_a_trailer_for_its_non_exempt_half(tmp_path):
    _register(tmp_path)
    config = ClaimsConfig(exempt=("docs/**",))
    errors = check_commit(
        tmp_path, "feat: thing\n", ["docs/a.md", "src/a.py"], config=config
    )
    assert len(errors) == 1
    assert "src/a.py" in errors[0]
    assert "docs/a.md" not in errors[0]


@pytest.mark.sr("SR-062")
def test_a_trailer_naming_an_unregistered_requirement_is_rejected(tmp_path):
    _register(tmp_path, "SR-050")
    errors = check_commit(
        tmp_path, "feat: thing\n\nSR: SR-999\n", ["src/a.py"], config=ClaimsConfig()
    )
    assert len(errors) == 1
    assert "SR-999" in errors[0]


@pytest.mark.sr("SR-062")
def test_a_malformed_id_is_rejected_before_the_register_is_consulted(tmp_path):
    _register(tmp_path, "SR-050")
    errors = check_commit(
        tmp_path, "feat: thing\n\nSR: banana\n", ["src/a.py"], config=ClaimsConfig()
    )
    assert len(errors) == 1
    assert "banana" in errors[0]


@pytest.mark.sr("SR-062")
def test_a_trailer_naming_a_registered_requirement_passes(tmp_path):
    _register(tmp_path, "SR-050")
    assert check_commit(
        tmp_path, "feat: thing\n\nSR: SR-050\n", ["src/a.py"], config=ClaimsConfig()
    ) == ()


@pytest.mark.sr("SR-062")
def test_a_multi_sr_trailer_passes_only_when_every_id_is_registered(tmp_path):
    _register(tmp_path, "SR-050")
    errors = check_commit(
        tmp_path, "feat: thing\n\nSR: SR-050, SR-023\n", ["src/a.py"], config=ClaimsConfig()
    )
    assert len(errors) == 1
    assert "SR-023" in errors[0]
    assert "SR-050" not in errors[0]


@pytest.mark.sr("SR-062")
def test_check_commit_falls_back_to_the_projects_own_config(tmp_path):
    """With no `config=` argument the check reads `.factory/trace-claims.yaml`
    itself, which is how the hook invokes it."""
    _register(tmp_path)
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "trace-claims.yaml").write_text(
        'exempt:\n  - "docs/**"\n', encoding="utf-8"
    )
    assert check_commit(tmp_path, "docs: x\n", ["docs/a.md"]) == ()
