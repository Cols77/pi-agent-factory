# SP-B — System Control Center: Design

**Date:** 2026-08-12
**Program:** [System Control Center](2026-08-10-system-control-center-program-decomposition.md), sub-project B of four (A → B → C → D).
**Status:** Design. Next step is an implementation plan, then subagent execution.
**Depends on:** SP-A landed (`adr:` kind+scope, `bundle_coverage`, `ordered_bundle_ids`, coverage gate, product bundle map).

## Goal

Turn `/system` from a blank-until-chosen navigator into a **control center**: a landing
page that opens on project health, a feature-first sidebar that bottlenecks browsing
through curated bundles, a published **readiness** predicate beside every bundle, and
working traversal for the core use case (requirement → satisfying tasks → design
decisions → changed files). SP-B is the human surface SP-C's remediation tools and
v2 Inc 6's Human UI are built on.

SP-B lands **in pi-agent-factory only** (contract, projection, Python rendering data,
TypeScript). No product-repo content is authored here.

## Context — state after SP-A

SP-A shipped the data and contract layer:

- `adr:` accepted by `_parse_member_ref` (`bundles.py:49`) and openable as a scope
  (`queries._SCOPE_KINDS` at `queries.py:72` now `("bundle","sr","task","file","adr")`).
- `factory.system.coverage.bundle_coverage()` returns per-kind bundled/unbundled splits
  with deterministic unbundled refs, over `trace.model.load_nodes` + `adr.load_adrs`.
- `factory.system.ordering.ordered_bundle_ids(repo_root, git)` returns the
  recency-descending, id-ascending bundle order plus a `recency_available` flag.
- The product repo now carries the full bundle map covering every SR/task/spec/plan/ADR,
  and a `coverage --gate` in `gates.full`.

Existing pieces SP-B reuses (never re-derives):

- `factory.trace.health.compute_health(nodes, gaps)` → `Health` (classes, percent,
  dangling, deferred, proposed).
- `factory.requirements.closure.classify(...)` → per-requirement `ClosureFinding`.
- `factory.trace.gaps.find_gaps(nodes, edges, validation)` → per-SR signals
  (`sr_unsatisfied`, `sr_proposed`, `sr_unvalidated`, `sr_unvalidatable`, `sr_stale`).
- `factory.trace.validation_status.load_validation(root)` → `dict[str, SrStatus]`
  (`state`, `stale`).
- `factory.requirements.register.load_register` → `Requirement` (`binding`, `checksum`).
- The DOM tests under `pi-ext/factory-watch/test/system-page-*.test.ts` pin current
  browser behaviour; they make the `system-page.ts` split verifiable.

Two facts about `system-page.ts` shape this design:

- `renderSystemPageHtml()` (line 17) is the **shell + CSS + markup**; the client
  script is an inline `<script>` starting at line ~172 (an IIFE that grabs
  `#banner/#picker/#content`), and the per-tab renderers (`renderBrief`, `renderMatrix`,
  `renderTimeline`, `renderGuide`, `renderStory`, `renderReverse`, `renderTrace`) live in
  that same script. The split seam is exactly the one the decomposition names: shell+CSS,
  per-tab renderers, client bootstrap.
- Today the page is **blank until a scope is chosen**: `#content` is `hidden`, and the
  sidebar is a flat picker fed by `list_scopes` (`queries.py:1240`), which emits
  `bundle:` and `adr:` (SP-A) plus every `sr:`. Health is computed (`compute_health`)
  but never shown.

## Decisions

| Decision | Ruling | Rationale |
|---|---|---|
| Health payload | **One `health` projection**, composed in Python, delivered to the browser as a single JSON document. | The navigator must render the whole project view in one request; a control center that needs three round-trips to understand its own state is not a control center. |
| Projection composition | **`factory.system.health.query_health(root)`** calls `compute_health`, `classify` (per bundle's SRs, for readiness), `bundle_coverage`, and `ordered_bundle_ids`. It **duplicates no logic** — it re-shapes existing results. | SP-A→SP-B interface, and the decomposition's "composes, never re-derives". |
| Bundle readiness | **Published Python predicate** `Strong/Medium/Weak`, computed per bundle, always rendered beside the counts that produced it (e.g. `Weak · 4 SR · 0 bound`). Never a bare label. | The decomposition's "readiness a *derived* claim, never synthesized" constraint. |
| Readiness input signals | Per-SR: `bound` (binding decided), `covered` (≥1 non-exempt satisfying task), `current` (not proposed / auto-declined), `deferred` (gap disposition deferred), `validated` (passing, non-stale validation). | Every signal already exists in `register`, `gaps`, and `validation_status` — readiness is a pure predicate over them. |
| Sidebar data source | The sidebar renders **from the health payload**, not from `list_scopes`. Python supplies bundle order, readiness, counts, and the unbundled remainder. | Inherited "no client-side sort" rule + the decomposition's "bundle ordering is an output of the health projection". |
| `sr:` leaves the sidebar | `list_scopes` stops emitting `sr:` (bundles + ADRs remain). `sr:` stays an **openable** scope; search resolves a bare `SR-137`. | Decomposition: a requirement is reached through a bundle or by direct ID search. This makes the coverage gate load-bearing for navigability. |
| Search resolution | The sidebar search control resolves **bundle labels** and **bare artifact refs** (`SR-137`, `bundle:NAME`, `adr:ADR-0001`). Resolution is exact/case-sensitive, matching `parse_scope_ref`. | "Reach SR-137 without knowing its bundle". Browser renders; it does not implement matching logic beyond a filter over the payload + posting an exact ref to the docs server. |
| Landing page | `#content` is shown by default, populated from the `health` projection: health summary + bundle list + the existing tabs. Scope choice navigates into focus mode. | Replaces the blank start. |
| Landing health summary | Renders the `Health` numbers verbatim, including a **denominator-of-one ratio** without reading as success — `SR validated 1/1` renders with its tiny denominator visible, never as a green checkmark. | Decomposition open question: a `1/1` must not look like a pass. |
| Unbundled remainder | Shown, not hidden, under the bundle groups. | The unbundled set is exactly the set unreachable by browsing; hiding it would erase the reason the coverage gate exists. |
| Grouping | Bundles group under `Weak/Medium/Strong`; `Weak` expanded by default, `Medium/Strong` collapsed but count-bearing; within a group, most-recently-touched order (SP-A). | Decomposition proposed shape, confirmed here. |
| "Member of" | Every requirement and task page lists each bundle that contains it (multi-membership is otherwise invisible). Python answers `bundles_containing(root, ref)`; TS renders the list. | Roadmap consequence: a shared requirement must read as shared. |
| Traversal | A `Traversal` affordance on the bundle/reference surface renders the core chain requirement → satisfying tasks → design decisions → changed files from the trace graph + reverse walk. | SP-B's "working traversal" deliverable; reuses existing `reverse`/`trace` data, no new parser. |
| `system-page.ts` split | **Structural** split along the existing seam: `system-shell.ts`/`system-styles.ts` (shell + CSS + markup), `system-renderers.ts` (per-tab renderers), `system-bootstrap.ts` (client IIFE + landing + sidebar + search). `docs-server.ts` imports the shell. | Decomposition explicitly lifts the three-prior-plans "only edit `system-page.ts`" constraint; DOM tests pin behaviour so the split is verifiable. |

## Architecture

Python supply (all in pi-agent-factory):

```
factory.system.health      query_health(), HealthProjection, bundle readiness rows  <- new
factory.system.bundles     bundles_containing()                                     +function
factory.system.queries     list_scopes -sr, query_health thin entry, search refs    +edits
factory.system.cli         `health --json`, `memberships <ref>`                     +subcommands
pi-ext/factory-watch/src   system-shell.ts, system-renderers.ts, system-bootstrap.ts
                           system-page.ts -> thin re-export (keeps docs-server import)   (split)
```

### `factory.system.health`

New module; the only place that composes health for the browser.

```python
@dataclass(frozen=True)
class BundleReadinessRow:
    id: str
    label: str
    readiness: str                 # "strong" | "medium" | "weak"
    sr_total: int
    bound: int
    covered: int
    current: int
    deferred: int
    validated: int
    members: int
    recency_iso: str | None

@dataclass(frozen=True)
class HealthProjection:
    health: dict                   # compute_health re-shaped: classes, satisfied, expected,
                                   # percent, dangling, deferred, proposed
    coverage: dict                 # SP-A bundle_coverage re-shaped
    bundles: list[BundleReadinessRow]
    unbundled: dict[str, list[str]]   # per-kind unbundled refs (from coverage)
    ordering_available: bool
    sr_listed: bool                # False in SP-B
    degraded: list[str]            # e.g. "git unavailable: bundle ordering fell back to id"

def query_health(repo_root: Path) -> dict: ...
def bundle_readiness(repo_root: Path) -> list[BundleReadinessRow]: ...
def _sr_flags(repo_root: Path, req_id: str, stack) -> dict  # bound/covered/current/deferred/validated
```

**Readiness predicate** (per bundle, over its `sr:` members):

- **Strong** — every SR: `current` AND `covered` (≥1 non-exempt satisfying task) AND `validated` (passing, non-stale).
- **Medium** — every SR `bound` and `covered`, but at least one not `validated` (validation missing or stale).
- **Weak** — any SR `unbound`, `uncovered`, or `deferred`.

Signals per SR, all from existing sources:

| Signal | Source |
|---|---|
| `bound` | `register.load_register` → `req.binding is not None` and **not** `sr_proposed` gap |
| `covered` | **no** `sr_unsatisfied` gap with pending disposition for this SR |
| `current` | the SR has a decided binding (`register` binding present), i.e. it is not `proposed`. Staleness is carried by `validated` (non-stale), not by `current`. |
| `deferred` | `sr_proposed` gap has `deferred` disposition, or an `sr_unsatisfied`/`sr_unvalidated` gap carries `deferred` |
| `validated` | `load_validation` entry `state == "passed"` and `stale is False` |

The label never renders alone. `BundleReadinessRow.readiness` is `strong/medium/weak`,
and TS renders it with the counts (`readiness_counts = {sr_total, bound, covered,
current, deferred, validated}`) that produced it.

### `factory.system.bundles.bundles_containing`

```python
def bundles_containing(repo_root: Path, ref: str) -> list[str]:
    """Bundle ids that declare `ref` as a member. Deterministic order."""
```

Iterates `list_bundles`; resolves each member via `member_target`/ref comparison. Pure,
no cache. `sr:`/`task:`/`adr:` compared by id; `spec:`/`plan:` by resolved path.

### `queries.py` and `cli.py`

- `_SCOPE_KINDS` unchanged (`sr` still openable, just not listed).
- `list_scopes` drops the `sr:` loop — emits `bundle:` and `adr:` only. Well-formed but
  unlisted refs (`sr:SR-007`) still resolve in `parse_scope_ref` and open.
- New `query_health(repo_root)` thin entry (delegates to `factory.system.health`).
- CLI: `factory.system health --json` and `factory.system memberships <ref>`.

### Landing page payload → DOM

The `health` projection is fetched once on load and drives:
- the header **health summary** (percent + the class list, verbatim),
- the **bundle list** grouped Weak/Medium/Strong with readiness + counts,
- the **unbounded remainder** group,
- the **search** control over bundle labels and bare refs.

When a scope is opened, the existing per-tab renderers take over unchanged; only the
landing/sidebar is new.

### `system-page.ts` split

Three modules, one seam:

- `system-shell.ts` — the HTML template (shell + inline CSS) currently in
  `renderSystemPageHtml()`.
- `system-renderers.ts` — the per-tab DOM renderers (`renderBrief`, `renderMatrix`, …).
- `system-bootstrap.ts` — the client IIFE: grabs `#banner/#picker/#content`, wires tabs,
  loads scopes, and **new**: fetches `health`, renders the landing page and the
  feature-first sidebar, and handles search.

`system-page.ts` becomes a thin re-export so `docs-server.ts:27` keeps working. The split
is staged so every existing `system-page-*.test.ts` stays green at each commit.

## Error handling

| Condition | Behaviour |
|---|---|
| Git unavailable / not a repo | `ordering_available=false`, bundles sort by id ascending, payload states it. |
| A bundle fails to load | `list_bundles` already degrades it; readiness row omitted, listed in `degraded`. |
| `memberships <ref>` for a ref in no bundle | Returns `[]`, renders as "in no bundle". |
| An SR in a bundle is not in the register | Reads as `unbound`/not `current`; never raised. |
| Validation report missing/unreadable | Every SR reads `validated=false` (`load_validation` returns `{}`); readiness degrades to Medium at best, never invented. |
| Health fetch fails | Landing page shows the degraded banner + the health summary absent; tabs still render when a scope opens. |

Consistent with the navigator's standing rule: missing evidence degrades one scope (here,
the landing page), never the whole surface.

## Testing

TDD, `pytest` (`-m unit` is the default; integration commands pass `-m 'unit or
integration'`). Browser tests via `vitest` + `jsdom` (existing `system-page-*.test.ts`).

Python:

- `query_health` on a fixture repo: composes `compute_health` + `bundle_coverage` +
  ordering; the payload carries every key the browser renders; `sr_listed=false`.
- `bundle_readiness`: a Strong bundle (all current+covered+validated); a Medium bundle
  (all bound+covered, validation stale/missing); a Weak bundle (an unbound or deferred
  SR); the counts equal the signals.
- `_sr_flags` per signal: bound/covered/current/deferred/validated each derived from the
  right source (register, gaps, validation).
- `list_scopes` no longer emits `sr:` but `sr:SR-007` still parses/opens.
- `bundles_containing`: an SR in two bundles returns both; a ref in none returns `[]`.
- CLI: `health --json` shape; `memberships <ref>` output.
- Every existing `test/system-*`, `test/trace-*`, `test/requirements-*` stays green.

Browser (vitest+jsdom, mirroring `system-page-dom.test.ts`):

- Landing renders the health summary + bundle groups (Weak expanded, others collapsed but
  count-bearing) from a fixture `health` payload, before any scope is chosen.
- Sidebar order and grouping come from the payload (no client sort).
- Readiness label always appears with its counts.
- `1/1` denominator renders verbatim, not as a checkmark.
- `sr:` is absent from the sidebar fixture but reachable by search → exact ref posted.
- Member-of list renders on a requirement/task page.
- The split keeps every existing `system-page-*.test.ts` green.

## Work order

1. `factory.system.health`: `query_health` + `bundle_readiness` + `_sr_flags` (TDD).
2. `bundles_containing` in `bundles.py` (TDD).
3. `queries.list_scopes` drops `sr:`; add `query_health` entry (TDD).
4. CLI `health --json` and `memberships <ref>` (TDD).
5. `system-page.ts` structural split into shell/renderers/bootstrap, staged so DOM tests
   stay green.
6. Landing page + health summary from the `health` payload.
7. Feature-first sidebar (grouping, readiness+counts, unbundled remainder) + search.
8. Member-of affordance on requirement/task pages.
9. Traversal affordance (requirement → tasks → design decisions → changed files).
10. Full suite green (Python `-m 'unit or integration'` + lint; vitest) and review handoff.

## Out of scope

- Any write/remediation (`system_*` tools, buttons, POST routes) — SP-C.
- The business-requirement tier — SP-D.
- Any v2 surface (feat/metric/goal scopes, dossiers, `/catchup`, Human UI tabs) — v2 Inc 1–7.
- Obsidian integration (D2) and any non-additive TS behaviour change to existing tabs.

## Accepted limitations

- Readiness is a deterministic predicate over recorded signals; it cannot tell a *wrong*
  placement (an SR in a bundle it does not belong to) from a *missing* one. That is the
  same accepted limitation as SP-A's gate, and it is compensated the same way: the bundle
  map is reviewable in ADR-0003.
- A denominator-of-one `SR validated 1/1` is rendered truthfully rather than prettified;
  a human reading the control center must weigh a tiny denominator, exactly as the
  decomposition requires.
