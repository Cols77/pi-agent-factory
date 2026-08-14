# System Navigator Visual Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/system` into a responsive, highly readable midnight evidence console with distinct landing/focus modes, contextual navigation, accessible interactions, and a visual trace spine.

**Architecture:** Keep the existing shell/bootstrap/renderer split. `system-shell.ts` owns semantic markup and the visual system; `system-bootstrap.ts` owns modes, navigation, health/retry, and trace-spine orchestration; `system-renderers.ts` owns readable evidence presentation. Python remains authoritative and no JSON contract changes.

**Tech Stack:** TypeScript, vanilla DOM, inline CSS, jsdom, Vitest, existing Node HTTP server, Python 3.11+ projections.

**Starting point:** `feat/system-navigator-visual-identity` at committed performance tip `9239b20`.

---

## File responsibility map

| File | Responsibility |
|---|---|
| `pi-ext/factory-watch/src/system-shell.ts` | Semantic shell, theme tokens, typography, responsive layout, landing/workspace markup, tab/panel ARIA. |
| `pi-ext/factory-watch/src/system-bootstrap.ts` | Landing/focus state, health/retry, feature directory, sidebar, contextual tabs, keyboard behaviour, selected scope, trace spine. |
| `pi-ext/factory-watch/src/system-renderers.ts` | Claim/matrix content hierarchy and compact evidence disclosure. |
| `pi-ext/factory-watch/test/system-page-visual-identity.test.ts` | Visual, responsive, readability, and accessibility contract. |

## Task 1: Establish the semantic shell and visual system

**Files:**
- Create: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`
- Modify: `pi-ext/factory-watch/src/system-shell.ts`

- [x] **Step 1: Write failing shell contract tests**

Create the test file with this initial contract:

```ts
import { describe, expect, it } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

describe("system navigator visual identity", () => {
  const html = renderSystemPageHtml();

  it("renders distinct landing and focus workspaces immediately", () => {
    expect(html).not.toContain('<section id="content" hidden>');
    expect(html).toContain('id="landingPanel"');
    expect(html).toContain('id="scopeWorkspace" hidden');
    expect(html).toContain('id="healthStatus"');
    expect(html).toContain('id="retryHealth"');
  });

  it("defines the midnight evidence-console tokens", () => {
    expect(html).toContain("--bg: #071015");
    expect(html).toContain("--surface: #0d1a20");
    expect(html).toContain("--signal: #65d9ff");
    expect(html).toContain("--font-display:");
    expect(html).toContain("--font-mono:");
    expect(html).toContain("prefers-reduced-motion: reduce");
  });

  it("becomes one column on narrow viewports", () => {
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#tabs\s*\{[^}]*overflow-x:\s*auto/);
  });

  it("relates tabs and panels accessibly", () => {
    expect(html).toContain('id="panelBrief" class="panel" role="tabpanel" aria-labelledby="tabBrief"');
    expect(html).toContain('id="tabBrief" class="tab" role="tab" tabindex="0"');
    expect(html).toContain('id="tabMatrix" class="tab" role="tab" tabindex="-1"');
  });
});
```

- [x] **Step 2: Verify the tests fail**

Run `npx vitest run test/system-page-visual-identity.test.ts` from `pi-ext/factory-watch`.
Expected: FAIL on the new structure, tokens, mobile grid, and ARIA contract.

- [x] **Step 3: Implement explicit landing and focus markup**

Keep existing consumed IDs, but make `#content` a visible `<main>` containing:

```html
<section id="landingPanel" aria-labelledby="landingTitle">
  <div class="landing-intro">
    <div class="eyebrow">PROJECT EVIDENCE</div>
    <h2 id="landingTitle">See the system clearly.</h2>
    <p>Start with weak or unbundled features, then follow their evidence spine.</p>
  </div>
  <div id="healthStatus" class="loading-state" role="status">Reading project evidence…</div>
  <button id="retryHealth" class="secondary-action" type="button" hidden>Retry health scan</button>
  <div id="healthSummary"></div>
  <section class="feature-directory" aria-labelledby="featureDirectoryTitle">
    <div class="section-heading"><span>FEATURE DIRECTORY</span><h3 id="featureDirectoryTitle">Browse by readiness</h3></div>
    <div id="bundleList"></div>
  </section>
</section>
<section id="scopeWorkspace" hidden>
  <div class="scope-heading"><div id="scopeKind" class="eyebrow"></div><h2 id="scopeHeader"></h2><div id="scopeRef"></div></div>
  <!-- existing loading, metadata, tabs and panels -->
</section>
```

Give every panel `role="tabpanel"` and `aria-labelledby`. Give Brief `tabindex="0"` and all
other tabs `tabindex="-1"`.

- [x] **Step 4: Implement the midnight evidence-console CSS**

Use these exact base tokens and derive all styling from them:

```css
:root {
  color-scheme: dark;
  --bg: #071015;
  --bg-deep: #04090c;
  --surface: #0d1a20;
  --surface-raised: #12242c;
  --surface-soft: #102028;
  --line: #26404a;
  --line-strong: #3a606c;
  --text: #e7f2f5;
  --text-muted: #91a8b0;
  --text-dim: #698089;
  --signal: #65d9ff;
  --signal-soft: rgba(101, 217, 255, .12);
  --fresh: #72e6a6;
  --stale: #ffc857;
  --degraded: #ff6b6b;
  --na: #91a8b0;
  --font-display: "Bahnschrift", "Aptos Display", "Segoe UI Variable Display", sans-serif;
  --font-body: "Aptos", "Segoe UI Variable Text", sans-serif;
  --font-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
  --radius-sm: 6px;
  --radius-md: 10px;
  --shadow-raised: 0 18px 50px rgba(0, 0, 0, .28);
}
```

Use a dark radial-gradient atmosphere plus faint grid lines; cyan focus outlines; status-colored
left rails rather than full-card fills; `14px/1.62` body text; metadata of at least `12px`; and
panel width `min(100%, 1040px)`. Do not add white cards, purple gradients, remote assets, or fonts.

At `max-width: 760px`, implement:

```css
#layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
#picker { max-height: 42vh; border-right: 0; border-bottom: 1px solid var(--line); }
body.focus #picker nav, body.focus #picker h2 { display: none; }
#content { min-width: 0; padding: 18px 16px 44px; }
#tabs { overflow-x: auto; scrollbar-width: thin; }
.matrix-row, .feature-row { grid-template-columns: minmax(0, 1fr); }
```

Add `@media (prefers-reduced-motion: reduce)` to remove transitions and animation.

- [x] **Step 5: Run focused tests and commit**

Run:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-page-sidebar.test.ts test/system-page.test.ts
```

Update obsolete exact-markup assertions only where the approved shell replaces them. Commit:

```powershell
git add src/system-shell.ts test/system-page-visual-identity.test.ts test/system-page-sidebar.test.ts test/system-page.test.ts
git commit -m "feat(system-ui): establish evidence console shell"
```

## Task 2: Build readable landing/focus modes and recoverable health loading

**Files:**
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts`
- Modify: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`
- Modify as required: `pi-ext/factory-watch/test/system-landing.test.ts`
- Modify as required: `pi-ext/factory-watch/test/system-page-dom.test.ts`

- [x] **Step 1: Add failing jsdom tests**

Follow the existing `JSDOM` and stubbed-fetch setup. Assert:

```ts
expect(doc.querySelector("#landingPanel")?.hasAttribute("hidden")).toBe(false);
expect(doc.querySelector("#scopeWorkspace")?.hasAttribute("hidden")).toBe(true);
expect(doc.querySelector("#healthSummary")?.textContent).toContain("No measurable evidence");
expect(doc.querySelectorAll(".health-metric")).toHaveLength(5);
expect(doc.querySelector(".feature-row")?.textContent).toContain("Deterministic safety governor");
expect(doc.querySelector(".feature-row")?.textContent).toContain("15 SR");
expect(doc.querySelector(".feature-row")?.textContent).toContain("weak");
```

Stub health to reject once and succeed after clicking Retry. Assert the failure message contains
`Project evidence is unavailable`, Retry becomes visible, and a click clears the status after the
successful response. After a successful bundle click assert landing hidden, workspace visible,
and the matching link has `aria-current="page"`.

- [x] **Step 2: Verify behavioural tests fail**

Run `npx vitest run test/system-page-visual-identity.test.ts test/system-landing.test.ts`.
Expected: FAIL on mode switching, honest zero wording, directory rows, Retry, and selection.

- [x] **Step 3: Implement mode and health lifecycle helpers**

Add these helpers inside `systemBootstrap`:

```ts
function showLanding(): void {
  landingPanel.hidden = false;
  scopeWorkspace.hidden = true;
  content.setAttribute('aria-busy', 'false');
  setPickerClass(false);
}
function showWorkspace(): void {
  landingPanel.hidden = true;
  scopeWorkspace.hidden = false;
  content.setAttribute('aria-busy', 'false');
  setPickerClass(true);
}
function setHealthStatus(message: string, retry: boolean): void {
  healthStatus.textContent = message;
  healthStatus.hidden = message === '';
  retryHealth.hidden = !retry;
}
```

`loadHealth()` sets busy state and `Reading project evidence…`; on success it renders, clears
status, and shows landing; on failure it keeps landing visible and shows
`Project evidence is unavailable. The navigator is still running; retry the health scan.` plus
Retry. Bind Retry to `loadHealth()`. Successful scope loaders call `showWorkspace()`; failed scope
loaders call `showLanding()` instead of hiding all content.

- [x] **Step 4: Render honest metrics and actionable features**

`renderHealthSummary` creates one `.health-overall` and one `.health-metric` per class. When
`h.expected === 0`, display `No measurable evidence` and literal `0 / 0`, never `100%`; otherwise
display the supplied percentage.

`renderBundleList` creates safe text-node anchors:

```ts
const row = document.createElement('a');
row.className = 'feature-row readiness-' + b.readiness;
row.href = scopeHref('bundle:' + b.id);
row.dataset.readiness = b.readiness;
```

Include readiness label, human label, `members + ' artifacts'`, and
`countsText(b.readiness_counts)`. Prevent default and call `loadScope('bundle:' + b.id)`.

Add `markActiveScope(scopeRef)` to remove old selection and set `.is-active` plus
`aria-current="page"` on links whose href equals `scopeHref(scopeRef)`. For known bundles, use the
human label as `#scopeHeader`, the kind in `#scopeKind`, and raw ref in `#scopeRef`.

- [x] **Step 5: Run tests and commit**

Run:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-landing.test.ts test/system-page-dom.test.ts test/system-page-navigation.test.ts
```

Commit:

```powershell
git add src/system-bootstrap.ts src/system-shell.ts test/system-page-visual-identity.test.ts test/system-landing.test.ts test/system-page-dom.test.ts test/system-page-navigation.test.ts
git commit -m "feat(system-ui): separate landing and scope focus"
```

## Task 3: Make navigation contextual and keyboard-complete

**Files:**
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts`
- Modify: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`
- Modify as required: `pi-ext/factory-watch/test/system-page-navigation.test.ts`

- [x] **Step 1: Add failing navigation tests**

For bundle scope assert Brief/Matrix visible and Story/Reverse hidden. Add task and file cases that
show only Story and Reverse respectively. Assert `.scope-group-title` elements are native buttons.
Focus Brief, dispatch ArrowRight, and assert Matrix is focused/selected with `tabindex="0"` while
Brief becomes `-1`; add Home and End cases.

Enter `SR-137`, activate Go, and assert fetch contains
`/api/system/brief?scope=sr%3ASR-137` but never a bare `sr:SR-137` URL.

- [x] **Step 2: Verify navigation tests fail**

Run `npx vitest run test/system-page-visual-identity.test.ts test/system-page-navigation.test.ts`.
Expected: FAIL on contextual tabs, native buttons, roving focus, and search.

- [x] **Step 3: Implement native group buttons and contextual tabs**

Create each group heading as:

```ts
const title = document.createElement('button');
title.type = 'button';
title.className = 'scope-group-title';
title.setAttribute('aria-expanded', String(expanded));
```

Add:

```ts
const TABS_BY_KIND: Record<string, string[]> = {
  bundle: ['Brief', 'Matrix', 'Timeline', 'Guide', 'Trace'],
  sr: ['Brief', 'Matrix', 'Timeline', 'Guide', 'Trace'],
  task: ['Story'],
  file: ['Reverse'],
};
```

`configureTabs(kind)` hides nonmembers. `showTab` ignores hidden tabs, gives the selected tab
`tabindex=0`, all others `-1`, and synchronizes panels. Call `configureTabs` before selecting the
initial tab in each scope loader.

- [x] **Step 4: Implement standard keyboard and exact-ref search**

On visible tabs handle ArrowLeft, ArrowRight, Home, and End using visible tabs only, with wrapping,
`focus()`, and `showTab()`. Scope arrows must exclude items hidden by their row/group inline style
as well as `hidden`.

Delete `resolveScopeRef`. `searchGo` still resolves a known bundle label/id, otherwise normalizes a
bare value to `sr:<value>` and calls `loadScope(ref)`. The scope-specific API remains the validator.

- [x] **Step 5: Run tests and commit**

Run:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-page-navigation.test.ts test/system-page-vcycle.test.ts test/system-page-trace.test.ts
```

Commit:

```powershell
git add src/system-bootstrap.ts test/system-page-visual-identity.test.ts test/system-page-navigation.test.ts test/system-page-vcycle.test.ts test/system-page-trace.test.ts
git commit -m "feat(system-ui): make scope navigation contextual"
```

## Task 4: Improve evidence readability and render the trace spine

**Files:**
- Modify: `pi-ext/factory-watch/src/system-renderers.ts`
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts`
- Modify: `pi-ext/factory-watch/src/system-shell.ts`
- Modify: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`
- Modify as required: `pi-ext/factory-watch/test/system-page-dom.test.ts`
- Modify as required: `pi-ext/factory-watch/test/system-page-implementation-summary.test.ts`

- [x] **Step 1: Add failing renderer tests**

For one claim with two citations and one span, assert:

```ts
const evidence = doc.querySelector(".claim .evidence-disclosure");
expect(evidence?.tagName).toBe("DETAILS");
expect(evidence?.querySelector("summary")?.textContent).toBe("Evidence · 3");
expect(evidence?.textContent).toContain("requirements\\SR-034.md");
```

Assert a matrix row contains `.matrix-subject`, `.matrix-status`, and `.matrix-summary`. For a
traversal payload assert four `.trace-spine-step` nodes labelled Requirement, Tasks, Design, Files
in order.

- [x] **Step 2: Verify renderer tests fail**

Run:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-page-dom.test.ts test/system-page-implementation-summary.test.ts
```

Expected: FAIL on disclosure, matrix hooks, and trace-spine structure.

- [x] **Step 3: Add native evidence disclosure and matrix hooks**

In `renderClaim`, place citations/spans inside:

```ts
const evidenceCount = (claim.citations?.length || 0) + (claim.spans?.length || 0);
const details = document.createElement('details');
details.className = 'evidence-disclosure';
const summary = document.createElement('summary');
summary.appendChild(document.createTextNode('Evidence · ' + evidenceCount));
details.appendChild(summary);
```

Preserve all payload text and order. Keep implementation summaries expanded. Give matrix subject
`matrix-subject`, the badge wrapper `matrix-status`, and summary `matrix-summary`; style a compact
grid on wide screens and stack it below 760 px.

- [x] **Step 4: Render traversal as four spine segments**

Replace the sentence renderer with a local helper:

```ts
function addStep(label: string, values: string[]): void {
  const step = document.createElement('div');
  step.className = 'trace-spine-step';
  const stepLabel = document.createElement('div');
  stepLabel.className = 'trace-spine-label';
  stepLabel.appendChild(document.createTextNode(label));
  const stepValue = document.createElement('div');
  stepValue.className = 'trace-spine-value';
  stepValue.appendChild(document.createTextNode(values.join(', ') || 'Not recorded'));
  step.appendChild(stepLabel);
  step.appendChild(stepValue);
  node!.appendChild(step);
}
```

Call it with `[trav.requirement]`, `trav.tasks`, `trav.design`, and `trav.files` under Requirement,
Tasks, Design, and Files. CSS provides numbered nodes and connector lines without hiding text.

- [x] **Step 5: Run tests and commit**

Run:

```powershell
npx vitest run test/system-page-visual-identity.test.ts test/system-page-dom.test.ts test/system-page-implementation-summary.test.ts test/system-membership.test.ts
```

Commit:

```powershell
git add src/system-renderers.ts src/system-bootstrap.ts src/system-shell.ts test/system-page-visual-identity.test.ts test/system-page-dom.test.ts test/system-page-implementation-summary.test.ts test/system-membership.test.ts
git commit -m "feat(system-ui): clarify evidence and trace reading"
```

## Task 5: Automated verification

- [x] Run `npm run typecheck` in `pi-ext/factory-watch`; expect zero errors.
- [x] Run `npm test` in `pi-ext/factory-watch`; expect all tests green (baseline: 65 files / 753 tests).
- [x] Run `uv run python -m pytest tests/unit/system -q` at repository root; expect 311 passing.
- [x] Run `git diff --check 9239b20..HEAD`; expect no output.
- [x] Run `git status --short`; expect a clean tree after commits.
- [ ] If legitimate obsolete test assertions needed updates, commit them as
  `test(system-ui): cover responsive evidence console`; do not create an empty commit.

## Independent MCP browser validation gate

[PASSED] Executed with a standalone Playwright harness
(`pi-ext/factory-watch/test/system-browser-validation.test.ts`, env-gated via `BROWSER_GATE=1`)
against `C:\coding\cool_physical_ai_project` at 1440×900, 1024×768, and 390×844. Validated
landing + populated bundle focus, page overflow, scope sheet open/close, contextual tabs,
disclosures, Matrix hooks, trace spine, tab Left/Right/End roving focus, exact-ref search
(`sr:SR-137` -> encoded `sr%3ASR-137`, no bare-`sr:` fetch), `aria-current`, `aria-busy`, Retry
after an intercepted health failure, reduced-motion CSS, and console errors. Report:
`C:\coding\cool_physical_ai_project\.tmp\browser-gate-report.json` - zero findings.

## Independent plan/code review gate

[PASSED] Reviewed the full commit range `9239b20..HEAD` against the spec, this
plan, and the browser gate report. Every Task/Step (1-4) verified IMPLEMENTED
with file:line evidence: midnight tokens + semantic shell (`system-shell.ts`),
landing/focus separation, honest metrics + Retry (`system-bootstrap.ts`),
contextual tabs (TABS_BY_KIND + configureTabs), keyboard roving (visible-only
Arrow/Home/End), exact-ref search (bare id gets `sr:` prefix, encoded fetch),
native `<details>` disclosure + matrix hooks (`system-renderers.ts`),
four-segment trace spine (Requirement/Tasks/Design/Files), 760px
single-column + mobile scope sheet, reduced-motion. No missing or extra scope.
Readability, accessibility, security, and maintainability assessed; no
Critical/Important findings. Human visual check guide:
`docs/superpowers/2026-08-13-system-navigator-visual-check.md`.

## Final completion gate

Run fresh after all fixes:

```powershell
cd pi-ext/factory-watch
npm run typecheck
npm test
cd ../..
uv run python -m pytest tests/unit/system -q
git diff --check 9239b20..HEAD
git status --short
```

Do not claim completion unless every command exits zero and both independent agents approve the
current HEAD.
