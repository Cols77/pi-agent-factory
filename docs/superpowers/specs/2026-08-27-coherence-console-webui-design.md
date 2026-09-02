# Coherence Console — Web-Skin Design (feasibility + approach)

_Status: design spec (2026-08-27; read-only planning — no repo code modified)._
_Location: `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`_
_Upstream: driven by the Inc-9 programme session capture
`docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-10
COHERENCE-CONSOLE). Consumed by the Inc-9 Console slice plan + the shared-health
/ dossier / teach surfaces. Part of the coherence workflow trace spine (plan → spec →
SR)._
_Target: the interactive "Coherence Console" — a shared browser dashboard for project
health, artifact-dossier browsing, and explain/teach — served by the coherence backend
and rendered as a thin web skin. This doc answers feasibility, approach, design-system
application, thin-adapter preservation, touch points, and server-side gaps.

---

## 1. Feasibility — reusing the `/system` browser surface

**Context I grounded this in (real repo):**

- `pi-ext/factory-watch/src/mission-control-dashboard.ts` — a proven terminal-TUI
  precedent: a `Component` with `handleInput(data)` + `render(width)`, selection
  cursor (j/k/Enter/q), a `type MissionControlAction` dispatch, `colorForState`,
  `formatMissionControlRows`, `nodeActivity`, live-snippet-for-running, obligation +
  resolve-cmd rendering. It is **the proof that the TUI machinery works** but is
  **list-only** — pick a row → dispatch ONE action. No inspector/drill layer.
- Pi's UI primitives (`ctx.ui.custom` full TUI, `select/confirm/editor`, browser
  servers) and the `/system` browser navigator views (brief, matrix, timeline, guide,
  story, reverse, VDGB) — the extension already ships a real browser canvas.
- The backend canonical contracts in `src/coherence/{status.py, router.py}`, and the
  runs `/transport.py` (`ObservationEnvelope`).

**Verdict.** Reusing the `/system` browser navigator as the console **web-skin base is
feasible and strongly preferred** to building a standalone page *because*:

1. **The browser surface already exists and is host-native.** `/system` is an
   `http.Server`-style (or browser-server) tier the Pi extension already owns and the
   Hermes preview pane can mount. Reusing it means the console web skin is **additive
   tabs** on an already-served surface, not a second, disconnected web app.
2. **It preserves the thin-adapter invariant.** The web skin is pure HTML/CSS/JS
   described *declaratively* over canonical JSON; the Python backend stays authority
   and single source of truth. No model, no re-implementation.

**The coupling cost is small and bounded.** The /system navigator and the console both
render artifacts in a browser; the console adds `health` + `dossier` + `explain/teach`
as tabs on that same webview. The main NEW work is the **web DOM renderer** (a real
browser component) over the existing canonical endpoints — this is the genuinely new
artifact, not the canvas.

**What is NOT proven by the precedent (and must be new):**
- The TUI is a **list + one-action-per-Enter**. The web console needs a **real
  inspector / drill-down + multi-action** experience — that's new DOM, not a port.
- The TUI renders `resolve_cmd` as **text**. The web skin should render a real
  **action button that *executes*** the resolve via a backend-gated verb (writes a
  `.decision` / calls the same transition the MCP would). That is a new interaction.

---

## 2. Concrete approach — serve & embed

**Recommended architecture (reuses everything):**

```
[Python backend]  --canonical JSON-->  [pi-ext browser-server / /system webview]
        ^   /health, route, status, obligations, NC-*, observation            |
        |   all served declaratively                                          v
    single source of truth                              [Coherence Console web skin]
                                                       tabs: HEALTH | DOSSIER | EXPLAIN
```

- **Server:** reuse the existing browser-server tier in `pi-ext/factory-watch` that
  backs `/system`. Serve the console as an HTML page that the same server mounts as an
  additional route (e.g. `/coherence-console`). Hermes opens this in its preview pane;
  Pi opens it via its native browser-open command. **One page, two hosts.**
- **Contract:** the skin reads from the canonical objects already emitted by the
  backend. Add NO new backend authority — only a thin, terminal JSON endpoint if one is
  missing (see §6); never host-side logic.
- **Tabs:** `HEALTH` (health gauge + worst-first list), `DOSSIER` (feature-walkview),
  `EXPLAIN` (teach panel). Each renders the same canonical state through design-system
  tokens (§3).

---

## 3. Design-system application (coherence-branded, `popular-web-designs` tokens)

Objective: the console feels like Stripe/Linear/Vercel — calm, principled, high
information density — with the coherence accent. Token mapping:

| Token | Value | Used for |
|---|---|---|
| `--accent` | brand (e.g. `#6366f1` indigo / coherence blue) | active tab, primary action, health-gauge arc, focus ring |
| `--surface` | layered grey scale (`#0f1115` → `#1a1d24`) | page bg, cards (elevated cards `#232733`) |
| `--border` | `1px solid rgba(255,255,255,0.08)` | dividers, card edges |
| `--text` / `--muted` | near-white / `#9aa0ae` | body/caption |
| `--success / --warning / --error` | green / amber / red | health-dim state colors (reuse TUI `colorForState`) |
| `--radius`, `--space-*`, `--font` | PRINCIPLED radii/spacing/system font stack | panel & spacing rhythm |

**Component sketch — Health gauge card (pseudo-DOM + CSS annotations):**

```html
<section class="health-gauge" role="group" aria-label="coherence health">
  <div class="card" style="--surface:var(--surface); border:var(--border); radius:12px">
    <header class="card-row">
      <h3 class="title">Project health</h3>
      <span class="badge tone-${worstState}">worst: executed_evidence <em>0/1</em></span>
    </header>
    <!-- radial gauge -->
    <svg class="gauge" viewBox="0 0 40 40">
      <circle class="track" r="16" cx="20" cy="20" stroke="var(--border)"/>
      <circle class="arc" r="16" cx="20" cy="20"
              stroke="var(--accent)" stroke-dasharray="…" stroke-linecap="round"
              transform="rotate(-90 20 20)"/>
    </svg>
    <ul class="dims"> <!-- each dim row: dot·name·state·resolve hint -->
      <li><span class="dot tone-ok"/>implementation_trace <b>2/24</b></li>
      <li><span class="dot tone-warn"/>plan->spec <b>44/78</b></li> …
    </ul>
  </div>
</section>
```

Key CSS: `--accent` drives the gauge arc + active tab; `.tone-*` reuse the TUI's
semantic color states; `--surface`/`--border` give the layered card; `--space-*` rhythm.
This is applied uniformly to HEALTH, DOSSIER, EXPLAIN chrome — one token system.

---

## 4. Thin-adapter property preserved

- The web skin is **declarative DOM over canonical JSON** — no model, no business logic.
- **Single source of truth = the Python backend.** Even interactive actions (a resolve,
  a decision) are POSTed to a backend-gated verb; the skin never computes, infers, or
  re-derives health — it renders what the backend emits (`StatusSnapshot`, `RouteMatch`,
  `ObservationEnvelope`, `NC-*`).
- Consequence (HLR-01 / D1): porting to a new host = a second thin adapter or embedding
  of the SAME page; never a second factory implementation.

---

## 5. Touch points the console ranges over (canonical contracts emitted)

| Contract | Emitted by | Console tab uses |
|---|---|---|
| `StatusSnapshot` (`coherence status --json`) | `src/coherence/status.py` | HEALTH (worst-first list, resolve cmd) |
| `RouteMatch` (`coherence route --json`) | `src/coherence/router.py` | EXPLAIN routing |
| `ObservationEnvelope` | runs `transport.py` (`src/coherence/runs/transport.py`) | dossier evidence provenance |
| `NC-*` nonconformance record | `src/factory/memory/nonconformance.py` | EXPLAIN / dossier "what blocks?" |

These are the exact canonical contracts the console skin consumes. All verified present
in the backend; the skin is a render of them.

---

## 6. Risks / gaps server-side

- **No single aggregate `/health-and-context` endpoint today.** The backend emits each
  canonical object separately. A rich console would love ONE endpoint that returns
  `{health:, status:, route:, obligations:, recent_observations:, nc:}` for a page-load.
  **Recommendation:** add a thin terminal aggregate endpoint (still Python authority;
  it's just composition, not new logic). This is the one "new" server surface.
- **Does the browser-server already subscribe?** The TUI watches live transitions
  (`transition watcher` in mission-control); the **web skin should re-use the same
  SSE/stream** (FEAT-12 LIVE-RUN-PROGRESS) so the web view updates live rather than
  polling.
- **`resolve_cmd` execution** — the web skin needs a gated POST to actually run a
  resolve. Verify the backend already exposes a transition verb; if not, add one
  (thin, read-write-backed-by-authority).

*End of spec.*