# System Control Center — SP-B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/system` into a control center — a health landing page, a feature-first bundle sidebar with a published readiness predicate, working traversal, and a member-of affordance — without changing Python's compute-in-Python rendering contract or the existing per-tab behaviour.

**Architecture:** Python composes the health projection and bundle readiness; the browser only renders. New `factory.system.health` module composes `compute_health` + `bundle_coverage` + `ordered_bundle_ids` + per-SR readiness signals from `register`/`gaps`/`validation_status`. `system-page.ts` is split into shell/renderers/bootstrap along its existing seam, staged so the DOM tests stay green.

**Tech Stack:** Python (`factory.system`), TypeScript (`pi-ext/factory-watch`), `pytest` / `vitest`+`jsdom`.

**Design:** `docs/superpowers/specs/2026-08-12-system-control-center-spb-design.md`
**Program:** `docs/superpowers/specs/2026-08-10-system-control-center-program-decomposition.md` (SP-B section)
**Depends on:** SP-A landed (bundle map, `adr:`, `bundle_coverage`, `ordered_bundle_ids`, coverage gate).

**Global constraints (inherited, not renegotiable):**
- Python computes; TypeScript renders. No freshness/ordering/provenance logic in the browser.
- No duplicated logic: `factory.system.health` composes existing loaders, never forks a parser.
- Scope refs exact and case-sensitive; never fuzzy.
- No derived index, no cache; projections computed on demand.
- `pyproject.toml` sets `addopts = "-m unit"`; integration commands must pass `-m 'unit or integration'` or they collect nothing and exit green.
- Payload-derived strings reach the DOM via `createTextNode`/`textContent`; `innerHTML` only ever a quoted literal.
- `NodeKind`/`EdgeKind`/scope kinds stay additive; do not touch existing v1 behaviour.
- Landing: pi-agent-factory only. No product-repo content authored here.

---

## File structure

**Created (pi-agent-factory):**
| File | Responsibility |
|---|---|
| `src/factory/system/health.py` | `query_health`, `bundle_readiness`, per-SR readiness predicate. |
| `pi-ext/factory-watch/src/system-shell.ts` | Shell + CSS + markup (moved from `system-page.ts`). |
| `pi-ext/factory-watch/src/system-renderers.ts` | Per-tab DOM renderers (moved from `system-page.ts`). |
| `pi-ext/factory-watch/src/system-bootstrap.ts` | Client IIFE + landing + sidebar + search + member-of (moved + new). |
| `tests/unit/system/test_health.py` | Task 1/2 Python tests. |
| `pi-ext/factory-watch/test/system-landing.test.ts` | Task 6/7 browser tests. |
| `pi-ext/factory-watch/test/system-membership.test.ts` | Task 8 browser tests. |

**Modified (pi-agent-factory):**
| File | Change |
|---|---|
| `src/factory/system/bundles.py` | add `bundles_containing(repo_root, ref)`. |
| `src/factory/system/queries.py` | `list_scopes` drops `sr:`; add `query_health` entry. |
| `src/factory/system/cli.py` | `health --json`, `memberships <ref>` subcommands. |
| `src/factory/system/__init__.py` | export nothing new (module import only). |
| `src/factory/system/models.py` | no change (readiness joined as plain dict). |
| `pi-ext/factory-watch/src/system-page.ts` | thin re-export of `renderSystemPageHtml`; split staged. |
| `pi-ext/factory-watch/src/docs-server.ts` | import unchanged (still `renderSystemPageHtml`); add `health`/`memberships` endpoints behind the split. |

---

## Task 1: `factory.system.health` — `bundle_readiness` predicate

**Files:** Create `src/factory/system/health.py`, `tests/unit/system/test_health.py`

Derive the published Strong/Medium/Weak readiness predicate per bundle from existing
signals only (register, gaps, validation_status). No new parsing.

- [x] **Step 1: Write the failing test** — a Weak bundle (one unbound SR):

```python
import pytest

from factory.requirements.register import load_register
from factory.system import health
from factory.trace import gaps as gaps_module
from factory.trace import model as trace_model
from factory.trace.validation_status import load_validation

pytestmark = pytest.mark.unit


def _write_sr(root, req_id, *, binding=True, statement="s"):
    """Helper: write a requirements/SR file and return its id."""
    req_dir = root / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    binding_yaml = (
        f"binding:\n  experiment: e\n  metric: m\n  assert: a\n  harness: h\n"
        if binding
        else ""
    )
    (req_dir / f"{req_id}.md").write_text(
        f"---\nid: {req_id}\ntitle: T\nstatement: {statement}\ndomain: d\n"
        f"{binding_yaml}---\nbody\n",
        encoding="utf-8",
    )
    return req_id


def test_readiness_weak_when_sr_unbound(tmp_path):
    sr = _write_sr(tmp_path, "SR-001", binding=False)
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    (bundles / "b1.json").write_text(
        f'{{"id": "b1", "label": "B1", "members": ["sr:{sr}"]}}', encoding="utf-8"
    )

    rows = health.bundle_readiness(tmp_path)
    assert rows["b1"].readiness == "weak"
    assert rows["b1"].bound == 0
    assert rows["b1"].sr_total == 1
```

- [x] **Step 2: Run test to verify it fails** (`ModuleNotFoundError: No module named 'factory.system.health'`).
- [x] **Step 3: Implement** — first the signal helper, then readiness:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from factory.system import bundles as bundles_module
from factory.requirements import register as register_module
from factory.trace import gaps as gaps_module
from factory.trace import model as trace_model
from factory.trace.validation_status import SrStatus, load_validation


@dataclass(frozen=True)
class SrFlags:
    req_id: str
    bound: bool
    covered: bool
    current: bool
    deferred: bool
    validated: bool


@dataclass(frozen=True)
class BundleReadinessRow:
    id: str
    label: str
    readiness: str                # "strong" | "medium" | "weak"
    sr_total: int
    bound: int
    covered: int
    current: int
    deferred: int
    validated: int
    members: int
    recency_iso: str | None

    @property
    def readiness_counts(self) -> dict[str, int]:
        return {
            "sr_total": self.sr_total,
            "bound": self.bound,
            "covered": self.covered,
            "current": self.current,
            "deferred": self.deferred,
            "validated": self.validated,
        }


def _sr_flags(root: Path, req_id: str, sr_gaps: dict[str, list[gaps_module.Gap]],
              validation: dict[str, SrStatus]) -> SrFlags:
    """Per-SR readiness signals from register, gaps and validation only."""
    req = next((r for r in register_module.load_register(root / "requirements")
                if r.id == req_id), None)
    # `bound` = a decided binding (register) that is not proposed in the trace.
    proposed = any(g.kind == "sr_proposed" for g in sr_gaps.get(req_id, []))
    bound = req is not None and req.binding is not None and not proposed
    # `covered` = at least one non-exempt satisfying task (no pending sr_unsatisfied).
    covered = not any(
        g.kind == "sr_unsatisfied" and g.disposition != "exempt"
        for g in sr_gaps.get(req_id, [])
    )
    # `current` = not proposed: the SR has a decided binding. Staleness is
    # carried by `validated`, not by `current` (ruled during Task 1).
    current = req is not None and req.binding is not None
    deferred = any(g.disposition == "deferred" for g in sr_gaps.get(req_id, []))
    status = validation.get(req_id)
    validated = status is not None and status.state == "passed" and not status.stale
    return SrFlags(req_id, bound, covered, current, deferred, validated)


def bundle_readiness(root: Path) -> dict[str, BundleReadinessRow]:
    """Readiness per bundle id, keyed by id. Pure predicate over recorded signals."""
    nodes = trace_model.load_nodes(root)
    edges = trace_model.build_edges(nodes) if hasattr(trace_model, "build_edges") else []
    # fall back to loading edges via the loader used by trace status
    if not edges:
        from factory.trace import graph as graph_module
        edges = graph_module.build_graph(root, load_nodes=nodes) if hasattr(graph_module, "build_graph") else []
    validation = load_validation(root)
    gaps = gaps_module.find_gaps(nodes, edges, validation)
    sr_gaps: dict[str, list[gaps_module.Gap]] = {}
    for g in gaps:
        sr_gaps.setdefault(g.node_id, []).append(g)

    by_id = {n.id: n for n in nodes}
    rows: dict[str, BundleReadinessRow] = {}
    for bundle in bundles_module.list_bundles(root / "bundles"):
        srs = [m.ref.partition(":")[2] for m in bundle.members
               if m.ref.startswith("sr:")]
        flags = [_sr_flags(root, r, sr_gaps, validation) for r in srs]
        if not flags:
            rows[bundle.id] = BundleReadinessRow(
                bundle.id, bundle.label, "weak", 0, 0, 0, 0, 0, 0, len(bundle.members), None)
            continue
        if all(f.covered and f.current and f.validated for f in flags):
            readiness = "strong"
        elif all(f.bound and f.covered for f in flags):
            readiness = "medium"
        else:
            readiness = "weak"
        rows[bundle.id] = BundleReadinessRow(
            id=bundle.id,
            label=bundle.label,
            readiness=readiness,
            sr_total=len(flags),
            bound=sum(f.bound for f in flags),
            covered=sum(f.covered for f in flags),
            current=sum(f.current for f in flags),
            deferred=sum(f.deferred for f in flags),
            validated=sum(f.validated for f in flags),
            members=len(bundle.members),
            recency_iso=None,
        )
    return rows
```

> The `build_edges`/`build_graph` fallback is resolved by the implementer against the
> exact edge-loading API in `factory.trace.graph` / `factory.trace.model` — read the
> module and use the real loader (do **not** invent a signature). The test only needs
> `find_gaps` to run with the loaded edges.

- [x] **Step 4:** Add tests for Strong and Medium:

```python
def test_readiness_strong_when_all_current_covered_validated(tmp_path, monkeypatch):
    sr = _write_sr(tmp_path, "SR-002", binding=True)
    _write_sr(tmp_path, "SR-003", binding=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "b2.json").write_text(
        '{"id": "b2", "label": "B2", "members": ["sr:SR-002", "sr:SR-003"]}',
        encoding="utf-8",
    )
    # A satisfying task so `covered` is true; passing non-stale validation.
    _write_task_satisfying(tmp_path, "T-001", "SR-002")
    _write_task_satisfying(tmp_path, "T-002", "SR-003")
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid: True)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b2"].readiness == "strong"


def test_readiness_medium_when_validation_missing(tmp_path, monkeypatch):
    sr = _write_sr(tmp_path, "SR-004", binding=True)
    _write_task_satisfying(tmp_path, "T-003", "SR-004")
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "b3.json").write_text(
        '{"id": "b3", "label": "B3", "members": ["sr:SR-004"]}', encoding="utf-8")
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid: False)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b3"].readiness == "medium"
```

For these tests, extract the validation lookup into a small module-level helper
`_validation_passing(root, sr_id) -> bool` (used by `_sr_flags`), so a test can
substitute it without a real validation report:

```python
def _validation_passing(root: Path, req_id: str, validation: dict[str, SrStatus] | None = None) -> bool:
    status = (validation or load_validation(root)).get(req_id)
    return status is not None and status.state == "passed" and not status.stale
```

and `_sr_flags` calls `health._validation_passing(root, req_id, validation)`.

- [x] **Step 5:** Run the full suite + lint:
  `cd pi-agent-factory && uv run python -m pytest -q -m 'unit or integration' && uv run python -m ruff check .`
- [x] **Step 6:** Commit `feat(system): bundle readiness predicate (strong/medium/weak)`.

---

## Task 2: `factory.system.health.query_health` — the composed projection

**Files:** `src/factory/system/health.py`, `tests/unit/system/test_health.py`

Compose `compute_health` + `bundle_coverage` + `ordered_bundle_ids` + readiness into the
browser's single landing document. No duplicated logic.

- [x] **Step 1: Failing test** — `query_health` payload carries every key the browser renders:

(This task also folds in the Task 1 quality note: hoist the per-SR `load_register`/`load_validation` loads in `bundle_readiness` so they are parsed once, not once per member SR — same public behaviour, same tests green.)

```python
from factory.system import health
from factory.trace.health import compute_health
from factory.system.coverage import bundle_coverage
from factory.system.ordering import FixedRecency


def test_query_health_shapes_the_landing_payload(tmp_path):
    _write_sr(tmp_path, "SR-001", binding=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "b1.json").write_text(
        '{"id": "b1", "label": "B1", "members": ["sr:SR-001"]}', encoding="utf-8")
    payload = health.query_health(tmp_path)
    assert payload["sr_listed"] is False
    assert {"health", "coverage", "bundles", "unbundled", "ordering_available", "degraded"} <= payload.keys()
    by_id = {b["id"]: b for b in payload["bundles"]}
    assert by_id["b1"]["readiness"] in ("strong", "medium", "weak")
    assert "readiness_counts" in by_id["b1"]
```

- [x] **Step 2: Run test to verify it fails**.
- [x] **Step 3: Implement** — add to `health.py`:

```python
from factory.system.coverage import bundle_coverage
from factory.system.ordering import GitRecency, ordered_bundle_ids
from factory.trace.gaps import find_gaps
from factory.trace.health import compute_health
from factory.trace.model import load_nodes, build_edges
from factory.trace.validation_status import load_validation


def query_health(root: Path) -> dict:
    """The single JSON document the browser renders as the landing page."""
    nodes = load_nodes(root)
    edges = build_edges(nodes)
    validation = load_validation(root)
    gaps = find_gaps(nodes, edges, validation)
    health = compute_health(nodes, gaps)
    cov = bundle_coverage(root)
    order, ordering_available = ordered_bundle_ids(root, GitRecency())
    rows = bundle_readiness(root)
    degraded: list[str] = []
    if not ordering_available:
        degraded.append("git unavailable: bundle ordering fell back to id ascending")

    ordered_rows = []
    for bundle_id in order:
        row = rows.get(bundle_id)
        if row is None:
            continue
        d = {"id": row.id, "label": row.label, "readiness": row.readiness,
             "readiness_counts": row.readiness_counts, "members": row.members}
        ordered_rows.append(d)
    # bundles not in git order (e.g. no git) append by id
    for bundle_id in sorted(rows.keys() - set(order)):
        row = rows[bundle_id]
        ordered_rows.append({"id": row.id, "label": row.label, "readiness": row.readiness,
                             "readiness_counts": row.readiness_counts, "members": row.members})

    return {
        "health": {
            "classes": [{"name": c.name, "satisfied": c.satisfied,
                         "expected": c.expected, "exempt": c.exempt} for c in health.classes],
            "satisfied": health.satisfied,
            "expected": health.expected,
            "percent": health.percent,
            "dangling": health.dangling,
            "deferred": health.deferred,
            "proposed": health.proposed,
        },
        "coverage": {
            "total": cov.total, "bundled": cov.bundled,
            "unbundled": cov.unbundled,
            "kinds": [{"kind": k.kind, "total": k.total, "bundled": k.bundled,
                       "unbundled": k.unbundled} for k in cov.kinds],
        },
        "bundles": ordered_rows,
        "unbundled": {k.kind: k.unbundled for k in cov.kinds},
        "ordering_available": ordering_available,
        "sr_listed": False,
        "degraded": degraded,
    }
```

- [x] **Step 4:** Add an ordering test using `FixedRecency` by injecting into
  `query_health(repo_root, recency_source=None)`:

```python
from factory.system.ordering import FixedRecency


def test_query_health_orders_by_recency(tmp_path):
    _write_sr(tmp_path, "SR-001", binding=True)
    _write_sr(tmp_path, "SR-002", binding=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "older.json").write_text(
        '{"id": "older", "label": "O", "members": ["sr:SR-001"]}', encoding="utf-8")
    (tmp_path / "bundles" / "newer.json").write_text(
        '{"id": "newer", "label": "N", "members": ["sr:SR-002"]}', encoding="utf-8")
    recency = FixedRecency({
        (tmp_path / "requirements" / "SR-001.md"): "2026-01-01T00:00:00Z",
        (tmp_path / "requirements" / "SR-002.md"): "2026-02-01T00:00:00Z",
    })
    payload = health.query_health(tmp_path, recency_source=recency)
    ids = [b["id"] for b in payload["bundles"]]
    assert ids == ["newer", "older"]
```

Implement by threading `recency_source` through `query_health` (default `GitRecency()`)
and `ordered_bundle_ids(root, recency_source)`.

- [x] **Step 5:** full suite + lint.
- [x] **Step 6:** Commit `feat(system): composed health projection for the landing page`.

---

## Task 3: `bundles_containing` + `list_scopes` drops `sr:`

**Files:** `src/factory/system/bundles.py`, `src/factory/system/queries.py`,
`tests/unit/system/test_bundles.py`, `tests/unit/system/test_queries.py`

- [x] **Step 1: Failing tests** — `bundles_containing` returns every bundle that declares
  the ref (multi-membership), `[]` for a ref in none; `list_scopes` no longer emits `sr:`
  but `parse_scope_ref("sr:SR-007")` still resolves:

```python
def test_bundles_containing_multi_membership(tmp_path):
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "a.json").write_text(
        '{"id": "a", "label": "A", "members": ["sr:SR-001"]}', encoding="utf-8")
    (tmp_path / "bundles" / "b.json").write_text(
        '{"id": "b", "label": "B", "members": ["sr:SR-001", "sr:SR-002"]}', encoding="utf-8")
    assert bundles_containing(tmp_path, "sr:SR-001") == ["a", "b"]
    assert bundles_containing(tmp_path, "sr:SR-999") == []


def test_list_scopes_omits_sr_but_parse_resolves(tmp_path):
    from factory.system.queries import list_scopes, parse_scope_ref
    kinds = {s.kind for s in list_scopes(tmp_path)}
    assert "sr" not in kinds
    ref = parse_scope_ref("sr:SR-007")
    assert ref.kind == "sr"
```

- [x] **Step 2: Run to verify they fail** (currently `sr` IS listed; `bundles_containing` undefined).
- [x] **Step 3: Implement** — in `bundles.py`:

```python
from factory.system.coverage import member_target


def bundles_containing(repo_root: Path, ref: str) -> list[str]:
    """Bundle ids that declare `ref` as a member, deterministic (load) order."""
    target = member_target(repo_root, ref)
    containing: list[str] = []
    for bundle in list_bundles(repo_root / "bundles"):
        for m in bundle.members:
            if m.ref == ref or (target is not None and member_target(repo_root, m.ref) == target):
                containing.append(bundle.id)
                break
    return containing
```

In `queries.py`, remove the register loop from `list_scopes` (lines ~1252–1254) so it
emits `bundle:` and `adr:` only. `_SCOPE_KINDS` and `parse_scope_ref` are unchanged —
`sr:` remains openable, just unlisted.

- [x] **Step 4:** Update any existing test asserting `sr:` appears in `list_scopes` to
  assert the opposite; run full suite + lint.
- [x] **Step 5:** Commit `feat(system): sr scopes leave the sidebar; bundles_containing`.

---

## Task 4: CLI `health --json` and `memberships <ref>`

**Files:** `src/factory/system/cli.py`, `tests/unit/system/test_cli.py`

- [x] **Step 1: Failing test** — the subcommands exist and shape their output:

```python
def test_health_subcommand(tmp_path, capsys):
    from factory.system import cli, health
    _write_sr(tmp_path, "SR-001", binding=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "b1.json").write_text(
        '{"id": "b1", "label": "B1", "members": ["sr:SR-001"]}', encoding="utf-8")
    rc = cli.main(["--repo-root", str(tmp_path), "health", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "bundles" in out and "health" in out


def test_memberships_subcommand(tmp_path, capsys):
    from factory.system import cli
    cli.main(["--repo-root", str(tmp_path), "memberships", "sr:SR-001", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["ref"] == "sr:SR-001"
    assert isinstance(out["bundles"], list)
```

- [x] **Step 2: Run to verify they fail**.
- [x] **Step 3: Implement** — add handlers after `cmd_coverage`:

```python
def cmd_health(repo_root: Path, recency_source=None) -> dict:
    return health_module.query_health(repo_root, recency_source=recency_source)


def cmd_memberships(repo_root: Path, ref: str) -> dict:
    return {"ref": ref, "bundles": bundles_module.bundles_containing(repo_root, ref)}
```

Add module aliases (`from factory.system import health as health_module`, and
`bundles` already imported as `bundles_module` — check existing import name). Register
subcommands and dispatch in `main()`:

```python
    p_health = sub.add_parser("health", parents=[common])
    p_memberships = sub.add_parser("memberships", parents=[common])
    p_memberships.add_argument("ref")
```

and in the dispatch chain:

```python
        elif args.cmd == "health":
            result = cmd_health(args.repo_root)
            rendered = json.dumps(result, indent=2)
        elif args.cmd == "memberships":
            result = cmd_memberships(args.repo_root, args.ref)
            rendered = json.dumps(result, indent=2)
```

>`--json` is already in the common parent; for text mode, `health` prints the ready
>summary. Match `_render_*` conventions: when `args.json` is set, `_render_*` returns
>JSON; otherwise text. Verify how `main()` decides text-vs-json by reading the tail of
>`main()` and use the same mechanism for `health`/`memberships`.

- [x] **Step 4:** full suite + lint.
- [x] **Step 5:** Commit `feat(system): health --json and memberships subcommands`.

---

## Task 5: Split `system-page.ts` into shell / renderers / bootstrap (behaviour-preserving)

**Files:** Create `pi-ext/factory-watch/src/system-shell.ts`,
`pi-ext/factory-watch/src/system-renderers.ts`, `pi-ext/factory-watch/src/system-bootstrap.ts`;
Modify `pi-ext/factory-watch/src/system-page.ts`, `docs-server.ts`.

This task is a **mechanical move with zero behaviour change** — the split is verified by
the existing DOM tests staying green at each commit, exactly as the decomposition requires.

- [x] **Step 1: Read the seams.** In `system-page.ts`:
  - lines 1–~171: the `renderSystemPageHtml()` shell + CSS + HTML template.
  - line ~172: `(async () => {` … end: the client script containing `showBanner`,
    `clear`, `setLoading`, the `render*` per-tab functions, and the scope-loading logic.
- [x] **Step 2: Create `system-shell.ts`** — move `renderSystemPageHtml()` and its
  template/CSS verbatim. It must render the same HTML string exactly as today (the DOM
  tests parse that string). Export `renderSystemPageHtml`.
- [x] **Step 3: Create `system-renderers.ts`** — move the per-tab DOM renderers
  (`renderBrief`, `renderMatrix`, `renderTimeline`, `renderGuide`, `renderStory`,
  `renderReverse`, `renderTrace`, and their helpers) verbatim, exporting each.
- [x] **Step 4: Create `system-bootstrap.ts`** — move the client IIFE body: the
  `document.getElementById` grabs, tab wiring, `loadScope`, and the calls into the
  renderers. Import the renderers from `./system-renderers.js`.
- [x] **Step 5: Rewrite `system-page.ts`** as a thin re-export so `docs-server.ts:27`
  keeps importing it:

```ts
export { renderSystemPageHtml } from "./system-shell.js";
```

  `docs-server.ts` still calls `renderSystemPageHtml()` to produce the page; the inline
  script tag in the shell must now point at the assembled client bundle. Update
  `docs-server.ts` only to serve the new client modules (check how the inline script is
  injected today and mirror the package's existing module-serving mechanism — the DOM
  tests import `renderSystemPageHtml` directly and do not need this).
- [x] **Step 6:** This step stages the move so behavior is pinned. Run the browser tests:
  `cd pi-ext/factory-watch && npx vitest run test/system-page-dom.test.ts test/system-page-navigation.test.ts test/system-page-sidebar.test.ts test/system-page-trace.test.ts test/system-page-implementation-summary.test.ts`
  **All must stay green** — they are the verification that the split changed nothing.
- [x] **Step 7:** If any renderer is not exercised by the DOM tests, add a small
  regression assertion to `system-page-dom.test.ts` for it (the tests are the seam
  guarantee). Run the full vitest suite.
- [x] **Step 8:** Commit `refactor(system): split system-page.ts into shell/renderers/bootstrap`.

---

## Task 6: Landing page — health summary from the `health` payload

**Files:** `pi-ext/factory-watch/src/system-bootstrap.ts`,
`pi-ext/factory-watch/test/system-landing.test.ts`

The browser now fetches `health` on load (no scope chosen) and renders the landing page:
`#content` is shown, carrying the health summary + bundle list + existing tabs.

- [x] **Step 1: Failing test** — the landing renders a health summary from a fixture
  payload before any scope is chosen, with the `1/1` denominator shown verbatim (not a
  checkmark):

```ts
import { JSDOM } from "jsdom";
import { describe, expect, test } from "vitest";
import { renderSystemPageHtml } from "../src/system-shell.js";

const HEALTH = {
  health: { classes: [{ name: "SR validated", satisfied: 1, expected: 1, exempt: 0 }],
            satisfied: 1, expected: 1, percent: 100, dangling: 0, deferred: 0, proposed: 0 },
  coverage: { total: 4, bundled: 4, unbundled: [], kinds: [] },
  bundles: [],
  unbundled: {},
  ordering_available: true, sr_listed: false, degraded: [],
};

async function renderWithHealth(fixture: any) {
  const dom = new JSDOM(renderSystemPageHtml(), { runScripts: "dangerously", url: "http://localhost/" });
  // stub the fetch that bootstrap uses for health
  (dom.window as any).fetch = async () => ({
    ok: true, json: async () => fixture,
  });
  await new Promise((r) => setTimeout(r, 0));
  return dom.window.document;
}

test("landing shows the health summary with a verbatim small denominator", async () => {
  const doc = await renderWithHealth(HEALTH);
  const summary = doc.querySelector("#healthSummary");
  expect(summary).not.toBeNull();
  expect(summary!.textContent).toContain("SR validated");
  expect(summary!.textContent).toContain("1/1");
});
```

- [x] **Step 2: Run to verify it fails**.
- [x] **Step 3: Implement** — in `system-bootstrap.ts`, add a `loadHealth()` that fetches
  `health` and renders a `#healthSummary` node (percent + each class rendered verbatim via
  `createTextNode`, e.g. `"SR validated 1/1"`). Show `#content` on load when no scope is
  chosen; keep `#content` hidden-state semantics for focus mode unchanged.
- [x] **Step 4:** Add an assertion the landing shows the bundle list container and the
  navigation tabs when `bundles` is non-empty.
- [x] **Step 5:** vitest + full Python suite + lint.
- [x] **Step 6:** Commit `feat(system): health landing summary`.

---

## Task 7: Feature-first sidebar — grouping, readiness+counts, unbundled remainder, search

**Files:** `pi-ext/factory-watch/src/system-bootstrap.ts`,
`pi-ext/factory-watch/test/system-landing.test.ts`

- [x] **Step 1: Failing tests** —
  - bundles group under Weak/Medium/
Strong in payload order; Weak expanded, others collapsed but count-bearing;
  - the readiness label never renders alone (always beside its counts);
  - the unbundled remainder is visible, not hidden;
  - the search control resolves a bundle label and a bare artifact ref and posts the
    exact ref (stub the fetch that resolves it).

```ts
test("sidebar groups bundles by readiness with counts beside the label", async () => {
  const doc = await renderWithHealth({
    ...HEALTH, sr_listed: false,
    bundles: [
      { id: "b1", label: "B1", readiness: "weak",
        readiness_counts: { sr_total: 4, bound: 0, covered: 0, current: 0, deferred: 1, validated: 0 }, members: 4 },
      { id: "b2", label: "B2", readiness: "strong",
        readiness_counts: { sr_total: 2, bound: 2, covered: 2, current: 2, deferred: 0, validated: 2 }, members: 2 },
    ],
    unbundled: { sr: ["sr:SR-999"] },
  });
  const sidebar = doc.querySelector("#scopeList")!;
  const weak = sidebar.querySelector('[data-readiness="weak"]');
  expect(weak!.textContent).toContain("B1");
  expect(weak!.textContent).toContain("4 SR");
  expect(weak!.textContent).toContain("0 bound");
  expect(sidebar.textContent).toContain("sr:SR-999");
});

test("search resolves a bare artifact ref", async () => {
  let posted: string | undefined;
  const dom = new JSDOM(renderSystemPageHtml(), { runScripts: "dangerously", url: "http://localhost/" });
  (dom.window as any).fetch = async (url: string) => {
    if (String(url).endsWith("/health")) return { ok: true, json: async () => HEALTH };
    posted = String(url);
    return { ok: true, json: async () => ({ scope: { kind: "sr", ref: posted } }) };
  };
  await new Promise((r) => setTimeout(r, 0));
  const doc = dom.window.document;
  const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
  input.value = "SR-137";
  input.dispatchEvent(new dom.window.Event("input"));
  // submit triggers a resolve of the exact ref
  doc.querySelector<HTMLElement>("#searchGo")!.click();
  await new Promise((r) => setTimeout(r, 0));
  expect(posted).toBe("sr:SR-137");
});
```

- [x] **Step 2: Run to verify they fail**.
- [x] **Step 3: Implement** — in `system-bootstrap.ts`:
  - render the sidebar from `payload.bundles`, grouping by `readiness` in the order the
    payload gives (Weak, then Medium, then Strong — the payload is already ordered by
    recency within group); never `.sort()` client-side;
  - each bundle row shows the label and a `readiness_counts` line built with
    `createTextNode` (e.g. `4 SR · 0 bound`);
  - render the `unbundled` group at the bottom, visible;
  - add `#scopeFilter` search that matches bundle labels and bare refs; a match for a
    bare ref (`SR-137` → `sr:SR-137`) posts the exact ref to the docs-server scope
    endpoint to open it. Normalise a typed ref exactly as today's resolver does
    (prepend the right kind prefix for a bare id); do not do fuzzy matching.
- [x] **Step 4:** vitest + full suite + lint.
- [x] **Step 5:** Commit `feat(system): feature-first sidebar with readiness and search`.

---

## Task 8: Member-of affordance on requirement and task pages

**Files:** `src/factory/system/bundles.py` (done in Task 3), `src/factory/system/queries.py`,
`pi-ext/factory-watch/src/system-bootstrap.ts`, `pi-ext/factory-watch/test/system-membership.test.ts`

- [x] **Step 1: Failing test (Python)** — the brief for a `sr:`/`task:` scope carries the
  bundles that contain it:

```python
def test_brief_includes_member_bundles(tmp_path):
    from factory.system import queries
    _write_sr(tmp_path, "SR-001", binding=True)
    (tmp_path / "bundles").mkdir()
    (tmp_path / "bundles" / "b1.json").write_text(
        '{"id": "b1", "label": "B1", "members": ["sr:SR-001"]}', encoding="utf-8")
    brief = queries.query_brief(tmp_path, queries.parse_scope_ref("sr:SR-001"))
    assert brief["member_of"] == ["b1"]
```

- [x] **Step 2: Run to verify it fails**.
- [x] **Step 3: Implement** — `query_brief` adds a `member_of` key for `sr:`/`task:`
  scopes via `bundles.bundles_containing(repo_root, f"{scope.kind}:{scope.ref}")`. For
  other kinds it is absent. Do not touch the claim/render plumbing.
- [x] **Step 4: Failing test (browser)** — the brief renders the member-of list:

```ts
test("requirement brief lists its member bundles", async () => {
  const dom = new JSDOM(renderSystemPageHtml(), { runScripts: "dangerously", url: "http://localhost/" });
  (dom.window as any).fetch = async (url: string, init?: any) => {
    if (String(url).includes("/brief")) {
      return { ok: true, json: async () => ({
        scope: { kind: "sr", ref: "sr:SR-001" },
        member_of: ["b1", "gamma"],
        claims: [], degraded: false, degraded_reasons: [],
      }) };
    }
    return { ok: true, json: async () => HEALTH };
  };
  await new Promise((r) => setTimeout(r, 0));
  const doc = dom.window.document;
  expect(doc.querySelector("#memberOf")!.textContent).toContain("b1");
});
```

- [x] **Step 5: Implement** — `system-renderers.ts`'s `renderBrief` renders `member_of`
  into a `#memberOf` node via `createTextNode` when present; `system-bootstrap.ts` passes
  it through. Absent → no node.
- [x] **Step 6:** vitest + full suite + lint.
- [x] **Step 7:** Commit `feat(system): member-of bundles on requirement and task pages`.

---

## Task 9: Working traversal — requirement → satisfying tasks → design decisions → changed files

**Files:** `src/factory/system/queries.py`, `pi-ext/factory-watch/src/system-bootstrap.ts`,
`pi-ext/factory-watch/test/system-landing.test.ts`

Reuse the existing trace/reverse graph — do not add a parser.

- [x] **Step 1: Failing test (Python)** — a new `query_traversal(root, scope)` returns the
  core chain for a requirement:

```python
def test_traversal_chain(tmp_path):
    from factory.system import queries
    # build an sr satisfied by a task, and a design adr
    _write_sr(tmp_path, "SR-001", binding=True)
    _write_task_satisfying(tmp_path, "T-001", "SR-001")  # T-001 also source_plan: plan:P
    trav = queries.query_traversal(tmp_path, queries.parse_scope_ref("sr:SR-001"))
    assert trav["requirement"] == "SR-001"
    assert "T-001" in trav["tasks"]
    assert isinstance(trav["design"], list)
```

- [x] **Step 2: Run to verify it fails**.
- [x] **Step 3: Implement** — `queries.query_traversal(repo_root, scope)` walks the graph:
  from an `sr:` anchor, `satisfies`-in edges to tasks; from each task its `source_plan`
  to plans, the plan's `spec_ref` to a spec, and any `adr:`/design node the plan or task
  references; changed files from the reverse walk on the satisfying task. Return a plain
  dict: `{requirement, tasks, design, files}`. All values from the real graph — no
  synthesis, no invented paths.
- [x] **Step 4: Failing test (browser)** — the bundle/scope summary renders the chain as a
  linked path:

```ts
test("traversal path renders requirement -> tasks -> design -> files", async () => {
  const dom = new JSDOM(renderSystemPageHtml(), { runScripts: "dangerously", url: "http://localhost/" });
  (dom.window as any).fetch = async (url: string) => {
    if (String(url).includes("/traversal")) {
      return { ok: true, json: async () => ({
        requirement: "SR-001", tasks: ["T-001"], design: ["adr:ADR-0001"], files: ["src/a.py"],
      }) };
    }
    if (String(url).endsWith("/health")) return { ok: true, json: async () => HEALTH };
    return { ok: true, json: async () => ({ scope: { kind: "sr", ref: "sr:SR-001" }, claims: [] }) };
  };
  await new Promise((r) => setTimeout(r, 0));
  const doc = dom.window.document;
  const path = doc.querySelector("#traversalPath")!;
  expect(path.textContent).toContain("SR-001");
  expect(path.textContent).toContain("T-001");
  expect(path.textContent).toContain("src/a.py");
});
```

- [x] **Step 5: Implement** — `system-bootstrap.ts` renders `#traversalPath` for an
  `sr:`/`bundle:` scope, each hop clickable to open its scope, built with
  `createTextNode`/`textContent`.
- [x] **Step 6:** vitest + full suite + lint.
- [x] **Step 7:** Commit `feat(system): working traversal for the core use case`.

---

## Task 10: Increment gate + review handoff

- [ ] **Step 1:** run the full suites and lint in pi-agent-factory:
  `uv run python -m pytest -q -m 'unit or integration'` and `uv run python -m ruff check .`;
  and the full vitest suite in `pi-ext/factory-watch`.
- [ ] **Step 2:** run `uv run python -m factory.system health --json --repo-root <product>` in
  `cool_physical_ai_project` (editable path dependency) — confirm it renders the real
  project's health and that `sr_listed` is false.
- [ ] **Step 3:** reviewer sub-agent — read-only compliance review of SP-B against the
  design doc + decomposition SP-B section + SP-A→SP-B interface. Feed findings back as
  `T-###` fix-tasks.
- [ ] **Step 4:** update this plan's task checkboxes; note any escalation.

---

## Definition of done

- `factory.system health --json` returns the composed projection (health + coverage +
  ordered bundles + unbundled remainder + `sr_listed:false`).
- `factory.system memberships sr:SR-001` returns the containing bundles.
- Readiness is a published Python predicate; the browser never computes it and always
  renders it beside its counts.
- The `/system` landing opens on a health summary and a feature-first sidebar (Weak/Medium/
  Strong groups, unbundled visible); `sr:` is reachable by search, not by listing.
- Requirement/task pages show their member-of bundles; the core traversal renders.
- Every existing `system-page-*.test.ts` stays green (the split changed nothing); new
  `system-landing`/`system-membership` tests pass.
- `uv run python -m pytest -q -m 'unit or integration'` and `ruff check .` green; vitest green.
- No product-repo content authored; no v1 behaviour changed; no TS sorts client-side.
