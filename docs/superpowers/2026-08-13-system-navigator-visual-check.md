# System Navigator — Visual Check Guide

A quick, human-eyes review of the midnight evidence console that the
`feat/system-navigator-visual-identity` work (plan
`docs/superpowers/plans/2026-08-13-system-navigator-visual-identity.md`) set out
to deliver. Run this whenever you want to confirm the visual identity landed,
without re-running the whole test or Playwright gate.

> This is a **visual** check. The deterministic gates (typecheck, `npm test`,
> `pytest tests/unit/system`, and the `BROWSER_GATE=1` Playwright harness) are
> the authoritative pass/fail; this guide exists so a human can eyeball the
> finished surface in a real browser.

---

## 1. Start the navigator

The `/system` page is served by the factory-watch docs server against **the
current project** (`ctx.cwd`). To see a *populated* navigator, start `pi`
inside a repo that has evidence bundles (e.g. `C:\coding\cool_physical_ai_project`).
The factory repo itself deliberately serves the legitimate empty state (no
bundles), so you will only see the midnight shell there.

From a `pi` session in the target project:

```
/system
```

It opens in your browser at `/system` (close it later with `/system --stop`).

If you are not in a `pi` session and just want the page served against a
target repo, the simplest repeatable option is the Playwright gate below,
which boots the docs server and drives a real Chromium.

### End-to-end visual pass (Playwright gate)

This drives a real Chromium at 1440×900, 1024×768 and 390×844 against
`C:\coding\cool_physical_ai_project` and asserts everything the plan's gate
lists (landing, bundle focus, overflow, scope sheet, contextual tabs,
disclosures, Matrix, trace spine, keyboard, search, aria, Retry, reduced
motion, console errors):

```powershell
cd pi-ext/factory-watch
npm install --no-save playwright   # only if the gate has not been run here before
BROWSER_GATE=1 npx vitest run test/system-browser-validation.test.ts
```

The gate launches the **system Chrome** (`channel: "chrome"`), so no Playwright
browser download is required.

Pass means `PASS (1) FAIL (0)`; the detailed zero-finding report lands in
`C:\coding\cool_physical_ai_project\.tmp\browser-gate-report.json`.

To run it against a different repo:

```powershell
BROWSER_GATE=1 BROWSER_GATE_TARGET=C:\path\to\repo npx vitest run test/system-browser-validation.test.ts
```

---

## 2. What to look at (checklist)

Open `/system` with DevTools open (F12) at a wide desktop window (~1440 px
wide). Verify in this order.

### Landing mode
- [ ] Immediately a **midnight** console: very dark graphite/ink background
      (`#071015`), not a white SaaS dashboard. A faint cyan signal line
      (`#65d9ff`) accents focus/hover.
- [ ] A `PIF / EVIDENCE` eyebrow, the **System Navigator** title, and the lead
      copy *"Trace what the system claims, what validates it, and where the
      evidence leads."*
- [ ] A **health status** line then resolves into an "overall" metric plus one
      metric per class (task→plan, task→SR, SR satisfied, SR validated…).
- [ ] A **feature directory** below: rows that expose a human readable label, a
      readiness tag (strong/medium/weak), an "N SR" count and the readiness
      counts. These rows are real links (`/system?scope=bundle:…`).
- [ ] Body text is ≥14 px and comfortably readable; metadata/IDs use a
      monospace face.

### Focus mode (click a feature row, e.g. a "weak" bundle)
- [ ] Landing hides; the workspace shows a **scope eyebrow** (bundle scope), a
      human label, and the raw ref as monospace metadata.
- [ ] Only relevant tabs are available: **Brief, Matrix, Timeline, Guide,
      Trace** for bundle/SR scopes; **Story** for tasks; **Reverse** for files.
- [ ] Selecting a scope puts `aria-current="page"` on the matching sidebar
      link and a persistent visual highlight.
- [ ] The **trace spine** (Trace tab) renders as four labelled segments —
      **Requirement → Tasks → Design → Files** — not one run-on sentence.
- [ ] Evidence sections under a claim revert to a native `<details>` disclosure
      labelled `Evidence · N` (opening it shows the citations/spans).
- [ ] Matrix rows show a compact grid with a subject, a status badge, and a
      summary.

### Keyboard & accessibility
- [ ] Tabs are real tabs: click + **Arrow Left/Right** move focus with wrapping,
      **Home/End** jump to first/last; the active tab keeps `tabindex="0"`,
      inactive ones `tabindex="-1"`.
- [ ] Focus outlines use the **cyan accent** and stay visible on every
      focusable control.
- [ ] Tab focus (not a system caret) lands somewhere the instant you reach the
      page.

### Health failure / Retry
- [ ] Stop the docs server (or block `/api/system/health` in DevTools →
      Network → request → Right-click → Block). Reload `/system`.
- [ ] The landing stays visible and shows *"Project evidence is unavailable.
      The navigator is still running; retry the health scan."* with a
      **Retry health scan** button.
- [ ] Un-block, click Retry → health loads and the landing recounts.

### Responsive
- [ ] At ~1024 px it still reads as a two-column instrument; no horizontal
      scrollbar.
- [ ] At 390 px (Device Toolbar) it becomes one column. After picking a scope
      the rail collapses to a **Browse scopes** toggle; clicking it opens a
      **bounded sheet** above the workspace (and a Close control), never a
      300 px fixed sidebar beside the content.

### Reduced motion
- [ ] DevTools → Rendering → *Emulate CSS media feature prefers-reduced-motion:
      reduce*. Transitions/animations shrink to ~0; nothing blinks.

### No console errors
- [ ] DevTools Console shows **no red errors** (an optional `favicon.ico` 404
      is the known, benign exception).

---

## 3. "Something looks off" — first triage

| Symptom | Likely cause → check |
|---|---|
| White/light background or Purple gradients | shell tokens not applied → `src/system-shell.ts` `:root` block / tokens moved |
| Landing and workspace both show | landing/focus separation → `showLanding`/`showWorkspace` in `src/system-bootstrap.ts` |
| All 7 tabs show for every scope | contextual tabs not configured → `TABS_BY_KIND` + `configureTabs` in `src/system-bootstrap.ts` |
| Trace is one sentence, not segments | trace-spine renderer → `addStep(Requirement/Tasks/Design/Files)` in `src/system-bootstrap.ts` |
| Evidence not under a disclosure | native disclosure → the `evidence-disclosure` `<details>` in `src/system-renderers.ts` |
| `scope=sr%3ASR-137` blocked / bare `sr:` fetch | search resolution → `searchGo` (bare id gets `sr:` prefix, then exact ref) |
| No Retry on health failure | health lifecycle → `loadHealth`'s catch + `retryHealth` binding in `src/system-bootstrap.ts` |

If one of these flips, re-run the focused suite first:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-landing.test.ts test/system-page-navigation.test.ts test/system-page-dom.test.ts
```

---

## 4. Reference

- Spec: `docs/superpowers/specs/2026-08-13-system-navigator-visual-identity-design.md`
- Plan: `docs/superpowers/plans/2026-08-13-system-navigator-visual-identity.md`
- Shell/visual system: `pi-ext/factory-watch/src/system-shell.ts`
- Landing/focus, health, tabs, spine, keyboard: `pi-ext/factory-watch/src/system-bootstrap.ts`
- Claim/matrix/disclosure renderers: `pi-ext/factory-watch/src/system-renderers.ts`
- Playwright gate: `pi-ext/factory-watch/test/system-browser-validation.test.ts` (run with `BROWSER_GATE=1`)