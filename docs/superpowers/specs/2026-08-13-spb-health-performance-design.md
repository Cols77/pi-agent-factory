# SP-B Health Projection Performance Repair

**Goal:** Make `/system` render the SP-B health landing promptly for product-scale
repositories, without weakening the Python-computes/browser-renders contract or adding a
persistent cache.

## Context

On `cool_physical_ai_project`, `/api/system/health` remains pending and the browser shows
only the System Navigator shell. The health projection currently resolves each bundle member
by calling `member_target`; every `sr:` or `task:` call reloads the complete trace node set.
The product has 14 bundles and 253 members, so a single health request rescans the same
frontmatter hundreds of times. The docs server also calls its CLI through `spawnSync`, letting
one long traversal request block every other endpoint, including health.

## Design

### Per-request artifact lookup

`factory.system.coverage` will expose a small, in-memory lookup of canonical bundle-member
references to their resolved paths. Building it reads trace nodes and ADRs once. It is a local
value passed by the caller, never written to disk, retained between calls, or treated as a
derived index.

`member_target` will accept that lookup optionally. With no lookup it keeps its current public
behaviour. `bundle_coverage`, `bundles_containing`, and ordering will accept/pass the same
optional lookup so their loops do not repeatedly call `load_nodes`. `query_health` will build
one lookup and share it across coverage and ordering. Traversal will create one lookup from its
already-loaded trace nodes and reuse it while finding each SR's containing bundles.

Exact membership semantics stay unchanged: literal reference equality still wins; `spec:` and
`plan:` aliases continue to compare resolved paths; missing refs still resolve to `None`.

### Non-blocking docs endpoints

`cli-runner` will gain an asynchronous JSON CLI runner based on `spawn`. The existing
synchronous runner remains for current synchronous callers. Health and traversal will use the
new asynchronous runner, and their docs-server routes will await it. A long traversal then
holds only its own response open instead of blocking Node's event loop and starving a concurrent
health request.

### Failure handling

Async CLI failures preserve the present `CliResult` shape: launch error, non-zero exit, and
invalid JSON become `{ ok: false, error }`, so the existing 503 rendering path stays intact.
No timeout or request cancellation policy is introduced in this repair.

## Tests

- A multi-member coverage test will spy on `trace_model.load_nodes` and prove one lookup build
  serves all members.
- Health and traversal tests will prove their dependent calls receive a shared lookup.
- A docs-server test will run a deliberately delayed traversal CLI request alongside health and
  prove health responds before traversal completes.
- Existing health, bundle, system page, CLI runner, and docs-server tests remain green.

## Out of scope

- Persistent cache files, background indexing, and browser-side freshness/order/provenance
  computation.
- Changes to SP-B payload shape or rendered markup.
- Broader conversion of every docs-server endpoint to asynchronous CLI execution.
