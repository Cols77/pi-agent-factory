# System Navigator: Persistent Left Scope Sidebar + Recovered Trace Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Move the scope/requirement list into a persistent left sidebar so it never pushes the selected scope's content below the fold; (2) recover the per-requirement trace (which tasks satisfy it, and each task's plan → spec) that `/system` showed before it was repointed to the navigator.

**Architecture:** Both changes are confined to `src/system-page.ts` (the client-side HTML/CSS/JS in `renderSystemPageHtml()`). The left sidebar is a CSS grid layout. The Trace tab fetches the already-served `/api/graph` (the `factory.trace` graph: nodes for br/sr/spec/plan/task + edges `satisfies`/`source_plan`/`spec_ref`/`upstream`), inverts it for the selected SR, and renders a chain. No Python changes. `docs-server.ts` and `index.ts` untouched.

**Tech Stack:** TypeScript string template, vanilla DOM (createTextNode/appendChild), CSS grid, vitest + jsdom (`test/system-page*.test.ts`).

## Global Constraints (identical to the prior navigator work)

- Only edit `src/system-page.ts` (and `test/` files). Do NOT touch `src/docs-server.ts`, `src/index.ts`, or any `.py` file.
- `renderSystemPageHtml(): string` signature unchanged (`docs-server.ts` calls it).
- Payload-derived strings via `createTextNode`/`textContent` ONLY. `innerHTML` may only ever be set to a quoted literal (e.g. `el.innerHTML = ''`). Never `el.innerHTML = <expression>`.
- Never client-side `.sort(...)`. Render in payload order / deterministic edge order.
- Never remap/recolour a payload value as the visible label: `claim.kind`, `freshness.state`, `status`, `actor`, `action`, `run.source`, `stops_at` render verbatim.
- Keep the string `--export` out of the emitted HTML.
- All existing tests in `test/system-page.test.ts`, `test/system-page-dom.test.ts`, `test/system-page-vcycle.test.ts`, `test/system-page-implementation-summary.test.ts`, `test/system-page-navigation.test.ts` MUST stay green.

## Data note (why the trace is recoverable without new bundle data)

- Requirements (`requirements/SR-*.md`) are claim files with NO reverse index — they do not list satisfying tasks. The link is one-directional: `tasks/T-*.md` carry `satisfies: [SR-...]` and `source_plan: <plan file>`, and the trace graph (`factory.trace graph`, served as `/api/graph`) exposes nodes `br/sr/spec/plan/task` with edges `task --satisfies--> sr --upstream--> br` and `task --source_plan--> plan --spec_ref--> spec`.
- Therefore the per-requirement trace is already derivable from existing data; no bundle filling is required (bundles are flat feature memberships, not per-requirement task links).
- The `/system` navigator currently never renders this inversion because it only renders `factory.system` payloads (brief/matrix/timeline/guide/story/reverse), none of which carry it.

---

## Task A: Persistent left sidebar for the scope list

**Files:**
- Modify: `src/system-page.ts` (the `<style>` layout block and the `#picker`/`#content` markup structure)

**Interfaces:**
- Produces: a two-column layout — left column `#picker` (scope list, always visible & independently scrollable on wide screens), right column `#content` (tabs/panels). On narrow screens the Task 1 `body.focus` compact-bar collapse still applies; on wide screens the sidebar stays open regardless of `body.focus`.

- [ ] **Step 1: Write failing tests** in a new `test/system-page-sidebar.test.ts`

```ts
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}
function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse({ scopes: [{ kind: "sr", ref: "sr:SR-001" }], errors: [] });
    if (url.pathname === "/api/system/brief") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, claims: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/matrix") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, rows: [] });
    if (url.pathname === "/api/system/timeline") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, events: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, sections: [] });
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

describe("system-page left sidebar", () => {
  test("places the scope picker and content in a two-column grid layout", async () => {
    const dom = await loadPage();
    await vi.waitFor(() => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(), { timeout: 2000 });
    const layout = dom.window.document.getElementById("layout");
    expect(layout).not.toBeNull();
    expect(dom.window.document.getElementById("picker")!.parentElement!.id).toBe("layout");
    expect(dom.window.document.getElementById("content")!.parentElement!.id).toBe("layout");
  });

  test("the sidebar stays a distinct column when a scope is loaded", async () => {
    const dom = await loadPage("sr:SR-001");
    await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
    expect(dom.window.document.getElementById("picker")).not.toBeNull();
    expect(dom.window.document.getElementById("scopeList")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run tests, verify fail** — Expected: FAIL (no `#layout`, picker/content not siblings of a layout wrapper).

- [ ] **Step 3: Implement the grid layout**
- In the `<style>` block, replace the single-column rules (`body`, `main` max-width, `#picker`/`#content` padding, `body.focus` collapse) with a grid layout. The existing `body.focus` collapse rules stay but are wrapped in a narrow-viewport media query so a wide screen always shows the sidebar:
```css
body { font: 13px/1.55 ui-sans-serif, system-ui, sans-serif; margin: 0; height: 100vh; overflow: hidden; }
header { padding: 12px 20px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 12px; }
#banner { padding: 8px 20px; background: color-mix(in srgb, var(--degraded) 15%, transparent); }
#banner:empty { display: none; }
#layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); height: calc(100vh - 60px); }
#picker { border-right: 1px solid var(--line); overflow: auto; padding: 10px 14px 24px; }
#content { overflow: auto; padding: 8px 24px 48px; }
@media (max-width: 760px) {
  body.focus #scopeList, body.focus .scope-group-title, body.focus #scopeFilter, body.focus #picker h2 { display: none; }
  #scopeToggle { display: inline-block; font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--sunk); cursor: pointer; }
  body.focus #scopeToggle { display: inline-block; }
}
/* Wide screens: the sidebar is always an open column; the toggle + collapse are irrelevant. */
#scopeToggle { display: none; }
```
Keep the `#picker nav`, `#scopeFilter`, `.scope-group-title`, `.scope-row`, `.scope-item`, `.scope-kind`, `#tabs`, `.tab`, panels, claim/matrix/timeline/styles exactly as they are.
- Restructure the markup: wrap `#picker` and `#content` in `<div id="layout">` so that aside/wrapper structure is:
```html
<header>… System Navigator …</header>
<div id="banner" role="status"></div>
<div id="layout">
  <aside id="picker">…existing picker markup unchanged…</aside>
  <section id="content" hidden>…existing content markup unchanged…</section>
</div>
```
Keep every existing id (`picker`, `scopeList`, `scopeErrors`, `content`, `scopeHeader`, `loading`, `scope-meta`/`refresh`/`loadedAt`, all tabs and panels) unchanged inside the wrappers.
- Keep the `body.focus` class toggling from Task 1 exactly (it now only affects narrow screens).
- Ensure `#content.hidden === false` on scope load is untouched (all existing dom tests stay green).

- [ ] **Step 4: Run new tests + full system-page suite**
Run: `npx vitest run test/system-page-sidebar.test.ts && npx vitest run test/system-page`
Expected: PASS (new) + all existing system-page tests PASS.

- [ ] **Step 5: Typecheck** — `npm run typecheck`, no errors.
- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-sidebar.test.ts
git commit -m "feat(system-nav): persistent left scope sidebar via two-column grid layout"
```

---

## Task B: Recover per-requirement trace as a lazy Trace tab

**Files:**
- Modify: `src/system-page.ts` (add 7th tab, a pure inversion function, and a lazy loader)
- Modify: `test/system-page-navigation.test.ts` (append) and/or a new `test/system-page-trace.test.ts`

**Interfaces:**
- Produces: a `Trace` tab (id `tabTrace` / `panelTrace`) applicable to `sr:` and `bundle:` scopes (a "Not applicable — see Story/Reverse" notice for `task:`/`file:` scopes). On first click it `fetch('/api/graph')`, inverts the graph for the scope's SRs (or the single SR), and renders, per SR: the SR's `upstream` BR, then each satisfying task (edges `kind==='satisfies' && dst===srId`), then that task's `source_plan` → plan and the plan's `spec_ref` → spec. A failed graph fetch shows a fallback notice (never crashes, never hides the other tabs).

- [ ] **Step 1: Write failing tests** in a new `test/system-page-trace.test.ts`

```ts
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

const GRAPH = {
  nodes: [
    { id: "BR-002", kind: "br", title: "Swimmer safety", path: "requirements/BR-002.md", exempt: false, deferred: null },
    { id: "SR-086", kind: "sr", title: "Common planner protocol", path: "requirements/SR-086.md", exempt: false, deferred: null },
    { id: "T-059", kind: "task", title: "Common Planner Protocol", path: "tasks/T-059.md", exempt: false, deferred: null },
    { id: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", kind: "plan", title: "PAAD increment 1", path: "docs/superpowers/plans/2026-08-06-paad-increment-1-deterministic-vertical-slice.md", exempt: false, deferred: null },
    { id: "spec:docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", kind: "spec", title: "PAAD MVP spec", path: "docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", exempt: false, deferred: null },
  ],
  edges: [
    { src: "T-059", dst: "SR-086", kind: "satisfies" },
    { src: "SR-086", dst: "BR-002", kind: "upstream" },
    { src: "T-059", dst: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", kind: "source_plan" },
    { src: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", dst: "spec:docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", kind: "spec_ref" },
  ],
};
function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}
function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse({ scopes: [{ kind: "sr", ref: "sr:SR-086" }], errors: [] });
    if (url.pathname === "/api/system/brief") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, claims: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/matrix") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, rows: [] });
    if (url.pathname === "/api/system/timeline") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, events: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, sections: [] });
    if (url.pathname === "/api/graph") return jsonResponse(GRAPH);
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}
async function loadPage(): Promise<JSDOM> {
  const fetchMock = mockFetch();
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously", resources: "usable",
    url: "http://localhost/system?scope=sr%3ASR-086",
    beforeParse(w: never) { (w as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch; },
  });
}
afterEach(() => vi.restoreAllMocks());

describe("system-page Trace tab", () => {
  test("a Trace tab exists for the scope", async () => {
    const dom = await loadPage();
    await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
    expect(dom.window.document.getElementById("tabTrace")).not.toBeNull();
    expect(dom.window.document.getElementById("panelTrace")).not.toBeNull();
  });

  test("clicking Trace lazily fetches /api/graph and renders the task + plan + spec chain", async () => {
    const dom = await loadPage();
    const fetchMock = dom.window.fetch as unknown as ReturnType<typeof mockFetch>;
    await vi.waitFor(() => expect(dom.window.document.getElementById("tabTrace")).not.toBeNull(), { timeout: 2000 });
    dom.window.document.getElementById("tabTrace")!.click();
    await vi.waitFor(() => {
      expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("T-059");
    }, { timeout: 2000 });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/graph"));
    // The chain names the satisfying task, its plan, and its spec.
    expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("paad-increment-1");
    expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("paad-mvp-system-specification");
  });
});
```

- [ ] **Step 2: Run tests, verify fail** — Expected: FAIL (no `tabTrace`/`panelTrace`, clicking does nothing).

- [ ] **Step 3: Implement the Trace tab**
- Add a 7th tab to the tabs row: `<button id="tabTrace" class="tab" aria-selected="false" aria-controls="panelTrace" role="tab" aria-label="Trace">Trace</button>` and `<div id="panelTrace" class="panel" hidden></div>`. Extend every tab-list to include `'Trace'`: the `showTab` loop, the `selectInitialTab` mapping, the `renderNotApplicable` arrays in `loadStoryScope`/`loadReverseScope` (Trace is not applicable for `task:`/`file:` — show the same "Not applicable … See the Story/Reverse tab" notice), and the keyboard `TAB_ORDER` (Alt+1..7; update the digit regex to `/^[1-7]$/`).
- Add a module-scoped `let traceLoaded = false;` and `let traceData = null;`. Write a pure function `invertTraceForScope(graph, refs)`:
```js
// No .sort, no payload remap: walk the graph edges in the order factory.trace
// emits them. For each sr in refs, collect (in edge order) every task whose
// `satisfies` edge targets it, then each task's source_plan -> plan and the
// plan's spec_ref -> spec, plus the sr's upstream -> br. Returns a list of
// { sr, br, tasks: [{ task, plan, spec }] }.
```
- Add a lazy loader `loadTrace(refs)` that: if `traceLoaded` re-renders from `traceData`; else `fetch('/api/graph')`, on success store + render, on failure render a fallback notice ("Trace map is unavailable for this scope. See the Brief, Story, or Reverse tabs.") via `renderNotApplicable('panelTrace', ...)`. Wire `#tabTrace.onclick` to call `showTab('Trace')` and, if the scope kind is sr/bundle, call `loadTrace(<the SR refs for the current scope>)` (the SR refs are derivable at load time: store the current scope's SR list on scope load).
- Rendering: for each SR, one `.trace-sr` block. Title line: SR id + title (title from the graph node if present, else the id). Under it: `upstream: <br>` line if present; then a `.trace-task` per satisfying task rendered as `task —<title> → plan <title> → spec <title>` using text nodes; if a task has no resolved plan/spec, show `(plan: unresolved)` plainly (follow the `stops_at` "say where it stopped" discipline from `reverse.py`/`walkIntentChain`). Use a `.trace-task`/`.trace-chain` container and textOnly rendering (createTextNode only).
- Store the SR refs for the current scope: in `loadBundleScope`, capture the bundle's `sr:` member refs; in the `sr:` case (loadBundleScope is also used for `sr:` scopes) capture `[scopeRef]`. Keep `currentScope` (Task 2) for the header/refresh.
- Keep Trace fetch lazy so existing dom tests (whose `fetch` mocks throw on `/api/graph`) never trigger it — they never click the Trace tab.
- Add CSS for `.trace-sr`, `.trace-task`, `.trace-chain`, `.trace-hop`, `.trace-arrow` (reuse the `.run`/`.path` frame style), following the palette.

Keep all existing behavior byte-for-byte identical otherwise.

- [ ] **Step 4: Run new tests + full suite**
Run: `npx vitest run test/system-page-trace.test.ts && npx vitest run test/system-page`
Expected: PASS (new) + all existing PASS.
- [ ] **Step 5: Typecheck** — no errors.
- [ ] **Step 6: Commit**
```bash
git add src/system-page.ts test/system-page-trace.test.ts
git commit -m "feat(system-nav): recover per-requirement trace as a lazy Trace tab from the trace graph"
```

---

## Final verification

- [ ] **Step F1:** `cd C:/coding/pi-agent-factory/pi-ext/factory-watch && npx vitest run` (expect the only possible failure to be the pre-existing flaky `test/smoke.test.ts`; all system-page tests green).
- [ ] **Step F2:** `npm run typecheck` — clean.
- [ ] **Step F3:** Confirm only `src/system-page.ts` plus `test/system-page-sidebar.test.ts`, `test/system-page-trace.test.ts`, and (optionally) `test/system-page-navigation.test.ts` changed.

## Self-Review

- **Spec coverage:** Task A delivers the left sidebar (top ask). Task B recovers the requirement→task→plan→spec trace from existing graph data (no bundle filling needed), explains and closes the gap the user reported.
- **Placeholder scan:** every step names exact files, exact test assertions, and concrete implementation guidance.
- **Type/name consistency:** `#layout`, `#picker`, `#content`, `tabTrace`/`panelTrace`, `loadTrace`, `invertTraceForScope`, `showTab`, `selectInitialTab`, `currentScope`, `TAB_ORDER` are consistent across tasks.
