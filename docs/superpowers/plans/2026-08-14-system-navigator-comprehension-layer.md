# System Navigator Comprehension Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/system` self-explanatory — every artifact reference carries its title and recorded description, every contract word carries a plain-English gloss and definition, and every gap names the command that closes it.

**Architecture:** Python gains three things: a ref-normalising label index (a new async endpoint), and two static tables (vocabulary, remediation) that are inlined into the page at render time rather than fetched. The browser gains one `refChip` helper, a card component, gloss-bearing badges, Next-step blocks, and a two-column workspace. The governing rule holds throughout: Python computes, the browser renders — the browser never parses a ref.

**Tech Stack:** Python 3 (`uv run python -m factory.system`), TypeScript with no framework, DOM assembled inline via `Function.prototype.toString()`, vitest + jsdom, Playwright behind `BROWSER_GATE=1`.

**Specs:** `docs/superpowers/specs/2026-08-14-system-navigator-comprehension-layer-design.md` (revision 2) and `…-comprehension-layer-visual-addendum.md`. Both are binding. Read both before Task 1.

## Global Constraints

- **The browser never parses, prefixes, or normalises a ref.** All ref resolution is `factory.system.labels.normalize_ref`.
- **No description is composed from multiple fields.** Every `description` is verbatim text from one named field, reported in `description_source`. If no such field exists, `description` is `null`.
- **No write actions.** The browser displays commands and copies them. It never executes one.
- **No new dependency:** no framework, build step, remote font, image, or icon package. Text glyphs only (`ⓘ`, `▌`).
- **No changes** to `system_response.schema.json`, `system_claim.schema.json`, `system_matrix_row.schema.json`, or `system_timeline_event.schema.json`.
- **Palette is fixed** to the tokens already in `system-shell.ts:78`. Gloss text uses `--text-muted` (`#91a8b0`), never `--text-dim` — `--text-dim` measures 3.83:1 on `--surface-raised` at 12 px and fails AA.
- **Renderers run inside a stringified IIFE.** Functions added to `clientSource()`'s array must be plain declarations that reference only siblings and preamble bindings — no imports, no closures over module scope.
- **Every state word stays visible as text.** Colour and border style never carry meaning alone.
- **Commit after every task.** Run `npm test` in `pi-ext/factory-watch` and `uv run pytest tests/unit/system` before each commit.

---

## File Structure

**Created:**
- `src/factory/system/labels.py` — ref normalisation + the label index projection.
- `src/factory/system/vocabulary.py` — the static term table.
- `src/factory/system/remediation.py` — the static state→command table.
- `tests/unit/system/test_labels.py`, `test_vocabulary.py`, `test_remediation.py`
- `pi-ext/factory-watch/src/system-comprehension.ts` — `refChip`, the card, bounded lists, Next-step block. Kept out of `system-renderers.ts` so that file keeps one responsibility.
- `pi-ext/factory-watch/test/system-comprehension.test.ts`

**Modified:**
- `src/factory/schemas/system_bundle.schema.json` — optional `description`.
- `src/factory/system/models.py` — `BundleDeclaration.description`.
- `src/factory/system/bundles.py` — parse `description`.
- `src/factory/system/health.py` — carry `description` on bundle rows.
- `src/factory/system/queries.py` — `query_traversal` emits canonical ref lists.
- `src/factory/system/cli.py` — `labels`, `vocabulary`, `remediation` subcommands.
- `pi-ext/factory-watch/src/system-cli.ts` — label types, `loadSystemLabelsAsync`, `SystemTraversal.requirement: string[]`.
- `pi-ext/factory-watch/src/docs-server.ts` — `/api/system/labels` route.
- `pi-ext/factory-watch/src/system-shell.ts` — preamble bindings, inlined tables, CSS, new renderers in `clientSource()`.
- `pi-ext/factory-watch/src/system-renderers.ts` — call `refChip` at each emission site.
- `pi-ext/factory-watch/src/system-bootstrap.ts` — fetch ordering, heading inversion, sidebar rows, traversal, first run, context rail.
- `pi-ext/factory-watch/test/system-browser-validation.test.ts` — new gate assertions.
- `tests/unit/system/_fixtures.py` — `write_bundle` gains `description`.

---

## Task 1: Ref normalisation

**Files:**
- Create: `src/factory/system/labels.py`
- Create: `tests/unit/system/test_labels.py`

**Interfaces:**
- Consumes: `factory.trace.model.load_nodes`, `factory.system.coverage.build_artifact_lookup`
- Produces: `normalize_ref(root: Path, raw: str) -> str | None`, `build_alias_map(root: Path) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/system/test_labels.py
from pathlib import Path

from factory.system.labels import build_alias_map, normalize_ref
from tests.unit.system import _fixtures


def test_normalize_bare_task_id(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path, "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "T-060") == "task:T-060"


def test_normalize_prefixed_task_ref_is_idempotent(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path, "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "task:T-060") == "task:T-060"


def test_normalize_spec_basename_resolves_to_path_form(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    canonical = "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    assert normalize_ref(tmp_path, "spec:2026-07-16-foo-design.md") == canonical
    assert normalize_ref(tmp_path, canonical) == canonical


def test_normalize_unresolvable_returns_none(tmp_path: Path) -> None:
    assert normalize_ref(tmp_path, "T-999") is None
    assert normalize_ref(tmp_path, "nonsense") is None


def test_alias_map_contains_basename_and_bare_forms(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    _fixtures.write_task(tmp_path, "T-060", title="Wire the governor")
    aliases = build_alias_map(tmp_path)
    assert aliases["spec:2026-07-16-foo-design.md"] == (
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    )
    assert aliases["T-060"] == "task:T-060"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.system.labels'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/factory/system/labels.py
"""Ref normalisation and the label index projection.

The repository carries two live spellings for document refs:
`trace/model.py:86` builds `spec:<basename>`, `system/coverage.py:70` builds
`spec:<repo-relative-path>`. `bundles.py:203` already documents that both
denote one file. This module is the single place that resolves either
spelling -- and bare ids like `T-060` -- to one canonical form.

The browser never parses a ref. It looks one up here.
"""
from __future__ import annotations

from pathlib import Path

from factory.trace import model as trace_model

# Kinds whose canonical id is the bare identifier. `spec`, `plan` and `file`
# use the repo-relative POSIX path instead, because their identity is the
# file, not a symbol.
_BARE_ID_KINDS = frozenset({"sr", "br", "task", "adr", "feat", "metric", "goal", "diag"})
_PATH_KINDS = frozenset({"spec", "plan"})


def _relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def canonical_ref(root: Path, node: trace_model.Node) -> str:
    if node.kind in _PATH_KINDS:
        return f"{node.kind}:{_relative_posix(root, root / node.path)}"
    return f"{node.kind}:{node.id}"


def build_alias_map(root: Path, nodes: list[trace_model.Node] | None = None) -> dict[str, str]:
    """Every non-canonical spelling encountered, mapped to its canonical ref.

    Includes the bare id, the `<kind>:<basename>` form the trace graph emits,
    and the canonical ref itself (so a lookup is one dict access either way).
    """
    if nodes is None:
        nodes = trace_model.load_nodes(root)
    aliases: dict[str, str] = {}
    for node in nodes:
        canonical = canonical_ref(root, node)
        aliases[canonical] = canonical
        aliases[node.id] = canonical
        aliases[f"{node.kind}:{node.id}"] = canonical
        if node.kind in _PATH_KINDS:
            aliases[f"{node.kind}:{Path(node.path).name}"] = canonical
    return aliases


def normalize_ref(
    root: Path, raw: str, aliases: dict[str, str] | None = None
) -> str | None:
    """Resolve a raw ref or bare id to its canonical form, or None.

    Never guesses: an input with no recorded artifact behind it returns None
    so the renderer can say so plainly.
    """
    if aliases is None:
        aliases = build_alias_map(root)
    return aliases.get(raw.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/system/test_labels.py -v`
Expected: PASS, 5 tests

Note: `_fixtures.write_spec` writes into `docs/superpowers/specs/`. If the assertion fails on the path, read `tests/unit/system/_fixtures.py:138` and use the directory it actually writes to — do not change the fixture.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/labels.py tests/unit/system/test_labels.py
git commit -m "feat(system): canonical ref normalisation for the label index"
```

---

## Task 2: Bundle description field

**Files:**
- Modify: `src/factory/schemas/system_bundle.schema.json`
- Modify: `src/factory/system/models.py:221-225`
- Modify: `src/factory/system/bundles.py:135-140`
- Modify: `src/factory/system/health.py` (bundle row dict)
- Modify: `tests/unit/system/_fixtures.py:73`
- Test: `tests/unit/system/test_bundles.py`

**Interfaces:**
- Produces: `BundleDeclaration.description: str | None`; `health` bundle rows gain `"description"`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/system/test_bundles.py
def test_bundle_description_is_parsed_when_present(tmp_path):
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    _fixtures.write_bundle(
        bundles_dir, "planner", "Reactive planner core", ["sr:SR-001"],
        description="The loop that turns observations into the next action.",
    )
    bundle = list_bundles(bundles_dir)[0]
    assert bundle.description == (
        "The loop that turns observations into the next action."
    )


def test_bundle_description_defaults_to_none(tmp_path):
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    _fixtures.write_bundle(bundles_dir, "planner", "Reactive planner core", ["sr:SR-001"])
    assert list_bundles(bundles_dir)[0].description is None


def test_bundle_description_over_280_chars_is_a_load_error(tmp_path):
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    _fixtures.write_bundle(
        bundles_dir, "planner", "Reactive planner core", ["sr:SR-001"],
        description="x" * 281,
    )
    errors = list_bundle_errors(bundles_dir)
    assert len(errors) == 1
    assert "description" in errors[0].error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_bundles.py -k description -v`
Expected: FAIL with `TypeError: write_bundle() got an unexpected keyword argument 'description'`

- [ ] **Step 3: Write minimal implementation**

`src/factory/schemas/system_bundle.schema.json` — add inside `properties`, after `label`:

```json
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 280,
      "description": "One short sentence stating WHAT the feature is -- an expansion of `label`, nothing more. Rationale for why artifacts were grouped this way belongs in an ADR, not here (see 2026-08-10-system-control-center-program-decomposition.md). The 280-character cap is a convention that keeps this field honest; it cannot enforce the distinction mechanically."
    },
```

`src/factory/system/models.py` — add to `BundleDeclaration`, after `label`:

```python
    description: str | None = None
```

Note: `members`, `unresolved` and `citation` have no defaults, so `description` must be declared **after** them, or given a default on all of them. Place `description: str | None = None` as the **last** field.

`src/factory/system/bundles.py` — in the `BundleDeclaration(...)` construction at line 135:

```python
    return BundleDeclaration(
        id=str(raw["id"]),
        label=str(raw["label"]),
        members=members,
        unresolved=unresolved,
        citation=citation,
        description=(str(raw["description"]) if raw.get("description") else None),
    )
```

`src/factory/system/health.py` — in the bundle row dict built around line 178, add:

```python
            "description": row.description,
```

and carry `description: str | None` through `BundleReadinessRow`, populated from
`bundle.description` at both construction sites (the empty-flags branch and the main
one).

`tests/unit/system/_fixtures.py:73`:

```python
def write_bundle(
    bundles_dir: Path,
    bundle_id: str,
    label: str,
    members: list[str],
    description: str | None = None,
) -> Path:
```

and include `"description": description` in the written payload only when
`description is not None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/system -v`
Expected: PASS, including the three new tests and every pre-existing bundle test

- [ ] **Step 5: Commit**

```bash
git add src/factory/schemas/system_bundle.schema.json src/factory/system/models.py src/factory/system/bundles.py src/factory/system/health.py tests/unit/system/
git commit -m "feat(system): optional bundle description field

Overrides the membership-only ruling on the user's explicit instruction of
2026-08-14; rationale still belongs in an ADR. Recorded in the design spec's
Component 5."
```

---

## Task 3: Label index projection

**Files:**
- Modify: `src/factory/system/labels.py`
- Modify: `src/factory/system/cli.py`
- Test: `tests/unit/system/test_labels.py`

**Interfaces:**
- Consumes: `normalize_ref`, `build_alias_map` (Task 1); `BundleDeclaration.description` (Task 2)
- Produces: `build_labels(root: Path) -> dict` and `factory.system labels --json`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/system/test_labels.py
from factory.system.labels import build_labels


def test_sr_description_is_the_statement(tmp_path):
    _fixtures.write_sr(tmp_path, "SR-121", title="Battery-aware return",
                       statement="The system shall return to base.")
    entry = build_labels(tmp_path)["labels"]["sr:SR-121"]
    assert entry["title"] == "Battery-aware return"
    assert entry["description"] == "The system shall return to base."
    assert entry["description_source"] == "statement"
    assert entry["scope_href"] == "/system?scope=sr%3ASR-121"


def test_task_has_no_description_but_carries_relations(tmp_path):
    _fixtures.write_task(tmp_path, "T-060", title="Wire the governor",
                         satisfies=["SR-121"])
    entry = build_labels(tmp_path)["labels"]["task:T-060"]
    assert entry["title"] == "Wire the governor"
    assert entry["description"] is None
    assert entry["description_source"] is None
    assert entry["relations"]["satisfies"] == ["sr:SR-121"]


def test_spec_is_not_an_openable_scope(tmp_path):
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    entry = build_labels(tmp_path)["labels"][
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    ]
    assert entry["scope_href"] is None


def test_aliases_resolve_the_basename_spelling(tmp_path):
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    payload = build_labels(tmp_path)
    canonical = payload["aliases"]["spec:2026-07-16-foo-design.md"]
    assert canonical in payload["labels"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_labels.py -k "statement or relations or openable or aliases" -v`
Expected: FAIL with `ImportError: cannot import name 'build_labels'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/factory/system/labels.py`:

```python
import re
from urllib.parse import quote

from factory.orchestrator import ledger as ledger_module
from factory.requirements import register as register_module
from factory.system import adr as adr_module
from factory.system import bundles as bundles_module

# Exactly the intersection of queries.py:74's _SCOPE_KINDS and
# system-bootstrap.ts:351's TABS_BY_KIND. `spec`/`plan` parse as nothing;
# `adr`/`diag`/`feat`/`metric`/`goal` parse as scopes but fall through to the
# bundle tab set and would render an error page. Neither gets a link.
_OPENABLE_KINDS = frozenset({"bundle", "sr", "task", "file"})

_HEADING_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _scope_href(ref: str, kind: str) -> str | None:
    if kind not in _OPENABLE_KINDS:
        return None
    return "/system?scope=" + quote(ref, safe="")


def _first_paragraph(body: str) -> str | None:
    for block in body.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#"):
            return " ".join(text.split())
    return None


def _section_paragraph(body: str, heading: str) -> str | None:
    """First paragraph of the first section whose heading matches, case-insensitively."""
    matches = list(_HEADING_SECTION.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1).strip().lower() != heading.lower():
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return _first_paragraph(body[match.end():end])
    return None
```

Then `build_labels`, assembling one entry per artifact:

```python
def build_labels(root: Path) -> dict:
    """The label index: every known ref with its title and recorded description.

    Composes existing loaders only. Never synthesises text: a description is
    verbatim from one named field, or it is None.
    """
    degraded: list[str] = []
    nodes = trace_model.load_nodes(root)
    aliases = build_alias_map(root, nodes)
    labels: dict[str, dict] = {}

    requirements = {}
    try:
        requirements = {r.id: r for r in register_module.load_register(root / "requirements")}
    except Exception as exc:  # a missing register must not sink the index
        degraded.append(f"requirements register unavailable: {exc}")

    tasks = {}
    try:
        tasks = {t.id: t for t in ledger_module.load_tasks(root / "tasks")}
    except Exception as exc:
        degraded.append(f"task ledger unavailable: {exc}")

    adrs = {}
    try:
        adrs = adr_module.load_adrs(root)
    except Exception as exc:
        degraded.append(f"adrs unavailable: {exc}")

    for node in nodes:
        ref = canonical_ref(root, node)
        description: str | None = None
        source: str | None = None
        status: str | None = None
        relations: dict[str, list[str]] = {}
        deferral_reason: str | None = None

        if node.kind == "sr" and node.id in requirements:
            req = requirements[node.id]
            description, source = req.statement.strip(), "statement"
            deferral_reason = getattr(req, "trace_deferred", None)
        elif node.kind == "task" and node.id in tasks:
            task = tasks[node.id]
            status = task.status
            satisfies = [aliases.get(s, s) for s in task.satisfies]
            if satisfies:
                relations["satisfies"] = satisfies
        elif node.kind == "adr" and node.id in adrs:
            body = (root / node.path).read_text(encoding="utf-8")
            found = _section_paragraph(body, "Decision")
            if found:
                description, source = found, "decision"
        elif node.kind in _PATH_KINDS:
            body = (root / node.path).read_text(encoding="utf-8")
            found = _section_paragraph(body, "Purpose") or _first_paragraph(
                body.split("\n", 1)[-1]
            )
            if found:
                description, source = found, "purpose"

        labels[ref] = {
            "ref": ref,
            "id": node.id,
            "kind": node.kind,
            "title": node.title,
            "description": description,
            "description_source": source,
            "deferral_reason": deferral_reason,
            "status": status,
            "relations": relations,
            "path": _relative_posix(root, root / node.path),
            "scope_href": _scope_href(ref, node.kind),
        }

    for bundle in bundles_module.list_bundles(root / "bundles"):
        ref = f"bundle:{bundle.id}"
        labels[ref] = {
            "ref": ref, "id": bundle.id, "kind": "bundle", "title": bundle.label,
            "description": bundle.description,
            "description_source": "description" if bundle.description else None,
            "deferral_reason": None, "status": None, "relations": {},
            "path": str(bundle.citation.path),
            "scope_href": _scope_href(ref, "bundle"),
        }
        aliases[ref] = ref
        aliases[bundle.id] = ref

    return {"labels": labels, "aliases": aliases, "degraded": degraded}
```

`src/factory/system/cli.py` — register the subcommand beside `health` (around line 445):

```python
    sub.add_parser("labels", parents=[common])
```

and in the dispatch, mirroring how `health` is handled:

```python
    if args.command == "labels":
        return _emit(labels_module.build_labels(root), args, _render_labels)
```

with a plain human renderer:

```python
def _render_labels(result: dict) -> str:
    lines = [f"labels: {len(result['labels'])}"]
    for ref, entry in result["labels"].items():
        described = "described" if entry["description"] else "no description"
        lines.append(f"  {ref}: {entry['title']} [{described}]")
    return "\n".join(lines)
```

Read `cli.py:440-470` first and follow the exact `_emit`/dispatch pattern already used
by `health` — do not invent a new one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/system/test_labels.py -v && uv run python -m factory.system labels --json | head -c 400`
Expected: PASS; the CLI prints a JSON object with `labels`, `aliases`, `degraded`

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/labels.py src/factory/system/cli.py tests/unit/system/test_labels.py
git commit -m "feat(system): label index projection with recorded descriptions"
```

---

## Task 4: Traversal emits canonical ref lists

**Files:**
- Modify: `src/factory/system/queries.py:1505-1590`
- Modify: `pi-ext/factory-watch/src/system-cli.ts:251-256`
- Test: `tests/unit/system/test_queries.py`

**Interfaces:**
- Consumes: `normalize_ref` / `build_alias_map` (Task 1)
- Produces: `SystemTraversal { requirement: string[]; tasks: string[]; design: string[]; files: string[] }` — all canonical refs

**Why:** `queries.py:1565` emits bare ids, and `queries.py:1588` emits `", ".join(sr_ids)` — a single comma-joined string. `refChip` cannot consume either without the browser parsing, which the design forbids.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/system/test_queries.py
def test_traversal_emits_canonical_ref_lists_for_a_bundle(tmp_path):
    _fixtures.write_sr(tmp_path, "SR-001", title="One", statement="s")
    _fixtures.write_sr(tmp_path, "SR-002", title="Two", statement="s")
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    _fixtures.write_bundle(bundles_dir, "b1", "Bundle one", ["sr:SR-001", "sr:SR-002"])
    result = query_traversal(tmp_path, "bundle:b1")
    assert result["requirement"] == ["sr:SR-001", "sr:SR-002"]
    assert isinstance(result["tasks"], list)
    assert all(":" in ref for ref in result["requirement"])


def test_traversal_task_refs_are_prefixed(tmp_path):
    _fixtures.write_sr(tmp_path, "SR-001", title="One", statement="s")
    _fixtures.write_task(tmp_path, "T-001", title="Do it", satisfies=["SR-001"])
    result = query_traversal(tmp_path, "sr:SR-001")
    assert result["requirement"] == ["sr:SR-001"]
    assert result["tasks"] == ["task:T-001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_queries.py -k traversal -v`
Expected: FAIL — `requirement` is `"SR-001, SR-002"` (a string), `tasks` are `["T-001"]` (bare)

- [ ] **Step 3: Write minimal implementation**

In `queries.py`, build an alias map once at the top of `query_traversal` and map every
emitted value through it:

```python
    from factory.system.labels import build_alias_map

    aliases = build_alias_map(root)

    def _ref(raw: str) -> str:
        # Unresolvable values are emitted unchanged so nothing is invented;
        # the browser renders them as "not in the label index".
        return aliases.get(raw, raw)
```

Replace the `", ".join(sr_ids)` at line 1588 with `[_ref(s) for s in sr_ids]`, the
single `sr_id` at 1565 with `[_ref(sr_id)]`, and map `tasks`, `design`, `files`
through `_ref` likewise. `files` are repo-relative paths and become `file:<path>`.

Read lines 1500-1600 before editing; preserve the existing ordering exactly — this
change is shape-only, never order.

`pi-ext/factory-watch/src/system-cli.ts:252`:

```ts
export interface SystemTraversal {
  requirement: string[];
  tasks: string[];
  design: string[];
  files: string[];
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/system -v && cd pi-ext/factory-watch && npx tsc --noEmit`
Expected: PASS. `tsc` will flag `renderTraversal`'s `addStep('Requirement', [trav.requirement])` — leave it for Task 9; if it blocks, change it to `trav.requirement` now.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/queries.py pi-ext/factory-watch/src/system-cli.ts tests/unit/system/test_queries.py
git commit -m "feat(system): traversal emits canonical ref lists, not joined bare ids"
```

---

## Task 5: Vocabulary table

**Files:**
- Create: `src/factory/system/vocabulary.py`
- Create: `tests/unit/system/test_vocabulary.py`
- Modify: `src/factory/system/cli.py`

**Interfaces:**
- Produces: `VOCABULARY: dict[str, dict]`, `COVERAGE_REGISTRY: dict[str, tuple[str, ...]]`, `build_vocabulary() -> dict`, `factory.system vocabulary --json`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/system/test_vocabulary.py
from factory.system.vocabulary import COVERAGE_REGISTRY, VOCABULARY, build_vocabulary


def test_every_registry_value_has_an_entry():
    missing = [
        value
        for values in COVERAGE_REGISTRY.values()
        for value in values
        if value not in VOCABULARY
    ]
    assert missing == [], f"undefined vocabulary terms: {missing}"


def test_every_entry_is_in_the_registry():
    known = {v for values in COVERAGE_REGISTRY.values() for v in values}
    assert set(VOCABULARY) - known == set()


def test_glosses_are_at_most_eight_words():
    long = {t: e["gloss"] for t, e in VOCABULARY.items() if len(e["gloss"].split()) > 8}
    assert long == {}


def test_computed_by_is_always_a_list():
    assert all(isinstance(e["computed_by"], list) for e in VOCABULARY.values())


def test_claim_kinds_match_the_typescript_union():
    ts = (
        __import__("pathlib").Path("pi-ext/factory-watch/src/system-cli.ts")
        .read_text(encoding="utf-8")
    )
    for kind in ("recorded", "derived", "synthesized", "missing"):
        assert f'"{kind}"' in ts
        assert kind in VOCABULARY


def test_build_vocabulary_is_serialisable():
    import json
    json.dumps(build_vocabulary())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_vocabulary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.system.vocabulary'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/system/vocabulary.py`. The registry is the test's source of truth
because several rendered values are typed `string` and are not mechanically
enumerable. Write **every** value listed in the design's "Coverage registry" section —
the test fails otherwise. Shape:

```python
"""Plain-language definitions for every contract word the navigator shows.

Static data. Inlined into the page by system-shell.ts at render time -- the
browser never fetches this. Exposed as `factory.system vocabulary --json` so
it stays inspectable and testable from Python.
"""
from __future__ import annotations

COVERAGE_REGISTRY: dict[str, tuple[str, ...]] = {
    "claim-kind": ("recorded", "derived", "synthesized", "missing"),
    "freshness": ("fresh", "stale", "degraded", "n/a"),
    "matrix-status": ("passed", "failed", "error", "blocked", "never-run", "unknown"),
    "validation-state": ("never_validated",),
    "readiness": ("weak", "medium", "strong"),
    "readiness-count": (
        "sr_total", "bound", "covered", "current", "deferred", "validated",
    ),
    "health-class": (
        "task->plan", "task->SR", "plan->spec", "SR satisfied", "SR validated",
    ),
    "health-counter": ("dangling", "proposed"),
    "timeline-actor": (
        "human", "dev", "review", "validation", "orchestrator", "unknown",
        "not-recorded",
    ),
    "timeline-action": (
        "approved", "rejected", "validated", "repaired", "published", "stopped",
    ),
    "citation-kind": (
        "manifest", "task", "requirement", "review", "decision", "trace",
        "bundle", "session",
    ),
    "scope-kind": ("run", "manifest"),
    "run-source": ("session",),
    "disposition": ("pending", "exempt"),
    "stops-at": ("satisfies", "chain-complete"),
    "noun": (
        "bundle", "scope", "SR", "BR", "ADR", "evidence run",
        "evidence manifest", "session record", "claim", "span", "citation",
    ),
}

VOCABULARY: dict[str, dict] = {
    "recorded": {
        "term": "recorded",
        "group": "claim-kind",
        "gloss": "straight from a file, not inferred",
        "definition": (
            "Copied verbatim out of an artifact file. Nothing was computed or "
            "written by a model."
        ),
        "siblings": ["derived", "synthesized", "missing"],
        "computed_by": [
            "src/factory/system/queries.py",
            "src/factory/system/story.py",
        ],
    },
    # … one entry per registry value.
}


def build_vocabulary() -> dict:
    return {"version": 1, "terms": VOCABULARY}
```

Values appearing in more than one group (`passed`, `failed`, `error`, `deferred`,
`task`, `sr`, `validated`, `bundle`) are listed once, in the group where they are most
often read, and their definition names the other context. That is why several tuples
above look short — the duplicates were removed deliberately, not forgotten.

Each `health-class` definition must state **its denominator rule in words**: the
landing shows `SR satisfied 102/181` beside `SR validated 1/43` and nothing explains
why the denominators differ.

Register the CLI subcommand exactly as Task 3 did for `labels`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/system/test_vocabulary.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/vocabulary.py src/factory/system/cli.py tests/unit/system/test_vocabulary.py
git commit -m "feat(system): vocabulary table with a completeness gate"
```

---

## Task 6: Remediation table

**Files:**
- Create: `src/factory/system/remediation.py`
- Create: `tests/unit/system/test_remediation.py`
- Modify: `src/factory/system/cli.py`

**Interfaces:**
- Produces: `REMEDIATION: dict[str, dict]`, `ABSENCE_STATES: tuple[str, ...]`, `build_remediation() -> dict`, `factory.system remediation --json`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/system/test_remediation.py
import re
from pathlib import Path

from factory.system.remediation import ABSENCE_STATES, REMEDIATION, build_remediation
from factory.trace.gaps import GapKind
from typing import get_args


def test_every_gap_kind_has_an_entry():
    missing = [k for k in get_args(GapKind) if k not in REMEDIATION]
    assert missing == []


def test_every_absence_state_has_an_entry():
    assert [s for s in ABSENCE_STATES if s not in REMEDIATION] == []


def test_no_entry_outside_gap_kinds_and_absence_states():
    known = set(get_args(GapKind)) | set(ABSENCE_STATES)
    assert set(REMEDIATION) - known == set()


def test_severity_is_absence_or_failure():
    assert all(e["severity"] in {"absence", "failure"} for e in REMEDIATION.values())


def test_only_id_and_ref_substitutions_are_used():
    for entry in REMEDIATION.values():
        for token in re.findall(r"\{(\w+)\}", entry["command"]):
            assert token in {"id", "ref"}, entry


def test_every_slash_command_is_registered():
    src = Path("pi-ext/factory-watch/src")
    registered = set()
    for path in src.glob("*.ts"):
        registered |= set(
            re.findall(r'registerCommand\("([a-z0-9-]+)"', path.read_text(encoding="utf-8"))
        )
    for entry in REMEDIATION.values():
        if entry["command_kind"] != "slash":
            continue
        name = entry["command"].split()[0].lstrip("/")
        assert name in registered, f"unregistered slash command: /{name}"


def test_every_shell_command_names_a_real_subparser():
    for entry in REMEDIATION.values():
        if entry["command_kind"] != "shell":
            continue
        parts = entry["command"].split()
        module = parts[parts.index("-m") + 1]
        sub = parts[parts.index("-m") + 2]
        source = Path(module.replace(".", "/")) / "cli.py"
        assert f'add_parser("{sub}"' in source.read_text(encoding="utf-8"), entry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/system/test_remediation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.system.remediation'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/factory/system/remediation.py
"""What to do about each gap, and the exact command that does it.

Static data, inlined into the page at render time. The navigator displays
these commands; it never runs one (write operations are SP-C's scope).

`{id}` is the bare identifier, `{ref}` the canonical ref. Templates use
`{id}` wherever the target command takes a bare identifier -- which is every
current case.
"""
from __future__ import annotations

# Absence states the browser decides itself: each is an explicit
# `if (!x.length)` branch in the renderers, so the browser always knows which
# key applies without interpreting any free text.
ABSENCE_STATES: tuple[str, ...] = (
    "no_claims", "no_matrix_rows", "no_timeline_events", "no_guide_sections",
    "no_runs", "no_requirements", "no_changed_files", "no_commit_range",
    "no_trace", "no_traversal_step", "no_bundles", "no_description",
    "traversal_not_applicable", "matrix_never_run", "unbundled_artifact",
    "unresolved_ref",
)

REMEDIATION: dict[str, dict] = {
    "sr_unsatisfied": {
        "state": "sr_unsatisfied",
        "headline": "No task satisfies this requirement",
        "what_it_means": "No task in the ledger declares that it implements {id}.",
        "why_it_matters": (
            "Nothing implements it yet, so it cannot be validated and the "
            "feature it belongs to stays weak."
        ),
        "command": "/trace-fix {id}",
        "command_kind": "slash",
        "severity": "absence",
    },
    "no_bundles": {
        "state": "no_bundles",
        "headline": "No features defined yet",
        "what_it_means": (
            "A feature bundle groups the requirements, tasks, and decisions you "
            "read together to understand one part of the system."
        ),
        "why_it_matters": (
            "Bundles are how this project is browsed, so until one exists the "
            "directory stays empty."
        ),
        "command": "uv run python -m factory.system bundle check --draft <path>",
        "command_kind": "shell",
        "severity": "absence",
    },
    # … one entry per GapKind and per ABSENCE_STATES member.
}


def build_remediation() -> dict:
    return {"version": 1, "states": REMEDIATION}
```

**`factory.system check` does not exist.** The only `check` is
`factory.system bundle check --draft <path>` (`system/cli.py:452`) and it requires
`--draft`. `test_every_shell_command_names_a_real_subparser` will need the two-level
form handled — if a command's third token is itself a subcommand group, assert against
the nested `add_parser` instead. Adjust the test to match reality; do not weaken it to
pass.

Register the CLI subcommand as in Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/system/test_remediation.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/remediation.py src/factory/system/cli.py tests/unit/system/test_remediation.py
git commit -m "feat(system): remediation table gated against the real CLI surface"
```

---

## Task 7: Labels endpoint

**Files:**
- Modify: `pi-ext/factory-watch/src/system-cli.ts`
- Modify: `pi-ext/factory-watch/src/docs-server.ts:256-260, 271-281`
- Test: `pi-ext/factory-watch/test/system-cli.test.ts`

**Interfaces:**
- Consumes: `factory.system labels --json` (Task 3)
- Produces: `SystemLabels`, `SystemLabelEntry`, `loadSystemLabelsAsync(cwd) -> Promise<CliResult<SystemLabels>>`, route `GET /api/system/labels`

- [ ] **Step 1: Write the failing test**

```ts
// append to pi-ext/factory-watch/test/system-cli.test.ts
import { buildSystemCommand } from "../src/system-cli.js";

test("labels command is built as a factory.system subcommand", () => {
  const cmd = buildSystemCommand(["labels", "--json"]);
  expect(cmd.bin).toBe("uv");
  expect(cmd.args).toEqual(["run", "python", "-m", "factory.system", "labels", "--json"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-cli.test.ts`
Expected: PASS for the builder (it is generic) — then add the type-level assertion below, which fails to compile until Step 3.

```ts
import type { SystemLabels } from "../src/system-cli.js";

test("label entries expose title, description and scope_href", () => {
  const entry: SystemLabels["labels"][string] = {
    ref: "task:T-060", id: "T-060", kind: "task", title: "Wire the governor",
    description: null, description_source: null, deferral_reason: null,
    status: "done", relations: { satisfies: ["sr:SR-121"] },
    path: "tasks/T-060.md", scope_href: "/system?scope=task%3AT-060",
  };
  expect(entry.title).toBe("Wire the governor");
});
```

- [ ] **Step 3: Write minimal implementation**

`system-cli.ts` — append, mirroring `SystemHealth`'s comment discipline:

```ts
// Mirrors `factory.system labels --json`. Titles and descriptions are read
// from recorded fields in Python; this file renders them and never derives a
// description, a title, or a ref.
export interface SystemLabelEntry {
  ref: string;
  id: string;
  kind: string;
  title: string;
  description: string | null;
  description_source: string | null;
  deferral_reason: string | null;
  status: string | null;
  relations: Record<string, string[]>;
  path: string;
  scope_href: string | null;
}

export interface SystemLabels {
  labels: Record<string, SystemLabelEntry>;
  aliases: Record<string, string>;
  degraded: string[];
}

export function loadSystemLabelsAsync(cwd: string): Promise<CliResult<SystemLabels>> {
  const cmd = buildSystemCommand(["labels", "--json"]);
  return runJsonCliAsync<SystemLabels>(cwd, cmd.bin, cmd.args);
}
```

There is deliberately **no** synchronous `loadSystemLabels`: `runJsonCli` is
`spawnSync` (`cli-runner.ts:44`) and would block the docs server's event loop for a
full interpreter start.

`docs-server.ts` — add the route beside `/api/system/health`:

```ts
  // The label index: every ref's title and recorded description. Async only --
  // this reads every spec and plan body, so it must not block the event loop.
  if (req.method === "GET" && url.pathname === "/api/system/labels") {
    const result = await loadSystemLabelsAsync(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }
```

and update the comment at `docs-server.ts:258` — it says "only these eight exact paths
exist" and is now wrong.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-cli.ts pi-ext/factory-watch/src/docs-server.ts pi-ext/factory-watch/test/system-cli.test.ts
git commit -m "feat(system): /api/system/labels endpoint, async only"
```

---

## Task 8: Client preamble and CSS

**Files:**
- Modify: `pi-ext/factory-watch/src/system-shell.ts:30-70` and its `<style>` block
- Modify: `pi-ext/factory-watch/src/system-renderers.ts:1-16` (contract comment)
- Test: `pi-ext/factory-watch/test/system-page.test.ts`

**Interfaces:**
- Consumes: `build_vocabulary`, `build_remediation` (Tasks 5, 6)
- Produces: page-scope bindings `LABELS`, `ALIASES`, `VOCABULARY`, `REMEDIATION`; `setLabels(payload)`; CSS classes `.ref-chip`, `.info-card`, `.gloss`, `.next-step`, `.presence-rail`, `.context-rail`, `.bounded-list`

- [ ] **Step 1: Write the failing test**

```ts
// append to pi-ext/factory-watch/test/system-page.test.ts
test("the page inlines the vocabulary and remediation tables", () => {
  const html = renderSystemPageHtml();
  expect(html).toContain("var VOCABULARY =");
  expect(html).toContain("var REMEDIATION =");
  expect(html).toContain('"recorded"');
  expect(html).toContain('"sr_unsatisfied"');
});

test("the page declares mutable label bindings before the renderers", () => {
  const html = renderSystemPageHtml();
  expect(html.indexOf("var LABELS =")).toBeLessThan(html.indexOf("function refChip"));
});

test("gloss text uses --text-muted, never --text-dim", () => {
  const html = renderSystemPageHtml();
  const gloss = html.match(/\.gloss\s*\{[^}]*\}/)?.[0] ?? "";
  expect(gloss).toContain("--text-muted");
  expect(gloss).not.toContain("--text-dim");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-page.test.ts`
Expected: FAIL — `var VOCABULARY =` not found

- [ ] **Step 3: Write minimal implementation**

`system-shell.ts` — the tables are read from Python **once at module load** and frozen
into the page. Add near the top:

```ts
import { runJsonCli } from './cli-runner.js';
```

No — do not spawn at render time. Instead, generate the two tables into a checked-in
TypeScript constant module and import it:

- Create `pi-ext/factory-watch/src/system-vocabulary-data.ts` exporting
  `export const VOCABULARY_DATA = { … } as const;` and
  `export const REMEDIATION_DATA = { … } as const;`, both copied verbatim from the
  Python tables.
- Task 13 adds the drift test that fails if these diverge from Python.

Then extend `clientSource()`'s preamble at line 31:

```ts
  const preamble = `
  function clear(el) {
    el.innerHTML = '';
  }
  var LABELS = {};
  var ALIASES = {};
  var VOCABULARY = ${JSON.stringify(VOCABULARY_DATA)};
  var REMEDIATION = ${JSON.stringify(REMEDIATION_DATA)};
  function setLabels(payload) {
    LABELS = (payload && payload.labels) || {};
    ALIASES = (payload && payload.aliases) || {};
  }`;
```

and join `preamble` where `clear` is joined today.

Add `refChip`, `infoCard`, `boundedList`, `nextStepBlock`, `glossBadge` (Tasks 9-11)
to the renderers array as they are written — the array is the only place a function
becomes visible in the page.

Update `system-renderers.ts:4-6`. It currently reads "none of them reads fetch/state".
Replace with:

```ts
// Each function builds DOM nodes from a payload it is handed; none of them
// fetches, sorts, filters by freshness, or decides ordering -- "Python
// computes, this only renders" applies to every function here. They MAY read
// the frozen page-scope lookups (LABELS, ALIASES, VOCABULARY, REMEDIATION),
// which are data Python computed, not state this file owns.
```

CSS — add to the `<style>` block, deriving every value from the existing tokens
(`system-shell.ts:78`) and following the visual addendum exactly:

```css
  .ref-chip { display: inline-flex; align-items: baseline; gap: 6px; max-width: 100%; }
  .ref-chip .chip-id { padding: 0 3px; border-radius: 3px; background: var(--signal-soft); font: 12px/1.5 var(--font-mono); }
  .ref-chip .chip-sep { color: var(--text-dim); }
  .ref-chip .chip-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ref-chip:hover .chip-id, .ref-chip:focus-visible .chip-id { box-shadow: inset 0 -1px 0 var(--signal); }
  .gloss { margin-top: 2px; color: var(--text-muted); font-size: 12px; line-height: 1.5; }
  .info-trigger { padding: 0 2px; border: 0; background: none; color: var(--signal); font-size: 11px; cursor: pointer; }
  .info-card { position: absolute; z-index: 40; max-width: 34ch; padding: 12px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-md); background: var(--surface-raised); box-shadow: var(--shadow-raised); }
  .presence-rail { border-left: 3px solid var(--line-strong); padding-left: 12px; }
  .presence-rail.is-absent { border-left-style: dashed; border-left-color: var(--stale); }
  .presence-rail.is-failure { border-left-style: solid; border-left-color: var(--degraded); }
  .next-step { margin: 12px 0; }
  .next-step .command { display: flex; align-items: center; gap: 10px; margin-top: 8px; padding: 9px 11px; border-radius: var(--radius-sm); background: var(--surface-soft); font: 13px/1.5 var(--font-mono); }
  .next-step .prompt { color: var(--signal); }
  .bounded-list { display: grid; gap: 4px; }
  @media (prefers-reduced-motion: reduce) { .info-card { transition: none; } }
  @media (min-width: 1200px) { .workspace-split { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; } }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-shell.ts pi-ext/factory-watch/src/system-vocabulary-data.ts pi-ext/factory-watch/src/system-renderers.ts pi-ext/factory-watch/test/system-page.test.ts
git commit -m "feat(system): page-scope comprehension bindings, inlined tables and CSS"
```

---

## Task 9: refChip, cards and bounded lists

**Files:**
- Create: `pi-ext/factory-watch/src/system-comprehension.ts`
- Create: `pi-ext/factory-watch/test/system-comprehension.test.ts`
- Modify: `pi-ext/factory-watch/src/system-shell.ts` (renderers array)

**Interfaces:**
- Consumes: `LABELS`, `ALIASES` (Task 8)
- Produces: `refChip(raw: string): HTMLElement`, `infoCard(fields): HTMLElement`, `boundedList(refs: string[], limit?: number): HTMLElement`

- [ ] **Step 1: Write the failing test**

```ts
// pi-ext/factory-watch/test/system-comprehension.test.ts
import { JSDOM } from "jsdom";
import { beforeEach, expect, test } from "vitest";
import { refChip, boundedList } from "../src/system-comprehension.js";

beforeEach(() => {
  const dom = new JSDOM("<!doctype html><body></body>");
  (globalThis as any).document = dom.window.document;
  (globalThis as any).LABELS = {
    "task:T-060": {
      ref: "task:T-060", id: "T-060", kind: "task",
      title: "Wire the safety governor into the planner loop",
      description: null, description_source: null, deferral_reason: null,
      status: "done", relations: { satisfies: ["sr:SR-121"] },
      path: "tasks/T-060.md", scope_href: "/system?scope=task%3AT-060",
    },
  };
  (globalThis as any).ALIASES = { "T-060": "task:T-060", "task:T-060": "task:T-060" };
});

test("a known ref renders id and title inline", () => {
  const el = refChip("task:T-060");
  expect(el.querySelector(".chip-id")?.textContent).toBe("T-060");
  expect(el.querySelector(".chip-title")?.textContent).toBe(
    "Wire the safety governor into the planner loop",
  );
});

test("a bare id resolves through the alias map", () => {
  expect(refChip("T-060").querySelector(".chip-title")?.textContent).toBe(
    "Wire the safety governor into the planner loop",
  );
});

test("an unknown ref says so and is never guessed", () => {
  const el = refChip("T-999");
  expect(el.textContent).toContain("T-999");
  expect(el.textContent).toContain("not in the label index");
  expect(el.className).toContain("is-absent");
});

test("bounded list shows five rows and hides the rest behind a disclosure", () => {
  const refs = Array.from({ length: 15 }, (_, i) => `SR-${i}`);
  const el = boundedList(refs);
  expect(el.querySelectorAll(":scope > .ref-chip").length).toBe(5);
  const details = el.querySelector("details");
  expect(details?.querySelector("summary")?.textContent).toBe("+ 10 more");
});

test("bounded list under the limit renders no disclosure", () => {
  expect(boundedList(["T-060"]).querySelector("details")).toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-comprehension.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```ts
// pi-ext/factory-watch/src/system-comprehension.ts
// Comprehension layer renderers: ref chips, info cards, bounded lists and
// Next-step blocks.
//
// Like system-renderers.ts these are embedded into the page's inline <script>
// via Function.prototype.toString() (see system-shell.ts), so they must be
// plain function declarations referencing only siblings and the page-scope
// bindings LABELS / ALIASES / VOCABULARY / REMEDIATION.
//
// This file never parses a ref. Resolution is ALIASES, computed in Python by
// factory.system.labels.normalize_ref.

/* eslint-disable no-undef */

declare const LABELS: Record<string, any>;
declare const ALIASES: Record<string, string>;

export function resolveLabel(raw: string): any | null {
  const canonical = ALIASES[raw];
  return canonical ? LABELS[canonical] || null : null;
}

export function refChip(raw: string): HTMLElement {
  const entry = resolveLabel(raw);
  const el = document.createElement('span');
  el.className = 'ref-chip';
  const id = document.createElement('span');
  id.className = 'chip-id';
  id.appendChild(document.createTextNode(entry ? entry.id : raw));
  el.appendChild(id);
  if (!entry) {
    el.className = 'ref-chip presence-rail is-absent';
    const note = document.createElement('span');
    note.className = 'chip-title';
    note.appendChild(document.createTextNode('not in the label index'));
    el.appendChild(note);
    return el;
  }
  const sep = document.createElement('span');
  sep.className = 'chip-sep';
  sep.appendChild(document.createTextNode('·'));
  el.appendChild(sep);
  const title = document.createElement('span');
  title.className = 'chip-title';
  title.appendChild(document.createTextNode(entry.title));
  el.appendChild(title);
  el.tabIndex = 0;
  el.dataset.ref = entry.ref;
  return el;
}

export function boundedList(refs: string[], limit?: number): HTMLElement {
  const max = limit || 5;
  const el = document.createElement('div');
  el.className = 'bounded-list';
  refs.slice(0, max).forEach((ref: string) => el.appendChild(refChip(ref)));
  if (refs.length <= max) return el;
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.appendChild(document.createTextNode('+ ' + (refs.length - max) + ' more'));
  details.appendChild(summary);
  refs.slice(max).forEach((ref: string) => details.appendChild(refChip(ref)));
  el.appendChild(details);
  return el;
}
```

Then `infoCard(entry)` building the card described in the visual addendum, and a
single delegated controller that opens it on `mouseenter` after 120 ms, on `focus`
immediately, and on `click` as a toggle; closes on `Escape` returning focus to the
trigger; and keeps at most one card open.

Add `resolveLabel`, `refChip`, `boundedList`, `infoCard` to `clientSource()`'s
renderers array **before** the functions that call them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-comprehension.ts pi-ext/factory-watch/src/system-shell.ts pi-ext/factory-watch/test/system-comprehension.test.ts
git commit -m "feat(system): ref chips, info cards and bounded ref lists"
```

---

## Task 10: Wire chips into every emission site

**Files:**
- Modify: `pi-ext/factory-watch/src/system-renderers.ts` at lines 148, 184, 237, 340, 404, 430-436, 555, 583-588
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts:270, 755-775`
- Test: `pi-ext/factory-watch/test/system-page-dom.test.ts`, `system-page-trace.test.ts`, `system-page-vcycle.test.ts`, `system-page-sidebar.test.ts`

**Interfaces:**
- Consumes: `refChip`, `boundedList` (Task 9); list-shaped traversal (Task 4)

- [ ] **Step 1: Write the failing test**

```ts
// append to pi-ext/factory-watch/test/system-page-dom.test.ts
test("matrix rows render the requirement title, not just its id", () => {
  // build the page DOM as the existing tests in this file do, seed LABELS
  // with sr:SR-121 -> "Battery-aware return", then:
  renderMatrix({ scope: { kind: "bundle", ref: "bundle:b" }, rows: [
    { subject: { kind: "sr", ref: "sr:SR-121" }, status: "never-run",
      evidence: [], freshness: { state: "n/a", reason: null, dependencies: [] },
      summary: "no validation recorded" },
  ]});
  const row = document.getElementById("panelMatrix")!;
  expect(row.querySelector(".chip-title")?.textContent).toBe("Battery-aware return");
});

test("the traversal spine renders one chip per row, bounded at five", () => {
  renderTraversal({
    requirement: ["sr:SR-030", "sr:SR-033", "sr:SR-038", "sr:SR-086", "sr:SR-087",
                  "sr:SR-088", "sr:SR-089"],
    tasks: [], design: [], files: [],
  });
  const step = document.querySelector(".trace-spine-step .bounded-list")!;
  expect(step.querySelectorAll(":scope > .ref-chip").length).toBe(5);
  expect(step.querySelector("summary")?.textContent).toBe("+ 2 more");
});

test("an empty traversal step reads Not recorded, not an empty row", () => {
  renderTraversal({ requirement: ["sr:SR-030"], tasks: [], design: [], files: [] });
  expect(document.querySelector(".trace-spine-step:nth-child(3)")?.textContent)
    .toContain("Not recorded");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-page-dom.test.ts`
Expected: FAIL — `.chip-title` is null; the spine renders a comma-joined string

- [ ] **Step 3: Write minimal implementation**

Replace each bare-text emission with a chip. Reference table — every site, verified:

| File:line | Today | Becomes |
|---|---|---|
| `system-renderers.ts:148` | `'member of bundles: ' + join(', ')` | label + `boundedList(brief.member_of)` |
| `:184` | `subject.appendChild(text(row.subject.ref))` | `subject.appendChild(refChip(row.subject.ref))` |
| `:237` | `text(event.subject.ref)` | `refChip(event.subject.ref)` |
| `:340` | `text(path)` per changed file | `refChip(path)` |
| `:404` | `text(ref)` per requirement | `boundedList(story.requirements)` |
| `:430` | `hop(path.file)` | `hop` wrapping `refChip(path.file)` |
| `:432` | `hop(path.run.run_id)` | **unchanged** — a run id is not a ref (`trace/model.py:102` creates no run nodes) |
| `:434` | `hop(path.task ? path.task.id : 'unresolved')` | `refChip(path.task.id)` or the absent treatment |
| `:436` | `hop(requirements.join(', '))` | `boundedList(path.requirements)` |
| `:555` | `'upstream: ' + entry.br.id + …` | label + `refChip(entry.br.id)` |
| `:583,586` | `'plan: ' + t.plan` (renders `plan: plan:foo.md`) | `refChip(t.plan)` — this also fixes the double-prefix wart |
| `:588` | `hop(t.task)` | `refChip(t.task)` |
| `system-bootstrap.ts:270` | `text(ref)` in Unbundled rows | `refChip(ref)` |
| `system-bootstrap.ts:766` | `values.join(', ') \|\| 'Not recorded'` | `boundedList(values)`, or the `Not recorded` absence treatment when empty |

`renderBundleList` (`:786`) and the sidebar's bundle rows (`:219`) already render
labels and are **not** changed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS. Several existing DOM tests assert bare-ref text content and will need
their expectations updated to the chip structure — update them, do not delete them.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(system): every artifact reference renders with its title"
```

---

## Task 11: Glosses, definition cards and the vocabulary panel

**Files:**
- Modify: `pi-ext/factory-watch/src/system-comprehension.ts`
- Modify: `pi-ext/factory-watch/src/system-renderers.ts:22-38` (`badge`, `freshnessBadge`)
- Modify: `pi-ext/factory-watch/src/system-shell.ts` (header control, panel markup)
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts:694-723` (health class labels)
- Test: `pi-ext/factory-watch/test/system-comprehension.test.ts`

**Interfaces:**
- Consumes: `VOCABULARY` (Task 8), `infoCard` (Task 9)
- Produces: `glossFor(term)`, `definitionTrigger(term)`, `renderVocabularyPanel()`

- [ ] **Step 1: Write the failing test**

```ts
test("a badge carries its gloss inline and a definition trigger", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: {
    term: "recorded", group: "claim-kind",
    gloss: "straight from a file, not inferred",
    definition: "Copied verbatim out of an artifact file.",
    siblings: ["derived"], computed_by: ["src/factory/system/queries.py"],
  } } };
  const el = badge("recorded", "kind-recorded");
  expect(el.textContent).toContain("recorded");
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".gloss")?.textContent)
    .toBe("straight from a file, not inferred");
  expect(wrap.querySelector(".info-trigger")?.getAttribute("aria-label"))
    .toBe("What does recorded mean?");
});

test("an unknown term renders the badge with no gloss and no trigger", () => {
  (globalThis as any).VOCABULARY = { terms: {} };
  const el = badge("mystery", "");
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".gloss")).toBeNull();
  expect(wrap.querySelector(".info-trigger")).toBeNull();
});

test("Escape closes the definition card and returns focus", () => {
  // open a card via the trigger, dispatch Escape, assert the card is gone and
  // document.activeElement is the trigger
});

test("health class labels render readable text with the raw name as metadata", () => {
  renderHealthSummary({ health: { classes: [
    { name: "task->plan", satisfied: 21, expected: 21, exempt: 0 },
  ], satisfied: 21, expected: 21, percent: 100, dangling: 0, deferred: 0, proposed: 0 } });
  const metric = document.querySelector(".health-metric")!;
  expect(metric.querySelector(".health-metric-label")?.textContent)
    .toBe("Tasks linked to a plan");
  expect(metric.querySelector(".health-metric-raw")?.textContent).toBe("task->plan");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-comprehension.test.ts`
Expected: FAIL — no `.gloss`, no `.info-trigger`

- [ ] **Step 3: Write minimal implementation**

`badge` and `freshnessBadge` return a wrapper containing the badge, the `ⓘ` trigger,
and the gloss line, looked up in `VOCABULARY.terms`. A term with no entry renders
exactly as today — no gloss, no trigger, never a placeholder.

The trigger is a real `<button type="button">` with
`aria-label = 'What does ' + term + ' mean?'` so it is keyboard reachable.

`renderVocabularyPanel()` renders a workspace view grouped by `group`, each entry
showing the **real badge** beside its definition, siblings, and `computed_by` paths.
Wire a `Vocabulary` control into the header.

`renderHealthSummary` reads the readable label from `VOCABULARY.terms[c.name].label`
and keeps `c.name` in a `.health-metric-raw` mono line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(system): badge glosses, definition cards and the vocabulary panel"
```

---

## Task 12: Next steps, severity, headings and first run

**Files:**
- Modify: `pi-ext/factory-watch/src/system-comprehension.ts` (`nextStepBlock`)
- Modify: `pi-ext/factory-watch/src/system-renderers.ts` (every `class="empty"` site: 169, 216, 265, 282, 296, 336, 390, 408, 455, 469, 540, 562)
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts:154-163` (heading), `:212-233` (sidebar rows), `:777-806` (first run)
- Test: `pi-ext/factory-watch/test/system-landing.test.ts`, `system-page-dom.test.ts`

**Interfaces:**
- Consumes: `REMEDIATION` (Task 8), `LABELS` (Task 9)
- Produces: `nextStepBlock(state: string, subject?: string): HTMLElement`

- [ ] **Step 1: Write the failing test**

```ts
test("a next step names the command and copies it", async () => {
  const el = nextStepBlock("sr_unsatisfied", "SR-121");
  expect(el.querySelector(".command")?.textContent).toContain("/trace-fix SR-121");
  expect(el.querySelector("button")?.textContent).toBe("Copy");
});

test("an empty panel renders exactly one next step", () => {
  renderStory({ scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "Load skills", status: "done" },
    runs: [], requirements: [], degraded: true,
    degraded_reasons: ["task has no recorded runs"] });
  expect(document.querySelectorAll("#panelStory .next-step").length).toBe(1);
});

test("an absence uses the dashed rail, not the failure rail", () => {
  renderStory({ scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "Load skills", status: "done" },
    runs: [], requirements: [], degraded: false, degraded_reasons: [] });
  const empty = document.querySelector("#panelStory .presence-rail")!;
  expect(empty.className).toContain("is-absent");
  expect(empty.className).not.toContain("is-failure");
});

test("the scope heading is the title, with the ref as metadata", () => {
  (globalThis as any).LABELS = { "task:T-001": {
    ref: "task:T-001", id: "T-001", kind: "task", title: "Load skills",
    description: null, description_source: null, deferral_reason: null,
    status: "done", relations: {}, path: "tasks/T-001.md", scope_href: null } };
  (globalThis as any).ALIASES = { "task:T-001": "task:T-001" };
  setScopeHeading("task:T-001");
  expect(document.getElementById("scopeHeader")?.textContent).toBe("Load skills");
  expect(document.getElementById("scopeRef")?.textContent).toBe("task:T-001");
});

test("zero bundles renders the first-run card, not an empty directory", () => {
  renderBundleList({ bundles: [] });
  const list = document.getElementById("bundleList")!;
  expect(list.textContent).toContain("No features defined yet");
  expect(list.querySelector(".next-step")).not.toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run`
Expected: FAIL — `nextStepBlock` undefined; heading is `task:T-001`; bundle list is empty

- [ ] **Step 3: Write minimal implementation**

`nextStepBlock(state, subject)` builds the terminal-styled block from the visual
addendum: `NEXT STEP` eyebrow, `what_it_means`, `why_it_matters`, then a `.command`
row with the `▌` prompt glyph, the substituted command, and a Copy button that writes
to `navigator.clipboard`, becomes `Copied` for two seconds, then reverts.

When the subject has a `deferral_reason` in `LABELS`, render it above
`what_it_means` — a recorded reason outranks the table.

**One Next step per panel.** Each `render*` function collects at most one state key and
appends the block once, after any degraded banner. Do not attach a block to each
empty child.

**Severity applies to browser-decided empty states only.** Apply `presence-rail
is-absent` to each `class="empty"` element. The red `degraded:` banner is untouched —
its reasons are free-text sentences the browser cannot classify without interpreting
them (`story.py:174`, `queries.py:1377`).

`setScopeHeading` reads the label entry: `scopeHeader` becomes `entry.title` (falling
back to `scopeRef` when unknown), `scopeRef` keeps the raw ref, and `entry.description`
renders as the lead paragraph when present.

Sidebar rows: label in a `<span class="scope-label">` on its own line, counts beneath
in `<span class="readiness-counts">`. Two blocks, never one wrapping paragraph.

`renderBundleList` with an empty list renders the first-run card and
`nextStepBlock('no_bundles')`.

Add the dismissible orientation strip with one `localStorage` key.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(system): next steps, absence severity, title headings and first run"
```

---

## Task 13: Context rail, drift gate and browser gate

**Files:**
- Modify: `pi-ext/factory-watch/src/system-shell.ts` (workspace markup)
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts` (rail population, label fetch ordering)
- Create: `tests/unit/system/test_table_drift.py`
- Modify: `pi-ext/factory-watch/test/system-browser-validation.test.ts`

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/system/test_table_drift.py
import json
import re
from pathlib import Path

from factory.system.remediation import REMEDIATION
from factory.system.vocabulary import VOCABULARY

TS = Path("pi-ext/factory-watch/src/system-vocabulary-data.ts")


def _extract(name: str) -> dict:
    text = TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\{{.*?\}}) as const;", text, re.S)
    assert match, f"{name} not found in {TS}"
    return json.loads(match.group(1))


def test_vocabulary_mirror_matches_python():
    assert _extract("VOCABULARY_DATA") == {"version": 1, "terms": VOCABULARY}


def test_remediation_mirror_matches_python():
    assert _extract("REMEDIATION_DATA") == {"version": 1, "states": REMEDIATION}
```

```ts
// append to pi-ext/factory-watch/test/system-browser-validation.test.ts,
// inside the existing BROWSER_GATE describe block
// - assert no console errors on landing and on bundle:reactive-planner
// - assert document.body.scrollWidth <= window.innerWidth at all three viewports
// - assert every .trace-spine-step .bounded-list has at most 5 direct chips
// - assert every element whose text is "Not recorded" has a .next-step sibling
// - focus a .ref-chip by keyboard, assert .info-card appears, press Escape,
//   assert it closes and activeElement is the chip
// - measure computed colour of .gloss against its background and assert >= 4.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/system/test_table_drift.py -v`
Expected: FAIL until the TS mirror is generated

- [ ] **Step 3: Write minimal implementation**

Generate `system-vocabulary-data.ts` from the Python tables (a small script, or by
hand — the drift test is what keeps it honest).

Wrap the workspace in `<div class="workspace-split">` with the panel column and an
`<aside class="context-rail">`. Populate the rail in `loadScope` with the scope
summary, readiness beside its counts, membership, and the current Next step.

In `systemBootstrap`, issue the labels fetch **before** health and await it in both
paths, so `renderFeatureSidebar` never renders bare and then reflows:

```ts
  const labelsPromise = fetch('/api/system/labels')
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  setLabels(await labelsPromise);
  await loadHealth();
```

On a null payload, `setLabels` leaves the lookups empty and every chip renders the
`label index unavailable` treatment.

- [ ] **Step 4: Run everything**

Run:
```bash
uv run pytest tests/unit/system -v
cd pi-ext/factory-watch && npx tsc --noEmit && npm test
BROWSER_GATE=1 npx vitest run test/system-browser-validation.test.ts
BROWSER_GATE=1 BROWSER_GATE_TARGET=C:/coding/pi-agent-factory npx vitest run test/system-browser-validation.test.ts
```
Expected: all PASS. The second gate run exercises the zero-bundle first-run path.

If the gate reports `ReferenceError: __name is not defined`, that is the tsx/esbuild
`keepNames` artifact, not a product bug — the harness must define
`window.__name = (fn) => fn` before navigation.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch tests/unit/system/test_table_drift.py
git commit -m "feat(system): context rail, table drift gate and browser gate assertions"
```

---

## Self-Review

**Spec coverage:** Component 1 → Tasks 1, 3, 4, 9, 10. Component 2 → Tasks 5, 8, 11.
Component 3 → Tasks 6, 8, 12. Component 4 → Tasks 12, 13. Component 5 → Task 2.
Client-side architecture → Task 8. Fetch ordering → Task 13. Error handling → Tasks 9,
13. All three verification sections → Tasks 1-13 plus 13's gate.

**Known gaps carried deliberately:** `spec:`/`plan:` remain unopenable (spec non-goal);
`degraded_reasons` remain free text (spec non-goal); tasks carry no description (spec
Component 1).

**Type consistency:** `refChip`/`boundedList`/`resolveLabel`/`infoCard`/
`nextStepBlock`/`glossFor`/`definitionTrigger`/`renderVocabularyPanel` are named
identically in every task that references them. `SystemTraversal.requirement` is
`string[]` from Task 4 onward, and Task 10's traversal test uses the list shape.
`setLabels` is defined in Task 8 and called in Task 13.
