# System Navigator Navigation + Visual Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/system` browser navigable and scannable: collapse the scope list when a scope is open, add search/grouping, switch to SPA-style scope navigation with working back/forward, sticky tabs with per-tab URL hashes, loading + refresh affordances, and keyboard/accessibility support.

**Architecture:** All change is confined to ONE file — `src/system-page.ts` (the client-side HTML/CSS/JS in `renderSystemPageHtml()`). The server (`docs-server.ts`) and the `/system` command wiring in `index.ts` are untouched. Python is never consulted or modified: this page only renders payload JSON. The existing DOM tests pin the rendering guarantees; every task must keep them green.

**Tech Stack:** TypeScript string template, vanilla DOM (createTextNode/appendChild only — never `innerHTML` from data), CSS. Tests via vitest + jsdom in `test/system-page*.test.ts`.

## Global Constraints

- Only edit `src/system-page.ts` (and, for tests, `test/` files). Do NOT touch `src/docs-server.ts`, `src/index.ts`, or any `.py` file.
- The exported function name `renderSystemPageHtml(): string` must not change — `docs-server.ts` calls it.
- Every payload-derived string must reach the DOM via `createTextNode`/`textContent`. `.innerHTML` may only ever be set to a quoted literal to clear a container (e.g. `el.innerHTML = ''`). Never `el.innerHTML = <expression>`.
- Never client-side `.sort(...)`; render in payload order.
- Never remap/recolour-only a payload value as the visible label: `claim.kind`, `freshness.state`, `status`, `actor`, `action`, `run.source`, `stops_at` render verbatim.
- No export affordance in the UI; keep the string `--export` out of the emitted HTML.
- Every existing DOM test must stay green (see "Test contract" below).

## Test Contract (do not break these)

Existing tests (`test/system-page.test.ts`, `test/system-page-dom.test.ts`, `test/system-page-vcycle.test.ts`, `test/system-page-implementation-summary.test.ts`) assert:

1. HTML contains ids: `picker`, `scopeList`, `scopeErrors`, `content`, `tabBrief`, `tabMatrix`, `tabTimeline`, `tabGuide`, `panelBrief`, `panelMatrix`, `panelTimeline`, `panelGuide`. Add `tabStory/tabReverse/panelStory/panelReverse` (already present) — keep all.
2. `#scopeList .scope-item` elements whose `textContent` equals the scope ref exactly (e.g. `bundle:evidence-lifecycle`). Scope items may be `<a>` or `<button>`; text must still be the raw ref.
3. `#scopeErrors .scope-error` text containing a bundle-load error.
4. `.claim` elements in `#panelBrief`; each `.claim`'s first `.badge` text equals `claim.kind`; `.claim-text` equals `claim.text`; `.claim-missing` present and visible.
5. `.freshness` element text equals `freshness.state` (never colour alone) — keep `createTextNode(freshness.state)`.
6. `.degraded-banner` text includes `degraded_reasons` items, verbatim.
7. `.span` text starts `quoted from <path>...` and does NOT contain `citation 0`.
8. `#panelMatrix .matrix-row` with `.badge` = `status` and `.claim-text` = `summary`.
9. `#panelTimeline .timeline-event` containing actor/`sequence=1`/degraded banner.
10. Guide sections render as `.claim`; when guide fetch fails, `#panelGuide` text contains "Guide synthesis is unavailable".
11. `#panelStory .run` with `.source` text `manifest`/`session`; session run text contains `missing`.
12. `#panelReverse .path` text contains `satisfies`.
13. `.implementation-summary` renders runs/outcome/changed files/latest validation, with `.validation-stale`/`.validation-none` classes.
14. `content.hidden === false` once a scope loads.
15. HTML contains `renderGuideFallback`, `[briefRes, matrixRes, timelineRes].find((r) => !r.ok)`, `claim.kind`, `claim-' + claim.kind`, the five `/api/system/*` fetch strings, and NOT `--export`.

---

## Task 1: Scope picker becomes searchable + grouped, and collapses to a compact bar when a scope is active

**Files:**
- Modify: `src/system-page.ts` (the `<style>` block and the `renderScopeList`/`loadScopes` functions + `#picker` markup)

**Interfaces:**
- Consumes: `data.scopes` (each `{ kind, ref }`), `data.errors` (`{ path, bundle_id, error }`) from `/api/system/scope`.
- Produces: a `<nav>`-wrapped picker with a search `<input id="scopeFilter">`, groups by `scope.kind`, and a `<body class="focus">` toggled when a scope is loaded so `#scopeList` collapses (CSS `display:none`) behind a compact "All scopes ▾" toggle button (`#scopeToggle`).

- [ ] **Step 1: Write failing tests** in a new `test/system-page-navigation.test.ts`

```ts
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = {
  scopes: [
    { kind: "bundle", ref: "bundle:evidence-lifecycle" },
    { kind: "sr", ref: "sr:SR-001" },
    { kind: "sr", ref: "sr:SR-002" },
    { kind: "task", ref: "task:T-001" },
    { kind: "file", ref: "file:src/a.py" },
  ],
  errors: [],
};
const EMPTY = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, rows: [] };
const EMPTY_TL = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, events: [], degraded: false, degraded_reasons: [] };
function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}
function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse(SCOPE_LIST);
    if (url.pathname === "/api/system/matrix") return jsonResponse(EMPTY);
    if (url.pathname === "/api/system/timeline") return jsonResponse(EMPTY_TL);
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: EMPTY.scope, sections: [] });
    if (url.pathname === "/api/system/brief") return jsonResponse({ scope: EMPTY.scope, claims: [], degraded: false, degraded_reasons: [] });
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}
async function loadPage(scope?: string): Promise<JSDOM> {
  const fetchMock = mockFetch();
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously", resources: "usable",
    url: scope ? `http://localhost/system?scope=${encodeURIComponent(scope)}` : "http://localhost/system",
    beforeParse(w: never) { (w as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch; },
  });
}
afterEach(() => vi.restoreAllMocks());

describe("system-page navigation", () => {
  test("groups scopes by kind and provides a filter input", async () => {
    const dom = await loadPage();
    await vi.waitFor(() => expect(dom.window.document.getElementById("scopeFilter")).not.toBeNull(), { timeout: 2000 });
    const list = dom.window.document.getElementById("scopeList")!;
    expect(Array.from(list.querySelectorAll(".scope-item")).map((e) => e.textContent))
      .toEqual(["bundle:evidence-lifecycle", "sr:SR-001", "sr:SR-002", "task:T-001", "file:src/a.py"]);
  });

  test("collapses the scope list into a compact bar once a scope loads", async () => {
    const dom = await loadPage("bundle:evidence-lifecycle");
    await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
    expect(dom.window.document.body.classList.contains("focus")).toBe(true);
    expect(dom.window.document.getElementById("scopeToggle")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run new tests, verify they fail**
Run: `npx vitest run test/system-page-navigation.test.ts`
Expected: FAIL — no `scopeFilter`, no `body.focus`, no `scopeToggle`.

- [ ] **Step 3: Add grouped, filterable picker + compact bar**

In the `<style>` block add CSS (below the existing `#picker` rules):

```css
#picker nav { margin: 10px 0; }
#scopeFilter { width: 100%; padding: 6px 8px; font: inherit; border: 1px solid var(--line); border-radius: 4px; background: Canvas; color: inherit; margin-bottom: 6px; }
.scope-group-title { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; opacity: .6; margin: 10px 0 2px; }
.scope-item { display: block; padding: 3px 8px; border: none; border-radius: 3px; margin: 1px 0; text-decoration: none; color: inherit; font: inherit; text-align: left; width: 100%; }
.scope-item:hover, .scope-item:focus-visible { background: var(--hover); outline: 2px solid currentColor; outline-offset: 1px; }
.scope-kind { font-size: 10px; text-transform: uppercase; opacity: .55; margin-right: 6px; }
body.focus #scopeList, body.focus .scope-group-title, body.focus #scopeFilter, body.focus #picker h2 { display: none; }
#scopeToggle { display: none; font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--sunk); cursor: pointer; }
body.focus #scopeToggle { display: inline-block; }
body.focus #picker { padding: 6px 0; }
```

Replace the `#picker` markup block:

```html
<div id="picker">
  <h2>Declared scopes</h2>
  <button id="scopeToggle" aria-expanded="false">All scopes ▾</button>
  <nav aria-label="Scopes">
    <input id="scopeFilter" type="search" placeholder="Filter scopes…" aria-label="Filter scopes" />
    <div id="scopeList"></div>
    <div id="scopeErrors"></div>
  </nav>
</div>
```

Rewrite `renderScopeList` to group by kind and filter; rewrite `loadScopes` to store the full list and drive a filter. Provide a `setPickerClass(focused)` helper called from `loadScope` success/failure paths. Pseudocode core (author the exact code in the file): build an ordered array of `{kind, ref}`; iterate `data.scopes`, appending a group title `<div class="scope-group-title">` the first time a kind is seen, then each scope as `<a class="scope-item" href="/system?scope=...">` containing a `<span class="scope-kind">kind</span>` and a text node with the ref. Filter listener hides non-matching `.scope-item` (and hides empty group titles). `scopeToggle` toggles `body` off the `.focus` class and swaps `aria-expanded`.

Title text for SRs/bundles is not available from the payload, so a tooltip/title can be added to the anchor but the visible ref text MUST remain exactly the ref.

- [ ] **Step 4: Run new tests + full system-page suite**
Run: `npx vitest run test/system-page`
Expected: PASS all new + existing.

- [ ] **Step 5: Typecheck**
Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-navigation.test.ts
git commit -m "feat(system-nav): searchable, grouped scope picker that collapses to a bar when a scope is open"
```

---

## Task 2: SPA scope navigation + sticky tabs with per-tab URL hash

**Files:**
- Modify: `src/system-page.ts` (scope item click handling, `loadScope`, tab switching, CSS)

**Interfaces:**
- Produces: clicking a scope calls `loadScope(ref)` (SPA, no full reload) and updates the URL via `history.pushState` to `/system?scope=<ref>`; switching tabs updates `location.hash` and reads it on boot. `#tabs` becomes `position: sticky`. A `<span id="scopeMeta">` carries the active tab label.

- [ ] **Step 1: Write failing tests** (append to `test/system-page-navigation.test.ts`)

```ts
test("scope items navigate via the SPA loader and pushState, not a full reload", async () => {
  const dom = await loadPage();
  await vi.waitFor(() => expect(dom.window.document.querySelectorAll("#scopeList .scope-item").length).toBe(5), { timeout: 2000 });
  const click = (dom.window.document.querySelector("#scopeList .scope-item") as unknown as HTMLElement);
  click.click();
  await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
  expect(dom.window.location.search).toContain("scope=bundle%3Aevidence-lifecycle");
});

test("tabs carry an aria-controls reference and reflect selection", async () => {
  const dom = await loadPage();
  await vi.waitFor(() => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(), { timeout: 2000 });
  const tab = dom.window.document.getElementById("tabMatrix");
  expect(tab!.getAttribute("aria-controls")).toBe("panelMatrix");
  tab!.click();
  expect(tab!.getAttribute("aria-selected")).toBe("true");
});
```

- [ ] **Step 2: Run tests, verify fail** — Expected: FAIL (no aria-controls, click reloads).

- [ ] **Step 3: Implement SPA load + sticky tabs + hash**
- Rewrite `loadScope(ref)` to: set `body.focus`, `showBanner('')`, call the appropriate kind loader, and `pushScope(ref)` which does `history.pushState({ scope: ref }, '', '/system?scope=' + encodeURIComponent(ref))` (or the current pathname with query) inside a `try/catch` guard so jsdom/odd environments don't throw.
- Give each scope `<a class="scope-item" href="/system?scope=...">` a `click` handler: `e.preventDefault(); loadScope(ref);` (keeping the `href` for middle-click/robustness).
- Rewrite `showTab(name)` to also set `location.hash` (e.g. `#matrix`) via `try { history.replaceState(null, '', location.pathname + location.search + '#' + name.toLowerCase()); } catch {}` and read the hash on boot to select the initial tab (default Brief for bundle kinds, Story/Reverse for their kinds).
- CSS: `#tabs { position: sticky; top: 0; z-index: 3; background: Canvas; }` (keep the existing border-bottom). Add `[aria-selected="true"]` state already present.
- Keep the existing click handlers on `#tabBrief/Matrix/Timeline/Guide/Story/Reverse` but make them call `showTab` (which now writes the hash).
- Ensure `content.hidden=false` still happens exactly as before for tests 14.

- [ ] **Step 4: Run tests + full suite** — PASS.
- [ ] **Step 5: Typecheck** — no errors.
- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-navigation.test.ts
git commit -m "feat(system-nav): SPA scope loading with history.pushState and sticky tabs with URL hash"
```

---

## Task 3: Loading indicator, per-tab refresh, and "loaded at" timestamp

**Files:**
- Modify: `src/system-page.ts` (add `#loading` element, a refresh button, timestamp; wire into load paths)

**Interfaces:**
- Produces: a `<div id="loading" role="status">` shown while a scope loads and hidden after; a refresh `<button id="refresh">` re-invokes `loadScope(<current ref>)`; a `<span id="loadedAt">` set to `new Date().toLocaleTimeString()` after each successful load.

- [ ] **Step 1: Write failing tests** (append to `test/system-page-navigation.test.ts`)

```ts
test("shows a loading status element and a refresh button while a scope is loaded", async () => {
  const dom = await loadPage("bundle:evidence-lifecycle");
  await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
  expect(dom.window.document.getElementById("loading")).not.toBeNull();
  expect(dom.window.document.getElementById("refresh")).not.toBeNull();
  expect(dom.window.document.getElementById("loadedAt")).not.toBeNull();
});
```

- [ ] **Step 2: Run, verify fail** — Expected: FAIL (elements absent).
- [ ] **Step 3: Implement**
- Add markup after `#scopeHeader`: `<div id="loading" role="status" hidden>Loading…</div>` and a header meta row with `<button id="refresh">Refresh</button> <span id="loadedAt"></span>`.
- In each load path (`loadBundleScope`, `loadStoryScope`, `loadReverseScope`): `document.getElementById('loading').hidden = false;` at the start, and `hidden = true` + set `loadedAt` text in the success tail. Wrap in a `finally`-style so failures also hide loading and return to the picker (existing failure branches already hide `content`/show picker — also clear loading there).
- Wire `refresh.onclick` to re-run `loadScope(currentRef)` where `currentRef` is a module-scoped variable set by `loadScope` (and initially from the boot `?scope=`).
- CSS: `#refresh { font: inherit; padding: 2px 8px; border: 1px solid var(--line); border-radius: 3px; background: var(--sunk); cursor: pointer; }`.

- [ ] **Step 4: Run tests + full suite** — PASS.
- [ ] **Step 5: Typecheck** — no errors.
- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-navigation.test.ts
git commit -m "feat(system-nav): loading status, per-scope refresh, and loaded-at timestamp"
```

---

## Task 4: Keyboard shortcuts + accessibility (focus, aria, landmarks)

**Files:**
- Modify: `src/system-page.ts` (keydown handler, `<nav>`/`role` attributes, visible-focus CSS)

**Interfaces:**
- Produces: `Alt+1..6` switches tabs; arrow-up/down moves focus across `.scope-item`s when the list is open; `:focus-visible` outlines on interactive elements; `aria-controls`/`aria-label` on tabs; the header/tabs wrapped in `<nav>` landmarks.

- [ ] **Step 1: Write failing tests** (append to `test/system-page-navigation.test.ts`)

```ts
test("Alt+number switches tabs", async () => {
  const dom = await loadPage();
  await vi.waitFor(() => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(), { timeout: 2000 });
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "2", altKey: true, bubbles: true }));
  expect(dom.window.document.getElementById("tabMatrix").getAttribute("aria-selected")).toBe("true");
});

test("tabs are exposed as a navigation landmark with labels", async () => {
  const dom = await loadPage();
  const tabs = dom.window.document.getElementById("tabs");
  expect(tabs!.getAttribute("role")).toBe("tablist");
  expect(dom.window.document.getElementById("tabMatrix").getAttribute("aria-label")).toBe("Matrix");
});
```

- [ ] **Step 2: Run, verify fail** — Expected: FAIL.
- [ ] **Step 3: Implement**
- Add `role="tablist"` to `#tabs`; each tab gets `role="tab"`, `aria-controls="panel<X>"`, `aria-label="<X>"`. Wrap the tabs and header in a `<nav aria-label="System navigator">`.
- Add a `window.addEventListener('keydown', ...)` that: if `e.altKey && !e.ctrlKey && !e.metaKey && /^[1-6]$/.test(e.key)` → `showTab(BRIEF_MATRIX_TIMELINE_GUIDE_STORY_REVERSE[Number(e.key)-1])` and `preventDefault()`; if focus is in an open scope list and ArrowDown/Up pressed, move focus to next/prev `.scope-item`.
- CSS: add a global `:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }` for interactive elements, and ensure `.tab:focus-visible` gets the same.
- Guard the keydown handler so it only acts when `#tabs` is relevant (always). Keep `showTab` updating both `aria-selected` and the hash (from Task 2).

- [ ] **Step 4: Run tests + full suite** — PASS.
- [ ] **Step 5: Typecheck** — no errors.
- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-navigation.test.ts
git commit -m "feat(system-nav): keyboard shortcuts and accessibility landmarks for the navigator"
```

---

## Final: full verification

- [ ] **Step F1:** Run entire test suite:
```bash
cd /c/coding/pi-agent-factory/pi-ext/factory-watch && npx vitest run
```
Expected: PASS, no failures (all legacy + new navigation tests).
- [ ] **Step F2:** `npm run typecheck` → no errors.
- [ ] **Step F3:** Confirm only `src/system-page.ts` and `test/system-page-navigation.test.ts` (plus this plan) changed in the extension: `git status` under `pi-ext/factory-watch`.

---

## Self-Review

- **Spec coverage:** Task 1 covers search/grouping + collapse; Task 2 covers SPA navigation + sticky tabs + URL hash; Task 3 covers loading/refresh/timestamp; Task 4 covers keyboard + accessibility. Each approved review item maps to a task.
- **Placeholder scan:** Each step names exact file, exact test assertions, and concrete implementation guidance.
- **Type/name consistency:** `loadScope`, `showTab`, `renderScopeList`, `loadScopes`, `scopeToggle`, `scopeFilter`, `loading`, `refresh`, `loadedAt` are used consistently across tasks.
