# Inc-09 Dossier Slice Plan (FEAT-10 COHERENCE-CONSOLE — dossier surface)

_Date: 2026-08-27._ **Planning only — no execution, no code changes, no git pushes.**
_Status: draft plan, a tracer-bullet increment building the **dossier browser** on the shared
console. It is a **surface of FEAT-10** (not an independent feature), landing after the Console
health slice so it mounts as a tab on the same page. Do NOT push/merge to main unless the user
explicitly says so.

_Design authority: `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md` (§3
dossier-browser component). Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md`
(FEAT-10; §5). Consumed by: the shared health/dossier surface both Pi and Hermes mount.
Mount target: `docs/superpowers/plans/2026-08-27-coherence-inc9-console-slice-plan.md` (C-2 scaffolds
this DOSSIER tab). Prerequisite: `docs/superpowers/plans/2026-08-27-coherence-health-resolution-plan.md`
(registers the features this dossier reads). Canonical types follow the console web-skin spec §5._

## 1. Objective

Turn the "walls of artifacts, I don't know where to start" problem into a **feature-walkthrough
view**: for a chosen feature, show its coherent 7-stage chain as a single scrollable/tabbed view —
**Requirement → Obligations → Implementation (codemap/trace) → Evidence → Sim-gate → Observations →
Review/Non-conformance** — so the user can understand a feature in depth and grip what is actually
implemented. This is the "grip on the system" the user asked for.

## 2. Guiding constraints (locked)

- **Thin-adapter invariant:** the dossier view reads canonical JSON (health snapshot, obligations,
  codemap edges, NC-*); it NEVER re-implements traceability. Python backend stays single source of truth.
- **Reuse the console surface:** dossier is a **tab** on the `/coherence-console` page from the
  Console slice (C-2 scaffold has DOSSIER visible-but-muted; this slice brings it live). One page, two hosts.
- **Trace-forward and trace-backward are the two navigations:** from a requirement → its code; from
  a code file → all its SRs. Both must be first-class interactions.
- **Evidence-first, no shortcuts:** per-stage structured data, not prose claims.

## 3. Slice scope (one thin tracer-bullet through every layer)

Vertical: substrate models (obligations, ./codemap edges) → coherence reads → factory evidence →
the console dossier DOM → shared page. Build the stable dossier view only for the features that
health-resolution (the preceding track) has already registered — so a dossier is backed by a real,
evidence-verified feature, never a hollow card.

### Task D-1 — Dossier aggregate read (thin composition)
- Add a backend endpoint that, given a feature id, returns its **7-stage chain** in canonical form:
  requirements (SRs), obligations (requiredness/state/resolve), implementation (codemap
  satisfies/implements), evidence (manifests, freshness), sim-gate (scenario refs/state), observations
  (`ObservationEnvelope`), review/NC (`NC-*`/`FR-*` + closure). Composition over existing emitters —
  no new authority.
- **Files (planned):** new `src/coherence/console/dossier.py` (read composition), route
  `GET /api/coherence-console/dossier/<feature_id>` wired in `src/coherence/router.py`; response uses
  the canonical types from the console web-skin spec §5 (`Obligation`, `ObservationEnvelope`,
  `NonconformanceRecord`).
- **Verify (exact):** `curl -s localhost:<PORT>/api/coherence-console/dossier/<FEAT-id>
  | jq -e '[.requirements,.obligations,.implementation,.evidence,.sim_gate,.observations,.review_nc]
        | all(length > 0 if present)'` — returns `true` for a registered feature.
- **Acceptance:** a dossier is data-complete for its feature (all 7 stages return real data).

### Task D-2 — Dossier DOM renderer (feature-walk view)
- Build the DOSSIER tab: stage sections mapped to the canonical data; trace-forward (requirement → code)
  and trace-backward (code → SRs) navigation; per-stage structured data with freshness state.
- **Files (planned):** `pi-ext/factory-watch/src/console/DossierTab.tsx` (new), mounted on the
  console `App.tsx` tab scaffold (from Console slice C-2); reuse the shared `tokens.css`.
- **Verify (exact):** headless smoke — `GET /coherence-console#dossier` renders `[data-stage]` elements
  for all 7 stages; clicking a requirement element navigates to its codemap node (assert `data-codepath`);
  clicking a code path lists its SRs (assert `data-sr` count > 0).
- **Acceptance:** the walkthrough is navigable both directions and never fabricates a link.

### Task D-3 — Wire into console page (two-host mount)
- Mount DOSSIER tab on the shared page alongside HEALTH; confirm Pi native + Hermes preview both render it.
- **Files (planned):** the console `App.tsx` tab registry (enable the DOSSIER entry scaffolded as
  visible-but-muted in Console C-2); no new host surface — reuses the console slice's Pi/Hermes mounts.
- **Verify (exact):** open from Pi and Hermes preview → both render `/coherence-console#/dossier` with
  an identical `sha256` of the page body.
- **Acceptance:** opened from Pi and Hermes preview → identical dossier surface.

### Task D-4 — Freshness + nonconformance surfacing
- A dossier shows stale evidence (fresh/stale/refreshed-of) and any open `NC-*` for the feature, with
  closure links to `gh-issue` via the `corrects` edge.
- **Files (planned):** read `FreshnessState` from the freshness kernel (`src/substrate/freshness.py` or
  wherever it's emitted) + `NonconformanceRecord` from the `NC-*` emitter; `DossierTab.tsx` renders them.
- **Verify (exact):** `curl -s .../dossier/<FEAT> | jq '.evidence.freshness.state'` returns one of
  `fresh|stale|refreshed-of`; a feature with a real `NC-*` shows the record + its `corrects -> gh-issue` link.
- **Acceptance:** "why is this not green / what blocks it" is answerable from the dossier.

### Task D-5 — Trace-edge emission + gate for the dossier's OWN code (locked D-D)
- The dossier increment's own produced code (`.py` + `.tsx`) carries codemap `satisfies`/`implements`
  edges to its owning SR (FEAT-10's dossier sub-requirement, from health-resolution). Emit + verify those
  edges so the dossier itself is trace-linked, not just the data it renders.
- **Verify (exact):** `coherence register check` passes for the dossier code (no "no account" pending),
  and `grep -rn "satisfies.*SR-" src/coherence/console/dossier.py pi-ext/factory-watch/src/console/DossierTab.tsx`
  finds a real edge for each new file.
- **Acceptance:** the dossier slice's own artifacts are registered + gate-validated (D-D), and reviewers
  saw the artifact-sufficiency in the review node.

## 4. Review & fix-loop

Same user-preferred dual-angle review (spec-compliance + code-quality/security) per task, fresh-context
fixers until silent, then one holistic pass (`git diff main...HEAD`) checking the dossier is genuinely
data-wired (not "dead-in-production"), trace-linked, and not leaking authority into the UI.

## 5. Definition of done

The Dossier tab turns "walls of artifacts, lost" into a navigable, data-backed feature walkthrough
(Requirement → … → Review/NC) with trace-forward/backward and freshness NC surfacing — on the same
shared page both hosts mount, thin over canonical JSON, trace-linked and gate-validated (including the
dossier's own code edges via D-5).

## 6. Files likely to change

- Backend: `src/coherence/console/dossier.py` (new), `src/coherence/router.py` (wire route).
- Frontend (pi-ext): `pi-ext/factory-watch/src/console/DossierTab.tsx` (new), `App.tsx` (enable the
  DOSSIER entry scaffolded in the Console slice C-2).
- Register: the FEAT-10 dossier sub-requirement + codemap `satisfies`/`implements` edges (D-5).

## 7. Risks & open questions

- **Precedence on Console slice** — the dossier reads only features the health-resolution registered and
  mounts on the Console page scaffold; physically ordered after Console C-2 (or the tab is muted). Verify
  ordering at slice start.
- **Not every 7-stage field exists for every feature** (e.g. sim-gate absent) — render "not applicable"
  explicitly, never fabricate.
- **`FreshnessState` naming** — assumed `src/substrate/freshness.py`; confirm enum values before D-4.
- **Two-host parity** — same body-hash assertion as the Console slice; a real constraint.
- **Trace-edge emission for TSX (D-5)** — may need a path-pattern covention (e.g. `.tsx` → SR) if the
  engine is Python-symbol-only; if so, scope a minimal path-pattern for the new component files.

## 8. Out of scope

- Teach/explain tier (separate deferred surface — see console plan §9).
- Any new authority / re-implementation of traceability server-side. Purely a read+render increment.