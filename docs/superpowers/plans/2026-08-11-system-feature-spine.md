# System Feature Spine (SP-A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the project a feature layer — bundles that can hold design decisions, measurable coverage over every artifact, a deterministic bundle ordering, and the authored map for `cool_physical_ai_project`, gated so it cannot rot.

**Architecture:** Python only, all of it inside `factory.system`. Two new modules (`adr.py`, `ordering.py`), one extended (`bundles.py`), one wired (`queries.py`), two new CLI subcommands. ADRs become frontmatter-carrying artifacts with id-based refs. Coverage is a pure function over existing loaders — `trace.model.load_nodes` for sr/task/spec/plan plus the new `load_adrs` — with no persisted index and no cache. SP-A ships no UI; SP-B renders this.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, `python-frontmatter`, `jsonschema` (Draft 2020-12), pytest.

**Spec:** `docs/superpowers/specs/2026-08-11-system-feature-spine-design.md`

## Two repositories

- **Tasks 1–7** land in `C:\coding\pi-agent-factory` (the factory).
- **Tasks 8–11** land in `C:\coding\cool_physical_ai_project` (the product). That repo consumes the factory as an editable path dependency (`pyproject.toml`: `pi-agent-factory = { path = "../pi-agent-factory", editable = true }`), so Tasks 1–7 are live there as soon as they are committed. No reinstall step is needed.

Commit in the repo you are working in. Never stage files from the other repo.

## Do not do these

- **Do not resolve the dangling `BR-002` reference.** `requirements/SR-001.md` carries `upstream: BR-002` and no `BR-*` file exists. That is a recorded known gap, resolved by SP-D when the business-requirement tier is restored. Unlinking it here would destroy the only recorded business intent in the repo.
- **Do not remove `sr:` from `list_scopes`.** Requirements stop being individually listed in SP-B, once bundles can carry navigation. Removing them now would leave the navigator with nothing to browse.
- **Do not bind any requirement.** Binding is per-bundle and on demand, in a later sub-project.
- **Do not touch `system-page.ts`, `docs-server.ts`, `index.ts`, or any TypeScript.** SP-A ships no UI.

## Global Constraints

- Python computes; nothing in this plan touches TypeScript, the browser, or `system-page.ts`.
- Claim class ∈ `recorded|derived|synthesized|missing`; freshness ∈ `fresh|stale|degraded|n/a`; `missing` ⟺ `n/a`, enforced in `SystemClaim.__post_init__` (`models.py:145`). No new claim classes.
- Freshness is content-based, never mtime-based.
- Scope refs are exact and case-sensitive. No fuzzy fallback.
- No derived index and no cache. Projections are computed on demand.
- Reuse existing loaders — `factory.trace.model`, `factory.requirements.register`, `factory.orchestrator.ledger`. No parallel parsing rules.
- A malformed artifact degrades one scope, never the whole listing (`bundles.py:164` establishes the pattern).
- Ordering tiebreaks are deterministic, never random (`propose.py:129` establishes the pattern).
- Test modules declare `pytestmark = pytest.mark.unit` or `pytest.mark.integration` at module level. `pyproject.toml:31` sets `addopts = "-m unit"`, so **integration runs must pass `-m 'unit or integration'` or they collect nothing and exit green.**
- `ruff` line-length is 100 (`pyproject.toml:34`).
- All existing tests stay green. Run `uv run python -m pytest -q` before every commit.

---

## File Structure

**Created in pi-agent-factory:**

| File | Responsibility |
|---|---|
| `src/factory/schemas/adr.schema.json` | The ADR frontmatter contract. |
| `src/factory/system/adr.py` | Parse one ADR; load all ADRs by id. Nothing else. |
| `src/factory/system/coverage.py` | Enumerate bundleable artifacts; compute the at-least-one-bundle split. |
| `src/factory/system/ordering.py` | Git-derived bundle recency and the resulting order. |
| `tests/unit/system/test_adr.py` | Task 1. |
| `tests/unit/system/test_coverage.py` | Task 4. |
| `tests/unit/system/test_ordering.py` | Task 7. |

**Modified in pi-agent-factory:**

| File | Change |
|---|---|
| `src/factory/system/bundles.py:33` | `_MEMBER_KINDS` gains `"adr"`. |
| `src/factory/system/queries.py:71` | `_SCOPE_KINDS` gains `"adr"`; `parse_scope_ref` message; `query_brief` adr branch; `list_scopes` emits adr. |
| `src/factory/system/cli.py` | `coverage` and `bundle` subcommands, renderers, dispatch. |
| `tests/unit/system/test_bundles.py` | Task 2 additions. |
| `tests/unit/system/test_queries.py` | Task 3 additions. |
| `tests/unit/system/test_cli.py` | Tasks 5, 6 additions. |

**Created/modified in cool_physical_ai_project:** `docs/adr/0001-*.md`, `docs/adr/0002-*.md` (migrated), `bundles/*.json` (the map), `docs/adr/0003-feature-bundle-map.md`, `.factory/factory.yaml`.

`coverage.py` is a separate module rather than an addition to `bundles.py`: `bundles.py` is about loading one declared file, coverage is about the whole artifact population. Keeping them apart stops `bundles.py` from growing a dependency on `factory.trace`.

---

## Task 1: ADR schema and parser

**Files:**
- Create: `src/factory/schemas/adr.schema.json`
- Create: `src/factory/system/adr.py`
- Test: `tests/unit/system/test_adr.py`

**Interfaces:**
- Consumes: `factory.validation.schema_validator.validate`, `SCHEMA_DIR` (`schema_validator.py:8,21`).
- Produces: `AdrDocument(id, path, title, status, superseded_by, sections, schema_errors)`; `parse_adr(path: Path) -> AdrDocument`; `load_adrs(repo_root: Path) -> dict[str, AdrDocument]`; `DuplicateAdrIdError`. Tasks 3 and 4 depend on these exact names.

- [ ] **Step 1: Write the schema**

Create `src/factory/schemas/adr.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://factory.local/schemas/adr.schema.json",
  "title": "Architecture decision record frontmatter",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "title", "status"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^ADR-[0-9]{4}$",
      "description": "Stable identity. Bundle members and scope refs use this, never the filename, so a file may be renamed for readability without breaking refs."
    },
    "title": {"type": "string", "minLength": 1},
    "status": {"enum": ["proposed", "accepted", "superseded"]},
    "superseded_by": {
      "type": ["string", "null"],
      "pattern": "^ADR-[0-9]{4}$",
      "description": "Required to be a real ADR id when status is superseded; null otherwise."
    }
  },
  "allOf": [
    {
      "if": {"properties": {"status": {"const": "superseded"}}, "required": ["status"]},
      "then": {"required": ["superseded_by"], "properties": {"superseded_by": {"type": "string"}}}
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/system/test_adr.py`:

```python
"""Tests for factory.system.adr: ADRs as structured artifacts.

An ADR carries machine-readable identity in frontmatter and prose in the
body. Identity is the `id`, never the filename, so a file can be renamed
without breaking every bundle that references it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.system.adr import AdrDocument, DuplicateAdrIdError, load_adrs, parse_adr

pytestmark = pytest.mark.unit


def _write_adr(adr_dir: Path, filename: str, text: str) -> Path:
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


_WELL_FORMED = """---
id: ADR-0001
title: Evolve the Existing Packages Through a Typed Contract Spine
status: accepted
superseded_by: null
---

## Decision
Keep `src/drone` and `src/sim`.

## Consequences
No parallel `src/paad` tree exists.
"""


def test_well_formed_adr_parses_identity_status_and_sections(tmp_path):
    path = _write_adr(tmp_path / "docs" / "adr", "0001-contract-spine.md", _WELL_FORMED)

    doc = parse_adr(path)

    assert doc.id == "ADR-0001"
    assert doc.title == "Evolve the Existing Packages Through a Typed Contract Spine"
    assert doc.status == "accepted"
    assert doc.superseded_by is None
    assert doc.schema_errors == []
    assert doc.sections == [
        ("Decision", "Keep `src/drone` and `src/sim`."),
        ("Consequences", "No parallel `src/paad` tree exists."),
    ]


def test_absent_frontmatter_yields_none_identity_and_reports_it(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0009-legacy.md",
        "# ADR-0009: Old Style\n\nStatus: Accepted\n\n## Decision\nSomething.\n",
    )

    doc = parse_adr(path)

    # Nothing is recovered from prose: identity is frontmatter or nothing.
    assert doc.id is None
    assert doc.title is None
    assert doc.status is None
    assert doc.schema_errors != []
    # The body still renders -- a bad header does not erase the document.
    assert doc.sections == [("Decision", "Something.")]


def test_schema_violation_is_reported_not_raised(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0010-bad-status.md",
        "---\nid: ADR-0010\ntitle: Bad\nstatus: rubbish\n---\n\n## Decision\nx.\n",
    )

    doc = parse_adr(path)

    assert doc.id == "ADR-0010"
    assert any("status" in err for err in doc.schema_errors)


def test_adr_with_no_sections_parses_with_an_empty_section_list(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0011-bare.md",
        "---\nid: ADR-0011\ntitle: Bare\nstatus: proposed\n---\n\nJust prose, no headings.\n",
    )

    doc = parse_adr(path)

    assert doc.sections == []


def test_unreadable_file_degrades_to_an_empty_document_rather_than_raising(tmp_path):
    missing = tmp_path / "docs" / "adr" / "0012-absent.md"

    doc = parse_adr(missing)

    assert doc.id is None
    assert doc.sections == []
    assert doc.schema_errors != []


def test_load_adrs_keys_by_id_not_filename(tmp_path):
    adr_dir = tmp_path / "docs" / "adr"
    _write_adr(adr_dir, "renamed-for-readability.md", _WELL_FORMED)

    adrs = load_adrs(tmp_path)

    assert list(adrs) == ["ADR-0001"]
    assert adrs["ADR-0001"].path.name == "renamed-for-readability.md"


def test_load_adrs_on_absent_directory_is_a_legitimate_empty_state(tmp_path):
    assert load_adrs(tmp_path) == {}


def test_duplicate_ids_fail_loudly(tmp_path):
    adr_dir = tmp_path / "docs" / "adr"
    _write_adr(adr_dir, "0001-first.md", _WELL_FORMED)
    _write_adr(adr_dir, "0001-copy.md", _WELL_FORMED)

    # An ambiguous id makes every ref to it meaningless, so this is the one
    # ADR failure that is not allowed to degrade quietly.
    with pytest.raises(DuplicateAdrIdError):
        load_adrs(tmp_path)


def test_an_adr_missing_its_frontmatter_is_skipped_by_load_adrs(tmp_path):
    adr_dir = tmp_path / "docs" / "adr"
    _write_adr(adr_dir, "0001-good.md", _WELL_FORMED)
    _write_adr(adr_dir, "0009-legacy.md", "# ADR-0009: Old Style\n\n## Decision\nx.\n")

    adrs = load_adrs(tmp_path)

    # It has no id, so there is no key to file it under. It is not an error
    # for the whole directory -- the good ADR still loads.
    assert list(adrs) == ["ADR-0001"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_adr.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'factory.system.adr'`.

- [ ] **Step 4: Write the implementation**

Create `src/factory/system/adr.py`:

```python
"""Architecture decision records as structured artifacts.

An ADR carries machine-readable identity in YAML frontmatter (validated
against `adr.schema.json`) and prose in the body. Identity is the `id`,
never the filename: bundle members and scope refs use `adr:ADR-0001`, which
matches the `sr:SR-001` / `task:T-059` convention and survives a file being
renamed for readability.

Nothing here recovers identity from prose. A document without frontmatter
has no id -- the parse reports that rather than guessing, which is the same
discipline `factory.system.bundles` applies to an unresolvable member ref.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "adr.schema.json"

_ADR_DIR_PARTS = ("docs", "adr")


class DuplicateAdrIdError(ValueError):
    """Two ADR files declare the same `id`.

    Unlike every other ADR failure, this one is raised rather than degraded.
    A ref like `adr:ADR-0001` must resolve to exactly one document; if two
    claim the id, every ref to it is meaningless and silently picking one
    would make bundle membership depend on directory iteration order.
    """


@dataclass(frozen=True)
class AdrDocument:
    """One parsed ADR. Absent fields are `None`, never a substituted default."""

    path: Path
    id: str | None = None
    title: str | None = None
    status: str | None = None
    superseded_by: str | None = None
    sections: list[tuple[str, str]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)


def _sections_of(body: str) -> list[tuple[str, str]]:
    """Split a body into `(## heading, prose)` pairs, in file order.

    Only `##` headings start a section. Text before the first one is
    preamble and belongs to no section, so it is dropped from `sections`
    rather than being attributed to a heading that did not introduce it.
    """
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(buffer).strip()))
            heading = line[3:].strip()
            buffer = []
        elif heading is not None:
            buffer.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(buffer).strip()))
    return sections


def parse_adr(path: Path) -> AdrDocument:
    """Parse one ADR file. Never raises: a bad document degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return AdrDocument(path=path, schema_errors=[f"{path}: unreadable ({exc})"])

    meta = dict(post.metadata)
    sections = _sections_of(post.content)

    if not meta:
        return AdrDocument(
            path=path,
            sections=sections,
            schema_errors=[f"{path}: no frontmatter; an ADR must declare id, title and status"],
        )

    errors = validate(meta, _SCHEMA)
    return AdrDocument(
        path=path,
        id=meta.get("id"),
        title=meta.get("title"),
        status=meta.get("status"),
        superseded_by=meta.get("superseded_by"),
        sections=sections,
        schema_errors=errors,
    )


def adr_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_ADR_DIR_PARTS)


def load_adrs(repo_root: Path) -> dict[str, AdrDocument]:
    """Load every ADR under `docs/adr/`, keyed by declared id.

    An absent directory is a legitimate state, not an error -- the same rule
    `bundles.list_bundles` applies to an absent bundles directory. A document
    with no declared id has no key to file itself under and is skipped
    without aborting the rest of the directory. Duplicate ids raise.
    """
    directory = adr_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, AdrDocument] = {}
    for path in sorted(directory.glob("*.md")):
        doc = parse_adr(path)
        if doc.id is None:
            continue
        if doc.id in loaded:
            raise DuplicateAdrIdError(
                f"ADR id {doc.id!r} is declared by both {loaded[doc.id].path} and {path}"
            )
        loaded[doc.id] = doc
    return loaded
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_adr.py -q
```

Expected: 9 passed.

- [ ] **Step 6: Run the full suite and lint**

```bash
uv run python -m pytest -q
uv run python -m ruff check .
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/factory/schemas/adr.schema.json src/factory/system/adr.py tests/unit/system/test_adr.py
git commit -m "feat(system): parse ADRs as structured artifacts with id-based identity"
```

---

## Task 2: `adr:` as a bundle member kind

**Files:**
- Modify: `src/factory/system/bundles.py:33` and its `_parse_member_ref` docstring at `:49`
- Test: `tests/unit/system/test_bundles.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_MEMBER_KINDS == ("spec", "plan", "task", "sr", "adr")`. Task 4 relies on `adr` being a legal member kind.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/system/test_bundles.py`:

```python
def test_adr_member_ref_resolves_by_id(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "shark-detection",
        {
            "id": "shark-detection",
            "label": "Shark detection",
            "members": ["adr:ADR-0001", "sr:SR-007"],
        },
    )

    bundle = load_bundle(bundles_dir, "shark-detection")

    assert [m.kind for m in bundle.members] == ["adr", "sr"]
    assert [m.ref for m in bundle.members] == ["adr:ADR-0001", "sr:SR-007"]
    assert bundle.unresolved == []


def test_adr_member_with_an_empty_identifier_does_not_resolve(tmp_path):
    bundles_dir = tmp_path / "bundles"
    _write_bundle(
        bundles_dir,
        "broken",
        {"id": "broken", "label": "Broken", "members": ["adr:"]},
    )

    bundle = load_bundle(bundles_dir, "broken")

    assert bundle.members == []
    assert [c.text for c in bundle.unresolved] == ["adr:"]
    assert bundle.unresolved[0].kind is ClaimClass.MISSING
    assert bundle.unresolved[0].freshness.state is FreshnessState.NA
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_bundles.py -q -k adr
```

Expected: `test_adr_member_ref_resolves_by_id` FAILS — `adr:ADR-0001` lands in `unresolved` because `adr` is not in `_MEMBER_KINDS`.

- [ ] **Step 3: Write the implementation**

In `src/factory/system/bundles.py`, replace line 32–33:

```python
# The only member kinds a bundle may declare (design §3.3, extended by SP-A).
# `adr` refs are id-based (`adr:ADR-0001`), matching `sr:`/`task:` and unlike
# `spec:`/`plan:`, which are repo-relative paths. Resolution to a file happens
# in the caller, never here -- this only parses the ref.
_MEMBER_KINDS = ("spec", "plan", "task", "sr", "adr")
```

And update the `_parse_member_ref` docstring at `:52-53`:

```python
    A member is well-formed only if it has a recognized `spec:`/`plan:`/
    `task:`/`sr:`/`adr:` prefix and a non-empty identifier after it. Anything
    else does not resolve (design §3.3) and is reported `missing` by the
    caller rather than raised, so one bad member never drops the whole bundle.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_bundles.py -q
```

Expected: all pass, including the pre-existing bundle tests.

- [ ] **Step 5: Run the full suite**

```bash
uv run python -m pytest -q && uv run python -m ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/bundles.py tests/unit/system/test_bundles.py
git commit -m "feat(system): accept adr: as a bundle member kind"
```

---

## Task 3: `adr:` as an openable scope with a Brief

**Files:**
- Modify: `src/factory/system/queries.py:71` (`_SCOPE_KINDS`), `:90` (`parse_scope_ref` docstring + message), `query_brief` at `:641`, `list_scopes` at `:1180`
- Test: `tests/unit/system/test_queries.py`

**Interfaces:**
- Consumes: `factory.system.adr.load_adrs`, `AdrDocument` (Task 1).
- Produces: `query_brief(repo_root, SystemScopeRef(kind="adr", ref="adr:ADR-0001"))` returns `{"scope": {...}, "claims": [...]}`; `list_scopes` emits `adr` scopes after bundles and before SRs.

An ADR renders **Brief only**. `query_matrix`, `query_timeline`, `query_story`, `query_reverse` and `query_guide` are not extended — an `adr:` scope passed to them raises `ScopeKindError`, which is the existing behaviour for a kind those queries do not handle.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/system/test_queries.py`:

```python
def _write_adr_fixture(repo_root, filename, text):
    directory = repo_root / "docs" / "adr"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text, encoding="utf-8")


_ADR_TEXT = """---
id: ADR-0001
title: Typed Contract Spine
status: accepted
superseded_by: null
---

## Decision
Keep the existing packages.

## Consequences
No parallel tree exists.
"""


def test_adr_is_a_legal_scope_ref(tmp_path):
    scope = parse_scope_ref("adr:ADR-0001")
    assert scope.kind == "adr"
    assert scope.ref == "adr:ADR-0001"


def test_adr_brief_renders_title_status_and_each_section_as_recorded_claims(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0001"))

    texts = [c["text"] for c in result["claims"]]
    assert texts == [
        "Typed Contract Spine",
        "status: accepted",
        "Decision: Keep the existing packages.",
        "Consequences: No parallel tree exists.",
    ]
    assert {c["kind"] for c in result["claims"]} == {"recorded"}
    assert {c["freshness"]["state"] for c in result["claims"]} == {"fresh"}


def test_adr_brief_cites_the_adr_file_with_a_content_hash(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0001"))

    citation = result["claims"][0]["citations"][0]
    assert citation["kind"] == "decision"
    assert citation["path"].endswith("0001-spine.md")
    assert citation["sha256"] is not None


def test_adr_brief_for_an_unknown_id_raises_scope_not_found(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    with pytest.raises(ScopeNotFoundError):
        query_brief(tmp_path, parse_scope_ref("adr:ADR-9999"))


def test_adr_brief_reports_schema_errors_as_a_missing_claim(tmp_path):
    _write_adr_fixture(
        tmp_path,
        "0002-bad.md",
        "---\nid: ADR-0002\ntitle: Bad\nstatus: rubbish\n---\n\n## Decision\nx.\n",
    )

    result = query_brief(tmp_path, parse_scope_ref("adr:ADR-0002"))

    missing = [c for c in result["claims"] if c["kind"] == "missing"]
    assert missing, "a schema violation must be visible, not silently tolerated"
    assert missing[0]["freshness"]["state"] == "n/a"


def test_list_scopes_includes_declared_adrs(tmp_path):
    _write_adr_fixture(tmp_path, "0001-spine.md", _ADR_TEXT)

    refs = [s.ref for s in list_scopes(tmp_path)]

    assert "adr:ADR-0001" in refs
```

Add `ScopeNotFoundError` and `list_scopes` to the module's existing import from `factory.system.queries` if they are not already imported.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_queries.py -q -k adr
```

Expected: `parse_scope_ref("adr:ADR-0001")` raises `ScopeKindError`.

- [ ] **Step 3: Extend the scope vocabulary**

In `src/factory/system/queries.py`, line 71:

```python
_SCOPE_KINDS = ("bundle", "sr", "task", "file", "adr")
```

And in `parse_scope_ref`, update the docstring and the error message:

```python
    """Parse a `--scope` CLI argument into a `SystemScopeRef`.

    `bundle:<id>`, `sr:<id>`, `task:<id>`, `file:<path>` and `adr:<id>` are
    legal top-level scopes. Anything else -- an unknown kind, a missing
    identifier, or a malformed string -- is rejected outright; there is no
    fuzzy fallback.
    """
    kind, sep, identifier = raw.partition(":")
    if not sep or kind not in _SCOPE_KINDS or not identifier:
        raise ScopeKindError(
            f"invalid scope ref: {raw!r} (expected bundle:<id>, sr:<id>, "
            f"task:<id>, file:<path> or adr:<id>)"
        )
    return SystemScopeRef(kind=kind, ref=raw)
```

- [ ] **Step 4: Add the ADR brief branch**

In `src/factory/system/queries.py`, add this helper above `query_brief` (line 641):

```python
def _adr_brief(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble an ADR's briefing: title, status, then each recorded section.

    An ADR renders Brief only -- it has no validation matrix, no runs and no
    reverse walk, and rendering five permanently-degraded tabs would teach a
    reader to ignore degraded states where they carry meaning.
    """
    adr_id = _scope_identifier(scope)
    adrs = adr_module.load_adrs(repo_root)
    doc = adrs.get(adr_id)
    if doc is None:
        raise ScopeNotFoundError(f"no ADR declares id {adr_id!r}")

    citation = SystemCitation(
        kind=CitationKind.DECISION,
        path=str(doc.path),
        sha256=_sha256_file(doc.path),
    )

    claims: list[SystemClaim] = []
    if doc.title is not None:
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=doc.title,
                freshness=_fresh(),
                citations=[citation],
            )
        )
    if doc.status is not None:
        status_text = f"status: {doc.status}"
        if doc.superseded_by:
            status_text = f"{status_text} (superseded by {doc.superseded_by})"
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=status_text,
                freshness=_fresh(),
                citations=[citation],
            )
        )
    for heading, body in doc.sections:
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=f"{heading}: {body}",
                freshness=_fresh(),
                citations=[citation],
            )
        )
    for error in doc.schema_errors:
        claims.append(_missing(error, "ADR frontmatter is absent or schema-invalid"))

    return {"scope": to_dict(scope), "claims": [to_dict(c) for c in claims]}
```

Add the import near the other `factory.system` imports at the top of `queries.py`:

```python
from factory.system import adr as adr_module
```

Then add the branch at the top of `query_brief`'s body, before the `if scope.kind == "bundle":` at line 650:

```python
    if scope.kind == "adr":
        return _adr_brief(repo_root, scope)
```

- [ ] **Step 5: Emit ADR scopes from `list_scopes`**

Replace `list_scopes` (line 1180):

```python
def list_scopes(repo_root: Path) -> list[SystemScopeRef]:
    """List every declared scope the browser can open (design SS5.2).

    Declared bundles, then declared ADRs, then SRs from the requirements
    register. A malformed bundle file degrades only itself
    (`bundles.list_bundles` already skips it); it never aborts the rest of
    the listing. An ADR with no declared id has no ref to be opened under and
    is likewise skipped by `load_adrs`.
    """
    scopes: list[SystemScopeRef] = []
    for bundle in bundles.list_bundles(_bundles_dir(repo_root)):
        scopes.append(SystemScopeRef(kind="bundle", ref=f"bundle:{bundle.id}"))
    for adr_id in adr_module.load_adrs(repo_root):
        scopes.append(SystemScopeRef(kind="adr", ref=f"adr:{adr_id}"))
    for req in register.load_register(_requirements_dir(repo_root)):
        scopes.append(SystemScopeRef(kind="sr", ref=f"sr:{req.id}"))
    return scopes
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_queries.py -q
```

Expected: all pass.

- [ ] **Step 7: Run the full suite**

```bash
uv run python -m pytest -q && uv run python -m ruff check .
```

Note: `list_scopes` now emits an extra kind. If any existing test asserts an exact scope list, update it to include the ADR scopes rather than weakening the assertion.

- [ ] **Step 8: Commit**

```bash
git add src/factory/system/queries.py tests/unit/system/test_queries.py
git commit -m "feat(system): open adr: as a scope with a brief-only page"
```

---

## Task 4: Bundle coverage

**Files:**
- Create: `src/factory/system/coverage.py`
- Test: `tests/unit/system/test_coverage.py`

**Interfaces:**
- Consumes: `factory.trace.model.load_nodes` (`model.py:86`), `factory.system.adr.load_adrs` (Task 1), `factory.system.bundles.list_bundles`.
- Produces: `KindCoverage(kind, total, bundled, unbundled)`; `Coverage(kinds, total, bundled, unbundled)`; `bundle_coverage(repo_root: Path) -> Coverage`; `member_target(repo_root: Path, member_ref: str) -> Path | None`. Tasks 5, 6 and 7 depend on these exact names.

**Critical detail — refs are not uniform.** `sr:`, `task:` and `adr:` are **id-based**; `spec:` and `plan:` are **repo-relative paths** (`queries.py:177` resolves them as `repo_root / identifier`). Task filenames carry slugs (`T-030-missionstate.md`), so an id cannot be turned into a path by string concatenation. Coverage therefore normalises **everything to a resolved `Path`** and compares paths — the only representation all five kinds share.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/system/test_coverage.py`:

```python
"""Tests for factory.system.coverage: which artifacts belong to no bundle.

Membership is many-to-many, so coverage asks only whether an artifact
belongs to *at least one* bundle. Counts are over the artifact set, never
summed across bundles -- summing would double-count anything shared between
two features and report more requirements than exist.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.system.coverage import bundle_coverage

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _sr(repo: Path, sr_id: str) -> None:
    (repo / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )


def _task(repo: Path, task_id: str, slug: str) -> None:
    (repo / "tasks" / f"{task_id}-{slug}.md").write_text(
        f"---\nid: {task_id}\ntitle: {slug}\nstatus: todo\n---\n", encoding="utf-8"
    )


def _spec(repo: Path, name: str) -> str:
    (repo / "docs" / "superpowers" / "specs" / name).write_text("# spec\n", encoding="utf-8")
    return f"docs/superpowers/specs/{name}"


def _plan(repo: Path, name: str) -> str:
    (repo / "docs" / "superpowers" / "plans" / name).write_text("# plan\n", encoding="utf-8")
    return f"docs/superpowers/plans/{name}"


def _adr(repo: Path, adr_id: str, filename: str) -> None:
    (repo / "docs" / "adr" / filename).write_text(
        f"---\nid: {adr_id}\ntitle: {adr_id}\nstatus: accepted\n---\n\n## Decision\nx.\n",
        encoding="utf-8",
    )


def _bundle(repo: Path, bundle_id: str, members: list[str]) -> None:
    (repo / "bundles" / f"{bundle_id}.json").write_text(
        json.dumps({"id": bundle_id, "label": bundle_id, "members": members}),
        encoding="utf-8",
    )


def _by_kind(coverage, kind):
    return next(k for k in coverage.kinds if k.kind == kind)


def test_every_kind_is_counted_including_adr(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _task(repo, "T-001", "thing")
    spec_ref = _spec(repo, "a-spec.md")
    plan_ref = _plan(repo, "a-plan.md")
    _adr(repo, "ADR-0001", "0001-decision.md")
    _bundle(
        repo,
        "everything",
        ["sr:SR-001", "task:T-001", f"spec:{spec_ref}", f"plan:{plan_ref}", "adr:ADR-0001"],
    )

    coverage = bundle_coverage(repo)

    assert coverage.total == 5
    assert coverage.bundled == 5
    assert coverage.unbundled == []
    for kind in ("sr", "task", "spec", "plan", "adr"):
        assert _by_kind(coverage, kind).bundled == 1


def test_an_artifact_in_two_bundles_is_counted_once(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "first", ["sr:SR-001"])
    _bundle(repo, "second", ["sr:SR-001"])

    coverage = bundle_coverage(repo)

    # Summing per-bundle counts would report 2 requirements where 1 exists.
    assert coverage.total == 1
    assert coverage.bundled == 1
    assert _by_kind(coverage, "sr").bundled == 1


def test_unbundled_artifacts_are_named_not_just_counted(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "partial", ["sr:SR-001"])

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 1
    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-002"]
    assert coverage.unbundled == ["sr:SR-002"]


def test_an_empty_bundle_contributes_nothing_and_is_not_an_error(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "forward-declared", [])

    coverage = bundle_coverage(repo)

    # Coverage counts artifacts, not bundles, so an empty bundle cannot
    # inflate it. Forward-declaring a feature stays legal.
    assert coverage.total == 1
    assert coverage.bundled == 0


def test_a_repo_with_no_bundles_reports_everything_unbundled(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _task(repo, "T-001", "thing")

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 0
    assert coverage.total == 2
    assert coverage.unbundled == ["sr:SR-001", "task:T-001"]


def test_a_member_naming_a_nonexistent_artifact_does_not_mark_anything_bundled(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "typo", ["sr:SR-999"])

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 0
    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-001"]


def test_unbundled_refs_are_in_deterministic_order(tmp_path):
    repo = _repo(tmp_path)
    for sr_id in ("SR-003", "SR-001", "SR-002"):
        _sr(repo, sr_id)

    coverage = bundle_coverage(repo)

    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-001", "sr:SR-002", "sr:SR-003"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_coverage.py -q
```

Expected: `ModuleNotFoundError: No module named 'factory.system.coverage'`.

- [ ] **Step 3: Write the implementation**

Create `src/factory/system/coverage.py`:

```python
"""Which artifacts belong to no bundle.

Membership is many-to-many, so the only question coverage asks is whether an
artifact belongs to *at least one* bundle. Counts are over the artifact set,
never summed across bundles: summing would double-count anything two features
share and report more requirements than the repo contains.

Refs are not uniform. `sr:`, `task:` and `adr:` are id-based; `spec:` and
`plan:` are repo-relative paths (`queries._resolve_spec_or_plan_member`). Task
filenames carry slugs, so an id cannot be concatenated into a path. Everything
is therefore normalised to a resolved `Path` -- the one representation all five
kinds share -- and compared on that.

Artifact enumeration reuses `factory.trace.model.load_nodes` rather than
re-globbing: a second set of parsing rules is how two surfaces start disagreeing
about what exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factory.system import adr as adr_module
from factory.system import bundles as bundles_module
from factory.trace import model as trace_model

# Ordered for stable reporting. `br` is deliberately absent: the BR tier is
# SP-D, and counting a kind with no artifacts would report a permanent 0/0.
_KINDS = ("sr", "task", "spec", "plan", "adr")


@dataclass(frozen=True)
class KindCoverage:
    kind: str
    total: int
    bundled: int
    unbundled: list[str]


@dataclass(frozen=True)
class Coverage:
    kinds: list[KindCoverage]
    total: int
    bundled: int
    unbundled: list[str]


def _artifacts(repo_root: Path) -> dict[str, list[tuple[str, Path]]]:
    """Every bundleable artifact as `{kind: [(ref, resolved_path), ...]}`.

    `ref` is the exact string a bundle member would have to declare to claim
    this artifact -- id-based for sr/task/adr, repo-relative path for
    spec/plan.
    """
    found: dict[str, list[tuple[str, Path]]] = {kind: [] for kind in _KINDS}
    for node in trace_model.load_nodes(repo_root):
        path = node.path.resolve()
        if node.kind in ("sr", "task"):
            found[node.kind].append((f"{node.kind}:{node.id}", path))
        elif node.kind in ("spec", "plan"):
            relative = node.path.relative_to(repo_root).as_posix()
            found[node.kind].append((f"{node.kind}:{relative}", path))
        # `br` nodes exist in trace but are not bundleable in SP-A.
    for adr_id, doc in adr_module.load_adrs(repo_root).items():
        found["adr"].append((f"adr:{adr_id}", doc.path.resolve()))
    for kind in found:
        found[kind].sort(key=lambda pair: pair[0])
    return found


def member_target(repo_root: Path, member_ref: str) -> Path | None:
    """Resolve a bundle member ref to the artifact path it names, or None.

    None means the ref is well-formed but names nothing that exists -- a typo
    in a bundle file, not a crash.
    """
    kind, _, identifier = member_ref.partition(":")
    if not identifier:
        return None
    if kind in ("spec", "plan"):
        path = repo_root / identifier
        return path.resolve() if path.is_file() else None
    if kind == "adr":
        doc = adr_module.load_adrs(repo_root).get(identifier)
        return doc.path.resolve() if doc is not None else None
    if kind in ("sr", "task"):
        for node in trace_model.load_nodes(repo_root):
            if node.kind == kind and node.id == identifier:
                return node.path.resolve()
        return None
    return None


def bundle_coverage(repo_root: Path) -> Coverage:
    """Per-kind bundled/unbundled split over every bundleable artifact."""
    artifacts = _artifacts(repo_root)

    claimed: set[Path] = set()
    for bundle in bundles_module.list_bundles(repo_root / "bundles"):
        for member in bundle.members:
            target = member_target(repo_root, member.ref)
            if target is not None:
                claimed.add(target)

    kinds: list[KindCoverage] = []
    all_unbundled: list[str] = []
    total = 0
    bundled = 0
    for kind in _KINDS:
        entries = artifacts[kind]
        unbundled = [ref for ref, path in entries if path not in claimed]
        kinds.append(
            KindCoverage(
                kind=kind,
                total=len(entries),
                bundled=len(entries) - len(unbundled),
                unbundled=unbundled,
            )
        )
        total += len(entries)
        bundled += len(entries) - len(unbundled)
        all_unbundled.extend(unbundled)

    return Coverage(kinds=kinds, total=total, bundled=bundled, unbundled=all_unbundled)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_coverage.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Run the full suite**

```bash
uv run python -m pytest -q && uv run python -m ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/coverage.py tests/unit/system/test_coverage.py
git commit -m "feat(system): compute at-least-one-bundle coverage over every artifact kind"
```

---

## Task 5: The `coverage` CLI and gate

**Files:**
- Modify: `src/factory/system/cli.py`
- Test: `tests/unit/system/test_cli.py`

**Interfaces:**
- Consumes: `factory.system.coverage.bundle_coverage`, `Coverage`, `KindCoverage` (Task 4).
- Produces: `cmd_coverage(repo_root: Path) -> dict`; the `coverage` subcommand with `--gate` and `--force`. Task 11 wires `--gate` into the product repo.

Exit codes: `0` when nothing is unbundled, or when `--gate` is absent, or when `--force` is passed. `2` when `--gate` is passed and anything is unbundled. `2` rather than `1` so a gate failure is distinguishable from the `1` that `_print_error` already returns for a malformed invocation.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/system/test_cli.py`:

```python
def _minimal_repo_with_one_unbundled_sr(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: One\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )
    return tmp_path


def test_coverage_json_reports_per_kind_totals(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    assert payload["bundled"] == 0
    assert payload["unbundled"] == ["sr:SR-001"]


def test_coverage_without_gate_exits_zero_even_when_artifacts_are_unbundled(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    assert main(["coverage", "--repo-root", str(repo)]) == 0


def test_coverage_gate_fails_and_names_every_unbundled_artifact(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--gate"])

    assert exit_code == 2
    assert "sr:SR-001" in capsys.readouterr().out


def test_coverage_gate_with_force_exits_zero_and_says_what_it_suppressed(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--gate", "--force"])

    out = capsys.readouterr().out
    assert exit_code == 0
    # A silent override would make the gate decorative.
    assert "forced" in out.lower()
    assert "sr:SR-001" in out


def test_coverage_gate_passes_when_everything_is_bundled(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)
    (repo / "bundles").mkdir()
    (repo / "bundles" / "all.json").write_text(
        json.dumps({"id": "all", "label": "All", "members": ["sr:SR-001"]}), encoding="utf-8"
    )

    assert main(["coverage", "--repo-root", str(repo), "--gate"]) == 0
```

Ensure `json` and `main` are imported at the top of `test_cli.py` (they already are for the existing tests).

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_cli.py -q -k coverage
```

Expected: `SystemExit: 2` from argparse — `coverage` is not a known subcommand.

- [ ] **Step 3: Add the command function and renderer**

In `src/factory/system/cli.py`, add the import:

```python
from factory.system.coverage import bundle_coverage
```

Add the command function after `cmd_scope` (line 88):

```python
def cmd_coverage(repo_root: Path) -> dict:
    return to_dict(bundle_coverage(repo_root))
```

Add the renderer after `_render_scope` (line 179):

```python
def _render_coverage(result: dict) -> str:
    lines = [f"bundle coverage: {result['bundled']}/{result['total']} artifacts"]
    for kind in result["kinds"]:
        lines.append(f"  {kind['kind']:<6} {kind['bundled']}/{kind['total']}")
    if result["unbundled"]:
        lines.append(f"unbundled ({len(result['unbundled'])}):")
        lines.extend(f"  - {ref}" for ref in result["unbundled"])
    return "\n".join(lines)
```

- [ ] **Step 4: Wire the subcommand**

In `main`, after the `sub.add_parser("scope", parents=[common])` line (211):

```python
    p_coverage = sub.add_parser("coverage", parents=[common])
    p_coverage.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero when any artifact belongs to no bundle",
    )
    p_coverage.add_argument(
        "--force",
        action="store_true",
        help="with --gate, report the failure but exit zero anyway",
    )
```

In the dispatch chain, replace the final `else:` branch (line 234) so `scope` stays explicit and `coverage` gets its own arm:

```python
        elif args.cmd == "coverage":
            result = cmd_coverage(args.repo_root)
            rendered = _render_coverage(result)
        else:
            result = cmd_scope(args.repo_root)
            rendered = _render_scope(result)
```

Then, immediately before the final `return 0` (line 248), add the gate:

```python
    # The gate runs after rendering so a failure still shows what failed.
    # `--force` is for manual invocation only: `.factory/factory.yaml` never
    # passes it, so a pipeline run cannot be silently forced.
    if args.cmd == "coverage" and args.gate and result["unbundled"]:
        if args.force:
            print(
                f"forced: suppressed {len(result['unbundled'])} unbundled artifact(s) listed above"
            )
            return 0
        return 2
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 6: Verify by hand against the real product repo**

```bash
cd C:/coding/cool_physical_ai_project && uv run python -m factory.system coverage
```

Expected: `bundle coverage: 7/237 artifacts` with 230 unbundled refs listed. If the totals differ, the artifact enumeration in Task 4 is wrong — stop and fix it before continuing.

- [ ] **Step 7: Run the full suite and commit**

```bash
cd C:/coding/pi-agent-factory
uv run python -m pytest -q && uv run python -m ruff check .
git add src/factory/system/cli.py tests/unit/system/test_cli.py
git commit -m "feat(system): add the coverage report and its forceable gate"
```

---

## Task 6: `bundle check --draft`

**Files:**
- Modify: `src/factory/system/cli.py`
- Test: `tests/unit/system/test_cli.py`

**Interfaces:**
- Consumes: `factory.system.coverage.bundle_coverage`, `member_target` (Task 4); `factory.system.bundles.list_bundles`.
- Produces: `cmd_bundle_check(repo_root: Path, draft_raw: str) -> dict` returning `{"id", "label", "members_total", "members_resolved", "unresolved", "coverage_before", "coverage_after", "overlaps", "id_matches_filename"}`. Task 9 uses this on every draft.

`--draft -` reads the draft from stdin. This tool verifies; it never proposes and never writes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/system/test_cli.py`:

```python
def _repo_with_two_srs(tmp_path):
    (tmp_path / "requirements").mkdir()
    for sr_id in ("SR-001", "SR-002"):
        (tmp_path / "requirements" / f"{sr_id}.md").write_text(
            f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
            encoding="utf-8",
        )
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _draft(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_bundle_check_reports_resolution_and_coverage_delta(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path, "draft.json", {"id": "one", "label": "One", "members": ["sr:SR-001"]}
    )

    exit_code = main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["members_total"] == 1
    assert payload["members_resolved"] == 1
    assert payload["unresolved"] == []
    assert payload["coverage_before"] == {"bundled": 0, "total": 2}
    assert payload["coverage_after"] == {"bundled": 1, "total": 2}


def test_bundle_check_names_unresolved_members(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path,
        "draft.json",
        {"id": "typo", "label": "Typo", "members": ["sr:SR-999", "adr:ADR-0404"]},
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["members_resolved"] == 0
    assert payload["unresolved"] == ["sr:SR-999", "adr:ADR-0404"]


def test_bundle_check_reports_overlap_with_an_existing_bundle(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    (repo / "bundles" / "existing.json").write_text(
        json.dumps({"id": "existing", "label": "Existing", "members": ["sr:SR-001"]}),
        encoding="utf-8",
    )
    draft = _draft(
        tmp_path, "draft.json", {"id": "new", "label": "New", "members": ["sr:SR-001"]}
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    # Multi-membership is legal, so this is information, not an error.
    assert payload["overlaps"] == [{"member": "sr:SR-001", "bundles": ["existing"]}]


def test_bundle_check_flags_an_id_that_does_not_match_its_filename(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path, "misnamed.json", {"id": "other", "label": "Other", "members": []}
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["id_matches_filename"] is False


def test_bundle_check_reads_a_draft_from_stdin(tmp_path, capsys, monkeypatch):
    repo = _repo_with_two_srs(tmp_path)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"id": "piped", "label": "Piped", "members": ["sr:SR-002"]})),
    )

    exit_code = main(["bundle", "check", "--draft", "-", "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["members_resolved"] == 1
    # There is no filename to compare against when the draft is piped.
    assert payload["id_matches_filename"] is None
```

Add `import io` to the top of `test_cli.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_cli.py -q -k bundle_check
```

Expected: `SystemExit: 2` — `bundle` is not a known subcommand.

- [ ] **Step 3: Write the command function**

In `src/factory/system/cli.py`, extend the coverage import:

```python
from factory.system.bundles import list_bundles
from factory.system.coverage import bundle_coverage, member_target
```

Add after `cmd_coverage`:

```python
def cmd_bundle_check(repo_root: Path, draft_raw: str) -> dict:
    """Answer four deterministic questions about a draft bundle.

    Resolution, coverage delta, overlap with existing bundles, and
    id/filename consistency. It proposes nothing and writes nothing -- the
    draft is judged, not generated. `--draft -` reads stdin, in which case
    there is no filename to check the id against and `id_matches_filename`
    is None rather than False.
    """
    if draft_raw == "-":
        raw = json.loads(sys.stdin.read())
        id_matches_filename: bool | None = None
    else:
        draft_path = Path(draft_raw)
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
        id_matches_filename = str(raw.get("id")) == draft_path.stem

    members = [str(m) for m in raw.get("members", [])]

    resolved: dict[str, Path] = {}
    unresolved: list[str] = []
    for ref in members:
        target = member_target(repo_root, ref)
        if target is None:
            unresolved.append(ref)
        else:
            resolved[ref] = target

    before = bundle_coverage(repo_root)
    already_claimed = {
        member_target(repo_root, m.ref)
        for bundle in list_bundles(repo_root / "bundles")
        for m in bundle.members
    }
    newly_claimed = {p for p in resolved.values() if p not in already_claimed}

    overlaps: list[dict] = []
    for ref, target in resolved.items():
        containing = [
            bundle.id
            for bundle in list_bundles(repo_root / "bundles")
            if any(member_target(repo_root, m.ref) == target for m in bundle.members)
        ]
        if containing:
            overlaps.append({"member": ref, "bundles": containing})

    return {
        "id": raw.get("id"),
        "label": raw.get("label"),
        "members_total": len(members),
        "members_resolved": len(resolved),
        "unresolved": unresolved,
        "coverage_before": {"bundled": before.bundled, "total": before.total},
        "coverage_after": {
            "bundled": before.bundled + len(newly_claimed),
            "total": before.total,
        },
        "overlaps": overlaps,
        "id_matches_filename": id_matches_filename,
    }
```

- [ ] **Step 4: Add the renderer**

```python
def _render_bundle_check(result: dict) -> str:
    before, after = result["coverage_before"], result["coverage_after"]
    lines = [
        f"draft: {result['id']} -- {result['label']}",
        f"  resolves       {result['members_resolved']}/{result['members_total']} members",
        f"  coverage       {before['bundled']}/{before['total']} -> "
        f"{after['bundled']}/{after['total']} bundled",
    ]
    for ref in result["unresolved"]:
        lines.append(f"  ! unresolved   {ref}")
    for overlap in result["overlaps"]:
        lines.append(f"  ~ also in      {overlap['member']} -> {', '.join(overlap['bundles'])}")
    if result["id_matches_filename"] is False:
        lines.append("  ! id does not match the draft filename (bundles must be named <id>.json)")
    return "\n".join(lines)
```

- [ ] **Step 5: Wire the nested subcommand**

After the `coverage` parser block in `main`:

```python
    p_bundle = sub.add_parser("bundle")
    bundle_sub = p_bundle.add_subparsers(dest="bundle_cmd", required=True)
    p_bundle_check = bundle_sub.add_parser("check", parents=[common])
    p_bundle_check.add_argument("--draft", required=True, help="path to a draft bundle, or - for stdin")
```

And in the dispatch chain, before the `coverage` arm:

```python
        elif args.cmd == "bundle":
            result = cmd_bundle_check(args.repo_root, args.draft)
            rendered = _render_bundle_check(result)
```

Guard the gate block so it does not read `args.gate` on a `bundle` invocation — it is already scoped by `args.cmd == "coverage"`, so no change is needed there.

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 7: Run the full suite and commit**

```bash
uv run python -m pytest -q && uv run python -m ruff check .
git add src/factory/system/cli.py tests/unit/system/test_cli.py
git commit -m "feat(system): add bundle check, a verifier for a drafted bundle"
```

---

## Task 7: Bundle ordering by git recency

**Files:**
- Create: `src/factory/system/ordering.py`
- Test: `tests/unit/system/test_ordering.py`

**Interfaces:**
- Consumes: `factory.system.bundles.list_bundles`, `factory.system.coverage.member_target` (Task 4).
- Produces: `RecencySource` Protocol with `last_commit_iso(repo_root: Path, paths: list[Path]) -> str | None`; `GitRecency`; `FixedRecency` (test double); `bundle_recency(repo_root, git) -> dict[str, str | None]`; `ordered_bundle_ids(repo_root, git) -> tuple[list[str], bool]` where the bool is `recency_available`. SP-B consumes `ordered_bundle_ids`.

Ordering is recency descending, then bundle id ascending. The tiebreak is deterministic and never random, mirroring `propose.py:129`. When git is unavailable every recency is `None`, the order falls back to id ascending, **and `recency_available` is `False`** so the caller can say so rather than presenting an arbitrary order as meaningful.

Only **member artifacts** count. Editing the bundle file itself does not move it: that is curation, and letting curation compete with development for the top of the list would make the sidebar a record of what was last tidied.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/system/test_ordering.py`:

```python
"""Tests for factory.system.ordering: which bundle is most recently touched.

Touched means a commit changed a *member artifact*. Editing the bundle file
is curation, not development, and must not float a dormant feature to the
top of the navigator's sidebar.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.system.ordering import FixedRecency, bundle_recency, ordered_bundle_ids

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _sr(repo: Path, sr_id: str) -> None:
    (repo / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )


def _bundle(repo: Path, bundle_id: str, members: list[str]) -> None:
    (repo / "bundles" / f"{bundle_id}.json").write_text(
        json.dumps({"id": bundle_id, "label": bundle_id, "members": members}),
        encoding="utf-8",
    )


def test_recency_is_the_most_recent_commit_touching_any_member(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "alpha", ["sr:SR-001", "sr:SR-002"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "requirements" / "SR-002.md").resolve(): "2026-08-09T00:00:00Z",
        }
    )

    assert bundle_recency(repo, git) == {"alpha": "2026-08-09T00:00:00Z"}


def test_bundles_are_ordered_most_recent_first(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "older", ["sr:SR-001"])
    _bundle(repo, "newer", ["sr:SR-002"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "requirements" / "SR-002.md").resolve(): "2026-08-09T00:00:00Z",
        }
    )

    order, available = ordered_bundle_ids(repo, git)

    assert order == ["newer", "older"]
    assert available is True


def test_equal_recency_breaks_ties_by_id_ascending(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "zulu", ["sr:SR-001"])
    _bundle(repo, "alpha", ["sr:SR-002"])
    same = "2026-08-05T00:00:00Z"
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): same,
            (repo / "requirements" / "SR-002.md").resolve(): same,
        }
    )

    order, _ = ordered_bundle_ids(repo, git)

    assert order == ["alpha", "zulu"]


def test_a_bundle_with_no_recency_sorts_after_every_dated_bundle(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "dated", ["sr:SR-001"])
    _bundle(repo, "empty", [])
    git = FixedRecency({(repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z"})

    order, _ = ordered_bundle_ids(repo, git)

    assert order == ["dated", "empty"]


def test_when_no_recency_is_available_order_falls_back_to_id_and_says_so(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "zulu", ["sr:SR-001"])
    _bundle(repo, "alpha", ["sr:SR-001"])
    git = FixedRecency({})

    order, available = ordered_bundle_ids(repo, git)

    assert order == ["alpha", "zulu"]
    # A silent fallback would make an arbitrary order look meaningful.
    assert available is False


def test_editing_the_bundle_file_does_not_affect_recency(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "alpha", ["sr:SR-001"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "bundles" / "alpha.json").resolve(): "2026-08-11T00:00:00Z",
        }
    )

    assert bundle_recency(repo, git) == {"alpha": "2026-08-01T00:00:00Z"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/system/test_ordering.py -q
```

Expected: `ModuleNotFoundError: No module named 'factory.system.ordering'`.

- [ ] **Step 3: Write the implementation**

Create `src/factory/system/ordering.py`:

```python
"""Which bundle was most recently touched, and the resulting order.

"Touched" means a commit changed one of the bundle's *member artifacts*.
Editing the bundle file itself is curation, not development; counting it
would make the navigator's sidebar a record of what was last tidied rather
than where work is happening.

Recency comes from git, never from filesystem mtime: mtime would reorder the
whole sidebar on a fresh clone, and the factory already bans mtime for
freshness. When git cannot answer, every recency is None and the caller is
told so -- an arbitrary order presented as meaningful is worse than an
admitted fallback.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.system import bundles as bundles_module
from factory.system.coverage import member_target


class RecencySource(Protocol):
    """Last-commit lookup. Mirrors `orchestrator.git_ops.GitOps`'s shape:
    a Protocol with a subprocess implementation and a test double, so no test
    needs a real repository."""

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None: ...


class GitRecency:
    """Real git. Returns the newest author date across `paths`, or None."""

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None:
        if not paths:
            return None
        try:
            completed = subprocess.run(
                ["git", "log", "-1", "--format=%aI", "--", *[str(p) for p in paths]],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        stamp = completed.stdout.strip()
        return stamp or None


@dataclass
class FixedRecency:
    """Test double: a path -> ISO timestamp table. No subprocess, no repo."""

    stamps: dict[Path, str]

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None:
        found = [self.stamps[p] for p in paths if p in self.stamps]
        return max(found) if found else None


def bundle_recency(repo_root: Path, git: RecencySource) -> dict[str, str | None]:
    """Newest member-artifact commit timestamp per bundle id, or None."""
    recency: dict[str, str | None] = {}
    for bundle in bundles_module.list_bundles(repo_root / "bundles"):
        targets = [
            target
            for target in (member_target(repo_root, m.ref) for m in bundle.members)
            if target is not None
        ]
        recency[bundle.id] = git.last_commit_iso(repo_root, targets)
    return recency


def ordered_bundle_ids(repo_root: Path, git: RecencySource) -> tuple[list[str], bool]:
    """Bundle ids most-recent-first, plus whether any recency was available.

    Undated bundles sort after every dated one. The tiebreak is id ascending
    -- deterministic, never random (`factory.trace.propose` line 129 sets the
    same rule for candidate ordering).
    """
    recency = bundle_recency(repo_root, git)
    available = any(stamp is not None for stamp in recency.values())
    order = sorted(
        recency,
        # `stamp is None` sorts False(0) before True(1), so dated bundles lead.
        # ISO-8601 strings compare correctly as text, so no parsing is needed;
        # negating is impossible on a string, hence the reverse-then-id shape.
        key=lambda bundle_id: (recency[bundle_id] is None, _descending(recency[bundle_id]), bundle_id),
    )
    return order, available


def _descending(stamp: str | None) -> tuple:
    """Sort key that reverses an ISO timestamp while keeping id ascending.

    `sorted(reverse=True)` would reverse the id tiebreak too, which would make
    two bundles committed in the same second order z-to-a. Inverting each
    character's code point reverses only this component.
    """
    if stamp is None:
        return ()
    return tuple(-ord(ch) for ch in stamp)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/system/test_ordering.py -q
```

Expected: 6 passed.

- [ ] **Step 5: Run the full suite and commit**

```bash
uv run python -m pytest -q && uv run python -m ruff check .
git add src/factory/system/ordering.py tests/unit/system/test_ordering.py
git commit -m "feat(system): order bundles by git recency of their member artifacts"
```

---

## Task 8: Migrate the two existing ADRs

**Repo: `C:\coding\cool_physical_ai_project`**

**Files:**
- Modify: `docs/adr/0001-paad-in-place-contract-spine.md`
- Modify: `docs/adr/0002-event-log-authority-and-replay.md`

**Interfaces:**
- Consumes: `adr.schema.json` (Task 1).
- Produces: two ADRs resolvable as `adr:ADR-0001` and `adr:ADR-0002`.

- [ ] **Step 1: Rewrite ADR-0001's header**

Replace the first three lines of `docs/adr/0001-paad-in-place-contract-spine.md`:

```markdown
# ADR-0001: Evolve the Existing Packages Through a Typed Contract Spine

Status: Accepted
```

with:

```markdown
---
id: ADR-0001
title: Evolve the Existing Packages Through a Typed Contract Spine
status: accepted
superseded_by: null
---
```

Leave `## Decision` and `## Consequences` and all prose untouched. The H1 is removed because the title now lives in frontmatter — two sources of truth for a title is exactly the ambiguity the migration exists to remove.

- [ ] **Step 2: Rewrite ADR-0002's header**

Same transformation on `docs/adr/0002-event-log-authority-and-replay.md`:

```markdown
---
id: ADR-0002
title: Make the Append-Only Event Log Authoritative
status: accepted
superseded_by: null
---
```

- [ ] **Step 3: Verify both parse and are openable**

```bash
cd C:/coding/cool_physical_ai_project
uv run python -m factory.system brief --scope adr:ADR-0001
uv run python -m factory.system brief --scope adr:ADR-0002
```

Expected: each prints the title, `status: accepted`, and one line per `##` section, all `[recorded] (fresh)`. No `[missing]` claims — a missing claim here means the frontmatter is wrong.

- [ ] **Step 4: Verify they appear as scopes**

```bash
uv run python -m factory.system scope | grep adr
```

Expected: `adr:ADR-0001` and `adr:ADR-0002`.

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0001-paad-in-place-contract-spine.md docs/adr/0002-event-log-authority-and-replay.md
git commit -m "refactor(adr): give ADRs structured frontmatter and stable ids"
```

---

## Task 9: Author the bundle map

**Repo: `C:\coding\cool_physical_ai_project`**

**Files:**
- Create: `bundles/*.json` — as many as the cuts require.

**Interfaces:**
- Consumes: `factory.system bundle check` (Task 6), `factory.system coverage` (Task 5).
- Produces: every one of the 237 artifacts in at least one bundle.

This task is an authoring pass, not a TDD cycle. The agent drafts, verifies, and writes; it does not ask for approval per bundle. It **stops and asks** only when a trigger fires.

**Mechanical triggers — decidable from `bundle check` output, always escalate:**

1. A member ref does not resolve (`unresolved` is non-empty).
2. An artifact would land in more than one bundle (`overlaps` is non-empty). Multi-membership is legal, but it is a deliberate claim that two features genuinely share an artifact.
3. An artifact remains unbundled once every bundle is drafted.
4. A bundle would be written empty. Legal for forward-declaration, never as a side effect of a placement pass.

**Judgment triggers — the agent's own call:**

5. It cannot state a one-sentence rationale for the cut that it believes is true.
6. An artifact could plausibly sit in another bundle already drafted.
7. The bundle has grown past the point where "read this to understand the feature" is still true.

Triggers 5–7 are not deterministic and cannot be made so. They are the judgment that was delegated when the ruling was "an agent proposes the cuts". Record every placement's rationale as you go — Task 10 depends on it.

- [ ] **Step 1: Read the source material**

Read all six specs in `docs/superpowers/specs/`. The bulk of the requirements (153 of 181) come from `2026-08-06-paad-mvp-system-specification-v0.1.md`, so its structure is the main input to the cuts.

- [ ] **Step 2: Record the starting baseline**

```bash
cd C:/coding/cool_physical_ai_project
uv run python -m factory.system coverage
```

Expected: `bundle coverage: 7/237 artifacts`, 230 unbundled. Write the number down; Step 6 checks it reached 237.

- [ ] **Step 3: Draft, verify, and write each bundle**

For each cut, in a loop:

```bash
# Write the draft to a scratch file, then:
uv run python -m factory.system bundle check --draft /path/to/draft.json
```

Read the output. If any mechanical trigger fires, stop and ask. Otherwise write the file to `bundles/<id>.json` — the filename stem must equal the `id`, or `load_bundle` raises `BundleIdMismatchError` (`bundles.py:36`).

A bundle file carries `id`, `label`, and `members` and nothing else — `system_bundle.schema.json` sets `additionalProperties: false`, so a rationale field will be rejected. The rationale goes in Task 10's ADR.

- [ ] **Step 4: Re-check the existing bundle**

`bundles/reactive-planner.json` already exists with 7 members. Decide whether it stands as-is or is re-cut alongside the new bundles, and record the decision. Do not silently leave it inconsistent with the map's other cuts.

- [ ] **Step 5: Handle the leftovers**

Run `coverage` again. Anything still unbundled is mechanical trigger 3 — stop and ask rather than inventing a `misc` bundle to absorb it. A catch-all bundle would make coverage pass while meaning nothing.

- [ ] **Step 6: Verify complete coverage**

```bash
uv run python -m factory.system coverage
```

Expected: `bundle coverage: 237/237 artifacts` and no `unbundled` section.

- [ ] **Step 7: Verify every bundle still loads**

```bash
uv run python -m factory.system scope
```

Expected: every bundle id listed, and **no** `! bundle load failed` lines.

- [ ] **Step 8: Commit**

```bash
git add bundles/
git commit -m "feat(bundles): author the feature map covering every artifact"
```

---

## Task 10: Record the map's reasoning as ADR-0003

**Repo: `C:\coding\cool_physical_ai_project`**

**Files:**
- Create: `docs/adr/0003-feature-bundle-map.md`

**Interfaces:**
- Consumes: the rationale recorded during Task 9.
- Produces: `adr:ADR-0003`, the compensating control for auto-approved placements.

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0003-feature-bundle-map.md`:

```markdown
---
id: ADR-0003
title: Feature Bundle Map
status: accepted
superseded_by: null
---

## Decision
<One paragraph: what a bundle means in this repo, and the shape of the cuts
that were made. State that membership is many-to-many and that bundles are
flat.>

## Rationale per bundle
<One entry per bundle: its id, and one sentence saying why those artifacts
belong together. This is the record that lets a later placement match
recorded reasoning instead of an invented taxonomy.>

## Escalations
<Every trigger that fired during the authoring pass and how it was resolved.
An empty section is a claim that nothing was ambiguous across 237 artifacts —
say so explicitly if that is what happened, rather than omitting the section.>

## Consequences
The coverage gate proves every artifact sits in some bundle. Nothing detects
an artifact sitting in the wrong bundle. Placements were auto-approved and
are reviewable here rather than at the time they were made.
```

Replace every `<...>` with real content. A placeholder left in this file is a plan failure.

- [ ] **Step 2: Add it to a bundle**

ADR-0003 is itself an artifact and must be bundled, or Task 11's gate fails. Add `adr:ADR-0003` to whichever bundle covers the traceability/evidence concern, then:

```bash
uv run python -m factory.system coverage
```

Expected: `238/238` — the total rose by one because the ADR is a new artifact.

- [ ] **Step 3: Verify it renders**

```bash
uv run python -m factory.system brief --scope adr:ADR-0003
```

Expected: title, status, and each `##` section as `[recorded] (fresh)`.

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0003-feature-bundle-map.md bundles/
git commit -m "docs(adr): record the feature bundle map and its rationale"
```

---

## Task 11: Wire the coverage gate

**Repo: `C:\coding\cool_physical_ai_project`**

**Files:**
- Modify: `.factory/factory.yaml`

**Interfaces:**
- Consumes: `factory.system coverage --gate` (Task 5).
- Produces: a `gates.full` that fails when any artifact is unbundled.

The gate is wired **last, on purpose**. Wired earlier it would fail on 230 artifacts and leave the product repo's full gate red for the whole of SP-A. Wired here it arrives green.

- [ ] **Step 1: Confirm the gate passes before wiring it**

```bash
cd C:/coding/cool_physical_ai_project
uv run python -m factory.system coverage --gate
echo "exit: $?"
```

Expected: `exit: 0`. If it is `2`, Task 9 or 10 is incomplete — fix that before wiring, never wire a red gate.

- [ ] **Step 2: Add the gate to `gates.full`**

In `.factory/factory.yaml`, append to the `full:` list, after the documentation gate:

```yaml
    # Deterministic feature-map gate: every requirement, task, spec, plan and
    # ADR must belong to at least one bundle. An unbundled artifact is not
    # merely untidy -- once the navigator lists bundles as the primary axis,
    # it is unreachable by browsing. --force is deliberately absent here: a
    # pipeline run must not be silently forceable.
    - { cmd: "{python} -m factory.system coverage --gate" }
```

- [ ] **Step 3: Verify the gate runs and passes in situ**

```bash
uv run python scripts/gates/all.py
```

Expected: all gates pass, including the new one.

- [ ] **Step 4: Verify the gate actually fails when it should**

Temporarily create an unbundled artifact and confirm the gate catches it:

```bash
cp requirements/SR-001.md requirements/SR-999.md
sed -i 's/id: SR-001/id: SR-999/' requirements/SR-999.md
uv run python -m factory.system coverage --gate; echo "exit: $?"
rm requirements/SR-999.md
```

Expected: `exit: 2` with `sr:SR-999` named. A gate never observed failing is not known to work.

- [ ] **Step 5: Commit**

```bash
git add .factory/factory.yaml
git commit -m "feat(gates): require every artifact to belong to a feature bundle"
```

---

## Definition of done

- `uv run python -m factory.system coverage` in the product repo reports every artifact bundled.
- `uv run python -m factory.system scope` lists bundles, ADRs and SRs with no load errors.
- `uv run python -m factory.system brief --scope adr:ADR-0003` renders.
- `uv run python -m pytest -q` and `uv run python -m ruff check .` are green in pi-agent-factory.
- `uv run python scripts/gates/all.py` is green in cool_physical_ai_project.
- SP-B can call `ordered_bundle_ids`, `bundle_coverage`, and `query_brief` on an `adr:` scope.
