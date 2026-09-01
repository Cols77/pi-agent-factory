# Inc-09 Console Slice Plan (FEAT-10 COHERENCE-CONSOLE)

_Date: 2026-08-27._ **Planning only — no execution, no code changes, no git pushes.**
_Status: draft plan, one tracer-bullet increment. Execution order step: after health-resolution,
`11 → 9 → 12 → 10`; this is the CONSOLE (10), the web skin on the shared health/dossier surface.
Do NOT push/merge to main until the user explicitly says so.

_Design authority: `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`
(feasibility + approach). Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md`
(doc D-A…D-H; FEAT-10). Related dest: the shared browser dashboard both Pi and Hermes mount.
Prerequisite (execution-order): `docs/superpowers/plans/2026-08-27-coherence-health-resolution-plan.md`
(runs first; it creates the FEAT-10 SR + register this slice's trace edges reference).
Sibling surface: `docs/superpowers/plans/2026-08-27-coherence-inc9-dossier-slice-plan.md`
(dossier tab lands on the page this slice scaffolds)._

## 1. Objective

Replace the inert `ctx.ui.notify(<text-mission-control>)` with an **interactive Coherence Console**
web view served by the existing pi-ext browser-server + `/system` base, rendered as a thin DOM
over canonical JSON. The console is **the single shared health surface** both Pi (native) and Hermes
(preview pane) mount. It is *additive tabs* on the browser surface, NOT a standalone app.

> **Forward refs (settled):** "FEAT-12 partial" here means this slice implements only the *browser
> live-update face* of FEAT-12 (C-4); FEAT-12 as a full feature ships in its own increment. The
> "console SR" this slice's code carries edges to is **created by the health-resolution track**
> (Task T-2/T-3) — if it does not exist at slice start, create it as `SR-<FEAT-10>` before C-1.

## 2. Guiding constraints (locked)

- **Thin-adapter invariant:** the web skin consumes `StatusSnapshot`/`RouteMatch`/`ObservationEnvelope`/
  `NC-*` canonical JSON; it **never re-implements** authority. Python backend stays single source of truth.
- **One page, two hosts:** Pi opens it natively; Hermes mounts the *same* page in its preview pane.
  No two implementations of the interactive surface (the FEAT-9/10 coupling).
- **Actions are backend-gated:** a resolve / decision = POST to a backend transition verb; the skin
  never computes health.
- **Design-system quality (Part 4):** apply `popular-web-designs` style tokens (accent/surface/border/
  text/muted/status colors + radius/spacing/type) coherently to the chrome so it feels Stripe/Linear/
  Vercel-calibre while staying thin.

## 3. Slice scope (one thin tracer-bullet path through every layer)

This increment cuts **one** end-to-end vertical path, exercised per task. It does NOT build a
horizontal broad surface. The vertical: substrate → coherence backend → factory state → Pi browser
server → Hermes preview → shared console page.

### Task C-1 — Backend aggregate endpoint (thin composition, still authority)
- Add **ONE** terminal JSON aggregate endpoint that returns
  `{health:, status:, route:, obligations:, recent_observations:, nc:}` for a single page-load.
  **Composition only** — this is not new authority; it's a thin read that reuses existing canonical
  emitters (`status.py`, `router.py`, `runs/transport.py`, `memory/nonconformance.py`).
- **Files (planned):** new `src/coherence/console/aggregate.py` (thin read composition), wired into the
  existing router at `src/coherence/router.py`; codemap `satisfies`/`implements` edges to the console
  SR (created by health-resolution T-2/T-3).
- **Contract shape (reference):** `{ "health": HealthSnapshot, "status": StatusSnapshot,
  "route": RouteMatch, "obligations": Obligation[], "recent_observations": ObservationEnvelope[],
  "nc": NonconformanceRecord[] }` — field types follow the console web-skin spec §5's canonical names.
- **Verify (exact):** `curl -s localhost:<PORT>/coherence-console | jq -e '.health and .status and .route
  and .obligations and .recent_observations and .nc'` → prints `true` and exits 0.
- **Acceptance:** `/coherence-console` load is 1 read, returns all tabs' state; no authority re-implemented
  (grep the new file for any parser/decider logic — none; only composition).

### Task C-2 — Console web skin DOM components (HEALTH tab first)
- Build the DOM renderer: **Health gauge card** + **worst-first state list** + action/run affordance
  (per design spec §3 component sketch). Tabs scaffold: HEALTH active, DOSSIER/EXPLAIN visible-but-muted
  (their own slices land later — see dossier/teach).
- **Files (planned):** frontend under `pi-ext/factory-watch/src/console/` — `HealthTab.tsx`,
  `App.tsx` (tabs), `tokens.css` (adopts the design-spec §3 token table as CSS custom props); reuse
  the existing `/system` browser-server harness rather than a new app.
- **Verify (exact):** `GET /coherence-console` renders a `[data-tab="health"]` node whose gauge
  value equals `StatusSnapshot.health` from the canonical payload (headless smoke: `node -e` / a
  Playwright step in CI). Clicking a red row fires a `POST /api/coherence-console/<dim>/resolve` and
  streams the response.
- **Acceptance:** a red dimension row is actionable — clicking it issues the backend-gated resolve and
  streams the result; the UI never fabricates a claim.

### Task C-3 — Thin adapter wiring / two-host mount
- Pi: native browser-open to `/coherence-console` + status widget pointing at it.
- Hermes: same page in the preview pane (via the existing browser-server pattern + the FEAT-9
  Hermes-MCP/plugin adapter; NOT a re-implementation).
- **Files (planned):** Pi `pi-ext/factory-watch/src/commands/coherence-console.ts` (native open +
  widget); Hermes `skills/coherence-console-preview/` (or MCP tool surface) — read-only thin mount.
- **Verify (exact):** open once from Pi and once from Hermes preview; assert both render the **same**
  `/coherence-console` URL with identical body hash (e.g. `curl -s <url> | sha256sum` equal between
  the two mounts).
- **Acceptance:** both hosts show the *same* page from the same backend, no divergence.

### Task C-4 — Live-run-progress integration (FEAT-12 partial face, the motion axis)
- The web view subscribes to the existing transition/SSE stream so a run advances live (the
  `transition watcher` analog in the browser) — node transitions + artifact accumulation render
  without polling.
- **Files (planned):** backend emits the SSE stream (reuse `runs/transport.py` `ObservationEnvelope`
  channel); frontend `useLiveStream.ts` in `pi-ext/factory-watch/src/console/`.
- **Verify (exact):** start a run, `curl -N` the SSE endpoint, assert a `node:transition` event for a
  running node arrives; the DOM updates without `location.reload` (headless assertion).
- **Acceptance:** "which node is running / what has it produced" is visible in real time, no manual refresh.

## 4. Review & fix-loop (user-preferred)

- Two reviewers per task in parallel — **spec-compliance** + **code-quality/security** (fail-closed
  resolve action, no accidental authority re-implementation, no missing error path) — dispatched on
  commits; fixers in a fresh context until both silent. Then a final holistic pass over the whole slice
  (`git diff main...HEAD`) asking: is the console genuinely wired end-to-end, or is it decoration leaking
  a "dead-in-production" risk.

## 5. Traceability requirement

- Every task's produced artifact (endpoint, DOM components, host wiring) carries codemap edges to its
  SR; the slice is not healthy unless the register/obligation/test-marker gates validate those edges
  AND the reviewers saw the artifact-sufficiency. No green-by-declaration.

## 6. Definition of done

- The Coherence Console answers "what is the project health + where do I start," interactively, live,
  on one shared page that Pi and Hermes both mount — thin over canonical JSON, backend-gated actions,
  `popular-web-designs`-quality visual language, trace-linked and gate-validated. The FEAT-10 SR it
  satisfies exists (health-resolution), its code carries `satisfies`/`implements` edges, and the
  register/obligation/test-marker gates validate them; reviewers saw the artifact-sufficiency.

## 7. Files likely to change

- Backend: `src/coherence/console/aggregate.py` (new), `src/coherence/router.py` (wire),
  `src/coherence/status.py` (read, no change), `src/coherence/runs/transport.py` (SSE emit, reuse).
- Frontend (pi-ext): `pi-ext/factory-watch/src/console/{App,HealthTab}.tsx` (new), `tokens.css` (new),
  `useLiveStream.ts` (new); `pi-ext/factory-watch/src/commands/coherence-console.ts` (new).
- Hermes: `skills/coherence-console-preview/` (new thin preview mount) or MCP tool surface.
- Register/requirements: the FEAT-10 SR + bundle (from health-resolution T-2/T-3), codemap edges.

## 8. Risks & open questions

- **Backend-gated resolve verb** — an in-line POST `/api/coherence-console/<dim>/resolve` assumes the
  backend exposes a read-write `resolve_cmd` transition (spec §6 flags it may need adding). Verify it
  exists before C-2 or plan C-1 to add the verb (still authority, thin).
- **SSE transport** — the "transition watcher" analog lives in the Pi TUI; the browser SSE counterpart
  may not exist yet (spec §6). C-4 is scoped as the browser face, but confirm the stream is reusable.
- **FEAT-10 SR may not yet exist** — mitigated (created by health-resolution T-2/T-3; fallback create
  `SR-FEAT-10` before C-1), but confirm ordering at slice start.
- **Two-host parity** is a real assertion (body-hash equality) — a genuine constraint, not a given.
- **Design tokens** depend on `popular-web-designs` tokens being vendorable into `tokens.css` without
  bloat; confirm the integration is a token import, not a full design system.

## 9. Out of scope

- Dossier-browser (separate slice — the "walls of artifacts, lost where to start" system).
- Teach/explain tier (deferred — `grill-understanding` + `visual-explainer` reuse, glossary-fetch +
  topic-decomposition; parked until console + dossier land).
- Performance (D-G global constraint) and Rust/WASM roadmap.