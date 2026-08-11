# Increment 1 — Engineering Ontology + Indexing (Implementation Plan)

**Status:** Draft for written review. Tasks assume the **recommended** sides of
Open Questions **D3 (in-place), D4 (feature-file AND bundle), D5 (spec vocabulary)**.
D1/D2 do not affect this increment. Pending approval (Program §7).
**Source phase:** Engineering Context spec §37 **Phase 1 — Engineering ontology.**
**Landing repo:** `C:/coding/pi-agent-factory` (the factory); `cool_physical_ai_project`
consumes it as an editable path dependency, so it is live there as soon as committed.
**Sub-agent execution:** dev=`pi -p <increment1-prompt>`; reviewer=`pi -p <review-prompt>`
(Program §5). Escalate any deviation to a human.

## Goal

Give the artifact ontology a **feature-centric vertical slice**: new typed artifact
kinds (feature, metric, goal) and new typed edges; **design decisions are already owned by
SCC SP-A's `adr:` kind** (D6) and are consumed, not rebuilt
V-cycle traversal, and a Feature Context query — without forking v1's single
markdown parser or its claim/freshness model. Ship no human UI (Inc 6) and no
`/goal` command yet (Inc 2); this increment is the ontology + indexing backbone only.

## Global constraints (carried from Program §6)

- Extend `factory.trace.model` — never fork or re-glob a parallel parser.
- `NodeKind` and `EdgeKind` are `typing.Literal`; extend the literal, update
  `load_nodes`/`build_graph`, keep every existing kind/edge intact.
- New scopes are exact and case-sensitive (`feat:FEAT-NAV-017`, `metric:MET-004`,
  `goal:GOAL-003`) with no fuzzy fallback (`system/queries _SCOPE_KINDS`).
- On-demand projections; no SQLite in this increment (matches v1 pattern and spec §33.
  "SQLite is sufficient" but not required — introduce an index in Inc 7 only if measured).
- Malformed artifact degrades one scope, never the whole listing.
- Tests declare `pytest.mark.unit`/`integration` at module level; full suite green
  before every commit; `ruff` line-length 100.
- Do not touch TypeScript, `docs-server.ts`, `system-page.ts`, or Obsidian here.

## File structure

**Created (in pi-agent-factory):**
| File | Responsibility |
|---|---|
| `src/factory/schemas/feat.schema.json` | Feature frontmatter contract. |
| `src/factory/schemas/metric.schema.json` | Metric frontmatter contract. |
| `src/factory/schemas/goal.schema.json` | Goal frontmatter contract (v1 subset; lifecycle in Inc 2). |
| `src/factory/schemas/diag.schema.json` | Diagram frontmatter contract (D7): points at the canonical `.html` artifact. |
| (_design decisions use SCC SP-A's `adr.schema.json` — no new design schema_) | — |
| `src/factory/system/vcycle.py` | Vertical-slice traversal over the graph (definition + verification sides). |
| `src/factory/system/feature.py` | `feature_context` / dossier aggregate (pure functions over loaders). |
| `tests/unit/system/test_vcycle.py` | Task 4. |
| `tests/unit/system/test_feature.py` | Task 6. |

**Modified (in pi-agent-factory):**
| File | Change |
|---|---|
| `src/factory/trace/model.py` | `NodeKind` += `feat,metric,goal,run,diag`; `EdgeKind` += `parent_of,verified_by,demonstrates,evaluates,contains`; `_id_node` reuse; `load_nodes` globs `docs/features` (`FEAT-*.md`), `metrics` (`MET-*.md`), `goals` (`GOAL-*.md`), `docs/diagrams` (`DIAG-*.md` stubs). Design decisions come from the existing `adr:` kind (SP-A). |
| `src/factory/trace/graph.py` | read new edges from frontmatter (`parent_of`, `verified_by`, ...) in `build_graph`. |
| `src/factory/system/queries.py` | `_SCOPE_KINDS` += `feat,metric,goal,diag`; `parse_scope_ref`; `query_feature_context`; `query_vcycle`; `query_diagram`; `list_scopes` emits new kinds. |
| `src/factory/system/bundles.py` | `_MEMBER_KINDS` += `feat,metric,goal` (id-based, like `sr:`). |
| `tests/unit/trace/test_model_nodes.py`, `test_model_edges.py`, `tests/unit/system/test_queries.py`, `test_bundles.py` | add coverage for the new kinds/edges. |
| `pi-ext/factory-watch` | `NodeKind`/type-compat consumers must stay additive — confirm only, do not touch v1 UI. |

**Created in cool_physical_ai_project:** `docs/features/FEAT-NAV-017.md` (target
reacquisition), `metrics/MET-NAV-004.md`, `goals/GOAL-NAV-003.md` (declared only —
evaluation is Inc 2). Design decisions use an EXISTING ADR (SCC SP-A `docs/adr/`, e.g.
`adr:ADR-0001`-style) rather than a new `docs/designs/`. These are the spec's running
example wired to the real drone scenarios.
## Task 1: Extend the trace `NodeKind` and `load_nodes`

**Files:** `src/factory/trace/model.py`
**Interfaces:** `NodeKind = Literal["br","sr","spec","plan","task","feat","metric","goal","run"]`.
`load_nodes(root)` additionally globs `docs/features/FEAT-*.md`, `metrics/MET-*.md`,
`goals/GOAL-*.md`. Runs (`evidence/runs/RUN-*`) are loaded as nodes
in Inc 3 (needs manifest parsing), so this task only reserves the literal.

- [ ] **Step 1: Write failing tests** in `tests/unit/trace/test_model_nodes.py` (the existing
v1 trace-node test module):

```python
from factory.trace.model import load_nodes, NodeKind

def test_feature_and_metric_and_goal_kinds_are_loaded(tmp_path):
    (tmp_path / "docs/features").mkdir(parents=True)
    (tmp_path / "metrics").mkdir(parents=True)
    (tmp_path / "goals").mkdir(parents=True)
    (tmp_path / "docs/features/FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Target Reacquisition\nstatus: implemented\n---\n# FEAT\n", encoding="utf-8")
    (tmp_path / "metrics/MET-NAV-004.md").write_text(
        "---\nid: MET-NAV-004\ntitle: reacquisition_rate\n---\n# MET\n", encoding="utf-8")
    (tmp_path / "goals/GOAL-NAV-003.md").write_text(
        "---\nid: GOAL-NAV-003\ntitle: reacquire >= 90%\n---\n# GOAL\n", encoding="utf-8")

    kinds = {n.kind for n in load_nodes(tmp_path)}

    assert {"feat", "metric", "goal"} <= kinds
```

- [ ] **Step 2: Run tests, expect fail** (`NodeKind` doesn't accept `feat` type-check at
  runtime but `load_nodes` returns nothing for those globs — assert the missing kinds).
- [ ] **Step 3: Implement.** Extend the literal and add globs:

```python
NodeKind = Literal["br","sr","spec","plan","task","feat","metric","goal","run"]

# in load_nodes, after the existing sr/br/task/plan/spec globs:
    for path in _glob(root, "docs", "features", pattern="FEAT-*.md"):
        nodes.append(_id_node(path, "feat"))
    for path in _glob(root, "metrics", pattern="MET-*.md"):
        nodes.append(_id_node(path, "metric"))
    for path in _glob(root, "goals", pattern="GOAL-*.md"):
        nodes.append(_id_node(path, "goal"))
    # "run" reserved: loaded from evidence/runs/*/manifest.json in Inc 3.
```

- [ ] **Step 4:** run `uv run python -m pytest -q && uv run python -m ruff check .`.
- [ ] **Step 5:** commit `feat(trace): add feat/metric/goal node kinds` (design stays `adr:`, SP-A).

## Task 2: Extend `EdgeKind` and read V-cycle edges

**Files:** `src/factory/trace/model.py`, `src/factory/trace/graph.py`
**Interfaces:** `EdgeKind = Literal[...,"parent_of","verified_by","demonstrates","evaluates","contains"]`.
`build_graph` parses new id-list frontmatter fields (`parent_of`, `child_of`→inverse,
`verified_by`, `demonstrates`, `evaluates`, `contains`) as typed edges with the same
id-resolution discipline as `satisfies`.

- [ ] **Step 1: Failing tests** — a feature file with `contains: [NAV-REQ-021]` yields
  an edge `FEAT-NAV-017 → NAV-REQ-021` of kind `contains`; unknown id → reported via the
  graph's existing "unresolved" mechanism, never silently dropped.
- [ ] **Step 2: Implement** a shared helper:

```python
def _edge_fields(meta: dict, kind: EdgeKind, field: str) -> list[Edge]:
    return [Edge(src=str(meta.get("id")), dst=t, kind=kind)
            for t in as_str_list(meta.get(field)) if t]

def edges_from_frontmatter(src_id: str, meta: dict) -> list[Edge]:
    out = []
    for child in as_str_list(meta.get("parent_of")):
        out.append(Edge(src=src_id, dst=child, kind="parent_of"))
    for child in as_str_list(meta.get("child_of")):
        out.append(Edge(src=child, dst=src_id, kind="parent_of"))  # inverse normalisation
    for t in as_str_list(meta.get("verified_by")):
        out.append(Edge(src=src_id, dst=t, kind="verified_by"))
    for t in as_str_list(meta.get("demonstrates")):
        out.append(Edge(src=src_id, dst=t, kind="demonstrates"))   # goal -> requirement
    for t in as_str_list(meta.get("evaluates")):
        out.append(Edge(src=src_id, dst=t, kind="evaluates"))      # goal -> metric
    for t in as_str_list(meta.get("contains")):
        out.append(Edge(src=src_id, dst=t, kind="contains"))       # feature -> requirement
    return out
```

Wire into `build_graph` where other id-based edges are added (unresolved dst ids go
through the same resolution/degradation path).
- [ ] **Step 3:** full suite + lint + commit.

## Task 3: New schemas (feat / metric / goal)

**Files:** `src/factory/schemas/{feat,metric,goal}.schema.json`
Plain JSON-Schema (Draft 2020-12) following `adr.schema.json` (SP-A): `id` with pattern
(`^FEAT-[A-Z0-9-]+$`, `^MET-[A-Z0-9-]+$`, `^GOAL-[A-Z0-9-]+$`),
`title`, and per-kind required fields. `goal.schema.json` in Inc 1 only requires
`id/title/feature/requirements/metric/target` (declared); `state`/lifecycle markup is
Inc 2.

- [ ] **Step 1:** write the three schemas (validate a draft doc by hand with
  `python -m factory.validation.schema_validator`).
- [ ] **Step 2:** unit tests load the expected schema keys; commit `feat(schemas): add
  feature/metric/goal contracts`.

## Task 3b: Diagram artifact kind (`diag:`) — canonical HTML with a markdown stub (D7)

**Files:** `src/factory/trace/model.py` (kind+glob), `src/factory/schemas/diag.schema.json`,
`src/factory/system/queries.py` (`query_diagram` + `diag:` scope), `tests/unit/trace/test_model_nodes.py`.
`diag:` nodes are **markdown stubs** in `docs/diagrams/DIAG-*.md` whose frontmatter points at the
**canonical self-contained HTML** file (`diagram_file: DIAG-NAV-003.html`) produced by the
`.pi/skills/diagram-design` skill (D7). The stub keeps the single-markdown-parser reuse rule intact;
the `.html` is the rendered artifact the browser embeds/launches. TS never re-derives the graph from
the HTML.

```yaml
id: DIAG-NAV-003
kind: diag
title: Reacquisition V-cycle slice
focus: [NAV-REQ-021]        # the 1–2 nodes the accent draws the eye to
illustrates: [FEAT-NAV-017] # the feature/ADR/dossier this picture belongs to
diagram_file: DIAG-NAV-003.html
```
- [ ] **Step 1: Failing tests** — a `docs/diagrams/DIAG-NAV-003.md` stub resolves as a `diag`
  node; `illustrates:` yields an edge to its feature/ADR; the referenced `.html` exists (missing
  → recorded `scope_errors`, degraded not dropped); a `diag:` scope parses and lists.
- [ ] **Step 2: Implement** — extend the `NodeKind` literal + `load_nodes` glob for
  `docs/diagrams/DIAG-*.md` (kind `diag`); add `diag.schema.json` (id `^DIAG-[A-Z0-9-]+$`,
  `focus`, `illustrates`, `diagram_file`); wire an `illustrates` edge in `build_graph` and a
  `query_diagram(root, id)` returning the stub + resolved HTML path; add `diag:` to `_SCOPE_KINDS`.
- [ ] **Step 3:** full suite + lint + commit `feat(system): add the diagram (diag:) artifact kind`.

## Task 4: `factory.system.vcycle` — the vertical slice

**Files:** `src/factory/system/vcycle.py`, `tests/unit/system/test_vcycle.py`
**Interfaces:**
```python
@dataclass(frozen=True)
class VCycleSide:      # one horizontal band of the definition or verification side
    label: str         # e.g. "SYSTEM_REQUIREMENT", "UNIT_VERIFICATION"
    nodes: list[Node]

@dataclass(frozen=True)
class VCycleSlice:
    anchor: str        # the feat:/sr: id the slice is anchored on
    definition: list[VCycleSide]   # needs -> sys req -> sub req -> arch/design -> detail design -> code
    verification: list[VCycleSide] # system val <- sim <- integration <- unit
    goals: list[Node]; metrics: list[Node]; runs: list[Node]

def vcycle_slice(root: Path, anchor_ref: str) -> VCycleSlice
def _definition_side(graph, anchor) -> list[VCycleSide]
def _verification_side(graph, anchor) -> list[VCycleSide]
```

- [ ] **Step 1: Failing tests.** Build a small synthetic tree: an `sr:` with a
  `parent_of` child, a satisfying task, a `verified_by` test run, a `demonstrates`
  goal, an `evaluates` metric. Assert `vcycle_slice` groups the definition side
  (requirement→design→code) and verification side (goal/metric→run→test) with the
  anchor in the middle; assert missing links appear as empty sides (distinctly), not
  dropped.
- [ ] **Step 2: Implement.** Pure functions over `factory.trace.graph`:

```python
def _definition_side(graph, anchor) -> list[VCycleSide]:
    # BFS-parent / children via `parent_of`/`child_of` on requirements reachable
    # from the anchor; collect connected `design`/`adr`/`task`/`spec` nodes.
    # Returns ordered bands; a band with no nodes is still emitted (missing = distinct).

def _verification_side(graph, anchor) -> list[VCycleSide]:
    # walk `verified_by` (tests), then `demonstrates` goals, `evaluates` metrics,
    # and (Inc 3) `run` nodes; band ORDER is fixed, never sorted by anything random.

def vcycle_slice(root, anchor_ref):
    graph = build_graph(root)
    return VCycleSlice(anchor_ref,
                       _definition_side(graph, anchor_ref),
                       _verification_side(graph, anchor_ref),
                       _goals(graph, anchor_ref), _metrics(graph, anchor_ref), [])
```

- [ ] **Step 3:** full suite + lint + commit `feat(system): add the V-cycle vertical slice`.

## Task 5: `feat`/`metric`/`goal` scopes in `queries` + `bundles`

**Files:** `src/factory/system/queries.py`, `src/factory/system/bundles.py`
- [ ] **Step 1:** extend `_SCOPE_KINDS` to include `feat`, `metric`, `goal`; extend
  `parse_scope_ref` error message; extend `list_scopes` to emit `feat:`/`metric:`/`goal:`
  refs from the model and goals register.
- [ ] **Step 2:** extend `_MEMBER_KINDS` in `bundles.py` with `feat`,`metric`,`goal`
  (id-based, like `sr:`).
- [ ] **Step 3:** unit tests: refs parse; a `feat:` scope resolves in `list_scopes`;
  a bundle with `feat:FEAT-NAV-017` resolves. Full suite + lint + commit.

## Task 6: `query_feature_context` / Feature Dossier aggregate

**Files:** `src/factory/system/feature.py`, `src/factory/system/queries.py`,
`tests/unit/system/test_feature.py`
**Interfaces:**
```python
def feature_context(root: Path, feature_id: str) -> dict          # AC-01 payload
def _implementation_files(node) -> list[str]
def _recent_changes(root, feature_id, limit=5) -> list[str]       # from git log on feature's files
```

- [ ] **Step 1: Failing tests.** Build a feature with one requirement, one design,
  code path, a goal+metric, a run manifest (stub). Assert `feature_context` returns in
  ONE operation: intent, requirements, design, implementation files, verification
  status, active goals, latest simulation evidence, recent changes (spec AC-01).
- [ ] **Step 2: Implement.** Compose existing loaders — no new parser:

```python
def feature_context(root, feature_id):
    nodes = {n.id: n for n in load_nodes(root)}
    feat = nodes.get(feature_id)               # None -> ScopeNotFoundError (degraded, not raised-wide)
    graph = build_graph(root)
    slice_ = vcycle_slice(root, f"feat:{feature_id}")
    return {
        "id": feat.id, "title": feat.title,
        "intent": _purpose(feat.path),          # from file body; never invented
        "requirements": _reachable(graph, feature_id, "contains", Sr),
        "design": _reachable(graph, feature_id, "adr"),   # SCC SP-A adr: nodes
        "implementation": _implementation_files(graph),
        "verification": _verification_status(root, feature_id),   # v1 validation_status
        "goals": [n.id for n in slice_.goals],
        "latest_simulation": _latest_run(root, feature_id),        # Inc 3 fills runs
        "recent_changes": _recent_changes(root, feature_id),
    }
```

Add `query_feature_context(root, scope)` and `query_vcycle(root, scope)` to
`queries.py` (reusing `query_brief`'s claim/render plumbing).
- [ ] **Step 3:** full suite + lint + commit `feat(system): add feature-context and
  vcycle queries`.

## Task 7: Seed the drone example artifacts in cool_physical_ai_project

**Files:** `docs/features/FEAT-NAV-017.md`, `metrics/MET-NAV-004.md`,
`goals/GOAL-NAV-003.md`, and an existing/added `docs/adr/*.md` (SCC SP-A) for the
design decision
Author the spec's running example wired to this product's real scenarios
(`multiple_threats.yaml` ⇄ reacquisition). Goals are **declared only** in Inc 1
(`state: declared`) — lifecycle/evaluation is Inc 2.

- [ ] **Step 1:** write the four frontmatter artifacts (id/title/status + edges).
- [ ] **Step 2:** run `cd cool_physical_ai_project && uv run python -m factory.system scope`
  — expect `feat:FEAT-NAV-017`, `metric:MET-NAV-004`, `goal:GOAL-NAV-003` to appear; and
  `python -m factory.system brief --scope feat:FEAT-NAV-017` to render the feature
  briefing from recorded claims.
- [ ] **Step 3:** commit in cool_physical_ai_project only.

## Task 8: Increment gate + review handoff

- [ ] **Step 1:** run full gates in pi-agent-factory and cool_physical_ai_project.
- [ ] **Step 2:** reviewer sub-agent (`pi -p <review-prompt>`) — read-only compliance
  review of Inc 1 against Program §6 reuse rules + source spec AC-01/AC-10 and §5.1/§5.2
  artifact/relationship coverage. Feed findings back as `T-###` fix-tasks.
- [ ] **Step 3:** update this plan's task checkboxes; note any escalation.

## Acceptance for Increment 1

- `load_nodes` returns `feat/metric/goal` nodes with stable ids from a single
  parser (AC-10 rebuildability path holds).
- `python -m factory.system vcycle --scope feat:FEAT-NAV-017` returns a typed
  definition⇄verification vertical slice with goals/metrics.
- `python -m factory.system brief --scope feat:FEAT-NAV-017` (feature context) returns
  intent/requirements/design/implementation/verification/goals/changes in one operation.
- All existing v1 tests stay green; no TS/Obsidian touched.
