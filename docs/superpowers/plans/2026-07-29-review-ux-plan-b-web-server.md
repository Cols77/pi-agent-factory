# Review UX — Plan B: Local Web Review Server + Surface Choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Plan A (`2026-07-29-review-ux-plan-a-model-tui-python.md`) must be complete — this plan builds on `review-model.ts` (`Annotation`, `ReviewDecisionPayload`, `buildDecision`, `mapDiffRows`, `anchorForRow`) and the shared `review-diff.ts` helpers.

**Goal:** Add a second review surface — a zero-dependency local web UI, diffx-style — that produces the exact same `review-decision.json` payload as the TUI, and let the reviewer choose Terminal or Browser at review time (remembering their last choice).

**Architecture:** A `node:http` server binds to loopback on an OS-assigned port, serves one self-contained HTML page plus two JSON endpoints (`GET /api/review`, `POST /api/decision`), and resolves a Promise with the posted decision. `index.ts`'s `review` dispatch prompts Terminal/Browser via `ui.select`, remembers the choice in a small JSON file under `sessions/`, and routes accordingly. No new npm dependencies.

**Tech Stack:** TypeScript, Node built-ins only (`node:http`, `node:fs`, `node:child_process`), vitest.

## Global Constraints

- **No new runtime dependencies.** `node:http` server, hand-written HTML/JS/CSS inline in one string. No Vite/Express/Shiki.
- **Loopback only.** Bind `127.0.0.1`; no auth (same single-user local trust model as the TUI); the page makes no external network requests.
- **Windows-first.** Launch the browser via the existing `spawnTerminalWindow`-style pattern — on `win32` use `cmd /c start "" <url>`.
- **Same payload as the TUI.** The server writes via the shared `writeReviewDecision` + `buildDecision`; the Python side cannot tell which surface produced the decision.
- **One review per server.** The server shuts down after a decision is posted; no decision is written until the reviewer submits.

---

### Task 1: Review-payload builder for the web page (`GET /api/review` data)

Extract the "what does the reviewer need to see" assembly into a pure function so it can be unit-tested without a live socket, and reused by the HTTP handler.

**Files:**
- Create: `pi-ext/factory-watch/src/review-server.ts`
- Test: `pi-ext/factory-watch/test/review-server.test.ts`

**Interfaces:**
- Consumes: `FileStat`, `computeReviewFiles`/`computeFileDiffText`/`computeImplementingFiles`/`computeImplementingFileDiffText` from `review-diff.ts`; `mapDiffRows` from `review-model.ts`; `ReviewGuide` from `review-guide.ts`.
- Produces:
  - `interface ReviewPageData { taskId: string; banner: string; implementing: boolean; guide: ReviewGuide | null; files: FileStat[]; diffs: Record<string, { lines: string[]; meta: import("./review-model.js").DiffRowMeta[] }> }`
  - `function buildReviewPageData(cwd: string, startCommit: string, files: FileStat[], opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide | null; taskId: string }): ReviewPageData`

- [ ] **Step 1: Write the failing test**

```ts
// pi-ext/factory-watch/test/review-server.test.ts
import { describe, expect, test, vi } from "vitest";

vi.mock("../src/review-diff.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/review-diff.js")>()),
  computeFileDiffText: vi.fn(() => "@@ -1,1 +1,1 @@\n-old\n+new\n"),
}));

import { buildReviewPageData } from "../src/review-server.js";
import type { FileStat } from "../src/review-diff.js";

const FILES: FileStat[] = [{ path: "a.py", status: "M", added: 1, removed: 1 }];

describe("buildReviewPageData", () => {
  test("returns files, diff lines, and row meta per file", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-1" });
    expect(data.taskId).toBe("T-1");
    expect(data.files).toHaveLength(1);
    expect(data.diffs["a.py"].lines).toContain("+new");
    // the "+new" row anchors to the new side
    const addIdx = data.diffs["a.py"].lines.findIndex((l) => l === "+new");
    expect(data.diffs["a.py"].meta[addIdx].side).toBe("new");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-server.test.ts`
Expected: FAIL — cannot resolve `../src/review-server.js`.

- [ ] **Step 3: Write minimal implementation**

```ts
// pi-ext/factory-watch/src/review-server.ts
import {
  computeFileDiffText,
  computeImplementingFileDiffText,
} from "./review-diff.js";
import type { FileStat } from "./review-diff.js";
import { mapDiffRows } from "./review-model.js";
import type { DiffRowMeta } from "./review-model.js";
import type { ReviewGuide } from "./review-guide.js";

export interface ReviewPageData {
  taskId: string;
  banner: string;
  implementing: boolean;
  guide: ReviewGuide | null;
  files: FileStat[];
  diffs: Record<string, { lines: string[]; meta: DiffRowMeta[] }>;
}

export function buildReviewPageData(
  cwd: string,
  startCommit: string,
  files: FileStat[],
  opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide | null; taskId: string },
): ReviewPageData {
  const implementing = opts.implementing ?? false;
  const diffs: ReviewPageData["diffs"] = {};
  for (const f of files) {
    const text = implementing
      ? computeImplementingFileDiffText(cwd, f.path)
      : computeFileDiffText(cwd, startCommit, f.path);
    const lines = text.split("\n");
    diffs[f.path] = { lines, meta: mapDiffRows(lines) };
  }
  return {
    taskId: opts.taskId,
    banner: opts.banner ?? "",
    implementing,
    guide: opts.guide ?? null,
    files,
    diffs,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-server.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-server.ts pi-ext/factory-watch/test/review-server.test.ts
git commit -m "feat: buildReviewPageData for the web review surface"
```

---

### Task 2: The HTTP server — routes, decision Promise, lifecycle

**Files:**
- Modify: `pi-ext/factory-watch/src/review-server.ts`
- Test: `pi-ext/factory-watch/test/review-server.test.ts`

**Interfaces:**
- Consumes: `buildReviewPageData` (Task 1); `renderReviewHtml` (Task 3 — for this task stub it as `() => "<html></html>"` and replace in Task 3); `ReviewDecisionPayload` from `review-model.js`.
- Produces:
  - `interface RunningReviewServer { url: string; port: number; decision: Promise<ReviewDecisionPayload | null>; close(): void }`
  - `function startReviewServer(data: ReviewPageData): Promise<RunningReviewServer>` — binds `127.0.0.1:0`, resolves once listening. `decision` resolves with the posted payload (then the server closes), or `null` if `close()` is called before any post.

- [ ] **Step 1: Write the failing test**

```ts
// append to pi-ext/factory-watch/test/review-server.test.ts
import { startReviewServer } from "../src/review-server.js";

async function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

describe("startReviewServer", () => {
  test("serves /api/review and accepts a decision, resolving the promise", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-9" });
    const srv = await startReviewServer(data);
    try {
      const review = await (await fetch(`${srv.url}/api/review`)).json();
      expect(review.taskId).toBe("T-9");

      const payload = { decision: "approve", annotations: [], reviewedFiles: ["a.py"] };
      const res = await post(`${srv.url}/api/decision`, payload);
      expect((await res.json()).ok).toBe(true);

      const decided = await srv.decision;
      expect(decided).not.toBeNull();
      expect(decided!.decision).toBe("approve");
      expect(decided!.reviewedFiles).toEqual(["a.py"]);
    } finally {
      srv.close();
    }
  });

  test("close() before any post resolves the decision to null", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-0" });
    const srv = await startReviewServer(data);
    srv.close();
    expect(await srv.decision).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-server.test.ts`
Expected: FAIL — `startReviewServer` not exported.

- [ ] **Step 3: Write minimal implementation**

```ts
// append to pi-ext/factory-watch/src/review-server.ts
import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import type { ReviewDecisionPayload } from "./review-model.js";
import { renderReviewHtml } from "./review-html.js"; // Task 3

export interface RunningReviewServer {
  url: string;
  port: number;
  decision: Promise<ReviewDecisionPayload | null>;
  close(): void;
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => resolve(raw));
  });
}

export function startReviewServer(data: ReviewPageData): Promise<RunningReviewServer> {
  return new Promise((resolveStart) => {
    let resolveDecision!: (d: ReviewDecisionPayload | null) => void;
    const decision = new Promise<ReviewDecisionPayload | null>((r) => (resolveDecision = r));
    let settled = false;

    const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
      const url = req.url ?? "/";
      if (req.method === "GET" && url === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(renderReviewHtml());
        return;
      }
      if (req.method === "GET" && url === "/api/review") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(data));
        return;
      }
      if (req.method === "POST" && url === "/api/decision") {
        const payload = JSON.parse(await readBody(req)) as ReviewDecisionPayload;
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        if (!settled) { settled = true; resolveDecision(payload); }
        server.close();
        return;
      }
      res.writeHead(404);
      res.end();
    });

    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolveStart({
        url: `http://127.0.0.1:${port}`,
        port,
        decision,
        close() {
          if (!settled) { settled = true; resolveDecision(null); }
          server.close();
        },
      });
    });
  });
}
```

Also add a temporary stub module so this task compiles before Task 3:

```ts
// pi-ext/factory-watch/src/review-html.ts  (placeholder; replaced in Task 3)
export function renderReviewHtml(): string {
  return "<!doctype html><html><body>review</body></html>";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-server.test.ts`
Expected: PASS (uses Node's global `fetch`; requires Node 18+, already the repo baseline).

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-server.ts pi-ext/factory-watch/src/review-html.ts pi-ext/factory-watch/test/review-server.test.ts
git commit -m "feat: loopback HTTP review server with decision promise"
```

---

### Task 3: The in-page client (self-contained HTML/JS/CSS)

**Files:**
- Modify: `pi-ext/factory-watch/src/review-html.ts` (replace the stub)
- Test: `pi-ext/factory-watch/test/review-html.test.ts`

**Interfaces:**
- Produces: `function renderReviewHtml(): string` — a complete HTML document with inline `<style>` and `<script>`. The script fetches `/api/review`, renders the file tree + per-file diffs (CSS-colored add/del/context rows) with a `+`-per-row comment affordance, a comment sidebar with a running count, per-file reviewed checkboxes, and approve/reject buttons; on submit it POSTs a `ReviewDecisionPayload` to `/api/decision` and shows a "you can close this tab" message.

- [ ] **Step 1: Write the failing test**

```ts
// pi-ext/factory-watch/test/review-html.test.ts
import { describe, expect, test } from "vitest";
import { renderReviewHtml } from "../src/review-html.js";

describe("renderReviewHtml", () => {
  const html = renderReviewHtml();
  test("is a self-contained document with no external resource references", () => {
    expect(html).toMatch(/<!doctype html>/i);
    expect(html).toContain("/api/review");
    expect(html).toContain("/api/decision");
    // no external network references (CSP-friendly, loopback-only)
    expect(html).not.toMatch(/src=["']https?:/);
    expect(html).not.toMatch(/href=["']https?:/);
  });
  test("wires approve/reject controls", () => {
    expect(html).toContain('id="approve"');
    expect(html).toContain('id="reject"');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-html.test.ts`
Expected: FAIL — stub HTML lacks the endpoints/controls.

- [ ] **Step 3: Write the implementation**

Replace `review-html.ts` with a single template string. The client logic (concrete, not a placeholder):

```ts
// pi-ext/factory-watch/src/review-html.ts
export function renderReviewHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly).
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Review</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.5 ui-monospace, monospace; margin: 0; display: grid; grid-template-columns: 240px 1fr 320px; height: 100vh; }
  #tree { overflow: auto; border-right: 1px solid #8884; padding: 8px; }
  #tree .file { cursor: pointer; padding: 2px 4px; white-space: nowrap; }
  #tree .file.active { background: #8884; }
  #diff { overflow: auto; padding: 8px; }
  #side { overflow: auto; border-left: 1px solid #8884; padding: 8px; }
  .row { white-space: pre-wrap; padding-left: 18px; position: relative; }
  .row.add { background: rgba(0,200,0,.12); }
  .row.del { background: rgba(220,0,0,.12); }
  .row.hunk { color: #6ab; }
  .row .plus { position: absolute; left: 2px; cursor: pointer; opacity: .5; }
  .row .plus:hover { opacity: 1; }
  .banner { color: #c80; padding: 4px 8px; grid-column: 1 / -1; }
  button { font: inherit; margin: 4px 4px 0 0; }
  .cmt { border: 1px solid #8884; padding: 4px; margin: 4px 0; }
</style></head>
<body>
  <div class="banner" id="banner"></div>
  <div id="tree"></div>
  <div id="diff"></div>
  <div id="side">
    <div><strong>Comments (<span id="count">0</span>)</strong></div>
    <div id="cmts"></div>
    <hr>
    <button id="approve">Approve</button>
    <button id="reject">Reject</button>
    <div id="done" hidden>Decision sent — you can close this tab.</div>
  </div>
<script>
(async () => {
  const data = await (await fetch('/api/review')).json();
  const annotations = [];
  const reviewed = new Set();
  let active = data.files[0] && data.files[0].path;
  document.getElementById('banner').textContent = data.banner || '';

  function renderTree() {
    const tree = document.getElementById('tree');
    tree.innerHTML = '';
    for (const f of data.files) {
      const n = annotations.filter(a => a.file === f.path).length;
      const el = document.createElement('div');
      el.className = 'file' + (f.path === active ? ' active' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = reviewed.has(f.path);
      cb.onclick = (e) => { e.stopPropagation(); cb.checked ? reviewed.add(f.path) : reviewed.delete(f.path); };
      el.appendChild(cb);
      el.appendChild(document.createTextNode(' ' + f.status + ' ' + f.path + (n ? ' (' + n + ')' : '')));
      el.onclick = () => { active = f.path; renderAll(); };
      tree.appendChild(el);
    }
  }
  function renderDiff() {
    const box = document.getElementById('diff');
    box.innerHTML = '';
    const d = data.diffs[active]; if (!d) return;
    d.lines.forEach((line, i) => {
      const m = d.meta[i] || { kind: 'meta' };
      const row = document.createElement('div');
      row.className = 'row ' + m.kind;
      if (m.line !== undefined) {
        const plus = document.createElement('span');
        plus.className = 'plus'; plus.textContent = '+';
        plus.onclick = () => addComment(active, m.line, m.side);
        row.appendChild(plus);
      }
      row.appendChild(document.createTextNode(line));
      box.appendChild(row);
    });
  }
  function renderSide() {
    document.getElementById('count').textContent = String(annotations.length);
    const box = document.getElementById('cmts');
    box.innerHTML = '';
    annotations.forEach((a, idx) => {
      const el = document.createElement('div');
      el.className = 'cmt';
      const where = a.line !== undefined ? a.file + ':' + a.line : a.file + ' (file)';
      el.appendChild(document.createTextNode(where + ': ' + a.body + ' '));
      const del = document.createElement('button');
      del.textContent = 'x'; del.onclick = () => { annotations.splice(idx, 1); renderAll(); };
      el.appendChild(del);
      box.appendChild(el);
    });
  }
  function renderAll() { renderTree(); renderDiff(); renderSide(); }
  function addComment(file, line, side) {
    const body = prompt('Comment on ' + file + (line !== undefined ? ':' + line : ''));
    if (body) { annotations.push({ file, line, side, body, severity: 'must-fix' }); renderAll(); }
  }
  async function submit(decision) {
    if (decision === 'reject' && annotations.length === 0) { alert('reject requires at least one comment'); return; }
    await fetch('/api/decision', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ decision, annotations, reviewedFiles: [...reviewed] }),
    });
    document.getElementById('done').hidden = false;
  }
  document.getElementById('approve').onclick = () => submit('approve');
  document.getElementById('reject').onclick = () => submit('reject');
  renderAll();
})();
</script>
</body></html>`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-html.test.ts test/review-server.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-html.ts pi-ext/factory-watch/test/review-html.test.ts
git commit -m "feat: self-contained web review page (diff view, inline comments, approve/reject)"
```

---

### Task 4: Surface choice + browser launch in `index.ts`

**Files:**
- Create: `pi-ext/factory-watch/src/review-surface.ts` (persisted last-choice helper)
- Modify: `pi-ext/factory-watch/src/index.ts` (the `case "review"` block, ~lines 110-130)
- Test: `pi-ext/factory-watch/test/review-surface.test.ts`

**Interfaces:**
- Produces:
  - `function surfacePrefPath(cwd: string): string` = `<cwd>/sessions/.factory-review-surface.json`
  - `function readSurfacePref(cwd: string): "terminal" | "browser"` (default `"terminal"` on missing/garbage)
  - `function writeSurfacePref(cwd: string, pref: "terminal" | "browser"): void` (best-effort; never throws)
  - `function openInBrowser(url: string, platform?: NodeJS.Platform): void` (Windows `cmd /c start "" <url>`; darwin `open <url>`; else `xdg-open <url>`)

- [ ] **Step 1: Write the failing test**

```ts
// pi-ext/factory-watch/test/review-surface.test.ts
import { afterEach, describe, expect, test } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readSurfacePref, writeSurfacePref } from "../src/review-surface.js";

const dirs: string[] = [];
function tmp() { const d = mkdtempSync(join(tmpdir(), "surf-")); dirs.push(d); return d; }
afterEach(() => { for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true }); });

describe("surface pref", () => {
  test("defaults to terminal when unset", () => {
    expect(readSurfacePref(tmp())).toBe("terminal");
  });
  test("round-trips a written pref", () => {
    const d = tmp();
    writeSurfacePref(d, "browser");
    expect(readSurfacePref(d)).toBe("browser");
  });
  test("garbage file falls back to terminal", () => {
    const d = tmp();
    // sessions/ may not exist yet; writeSurfacePref must create it, so write then corrupt
    writeSurfacePref(d, "browser");
    writeFileSync(join(d, "sessions", ".factory-review-surface.json"), "not json");
    expect(readSurfacePref(d)).toBe("terminal");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-surface.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```ts
// pi-ext/factory-watch/src/review-surface.ts
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type Surface = "terminal" | "browser";

export function surfacePrefPath(cwd: string): string {
  return join(cwd, "sessions", ".factory-review-surface.json");
}

export function readSurfacePref(cwd: string): Surface {
  try {
    const p = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as { surface?: string };
    return p.surface === "browser" ? "browser" : "terminal";
  } catch {
    return "terminal";
  }
}

export function writeSurfacePref(cwd: string, pref: Surface): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify({ surface: pref }), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the choice
  }
}

export function openInBrowser(url: string, platform: NodeJS.Platform = process.platform): void {
  let child;
  if (platform === "win32") {
    child = spawn("cmd", ["/c", "start", "", url], { detached: true, stdio: "ignore" });
  } else if (platform === "darwin") {
    child = spawn("open", [url], { detached: true, stdio: "ignore" });
  } else {
    child = spawn("xdg-open", [url], { detached: true, stdio: "ignore" });
  }
  child.unref();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi-ext/factory-watch && npx vitest run test/review-surface.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the surface choice into `index.ts`'s `case "review"`**

Replace the body of the `review` case (after `files`/`opts` are computed, before `writeReviewDecision`) with:

```ts
// existing: compute `files`, `opts`, `guide` ...
const remembered = readSurfacePref(ctx.cwd);
const pick = await ctx.ui.select(
  "Open review in",
  remembered === "browser" ? ["Browser", "Terminal"] : ["Terminal", "Browser"],
);
const surface: Surface = pick === "Browser" ? "browser" : "terminal";
writeSurfacePref(ctx.cwd, surface);

let decision: ReviewDecisionPayload | null = null;
if (surface === "browser") {
  try {
    const pageData = buildReviewPageData(ctx.cwd, hr.start_commit, files, {
      taskId: rec.task_id, implementing: opts.implementing, banner: opts.banner, guide: opts.guide ?? null,
    });
    const srv = await startReviewServer(pageData);
    ctx.ui.notify(`review open in your browser: ${srv.url}`, "info");
    openInBrowser(srv.url);
    decision = await srv.decision; // resolves on submit; null if the server is closed without a post
  } catch (err) {
    ctx.ui.notify(`browser review failed (${String(err)}); falling back to terminal`, "warning");
  }
}
if (decision === null && surface === "browser") {
  // browser closed without submitting, or bind failed: fall back to the TUI
  const r = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
  decision = buildDecision(r.decision, r.annotations, r.reviewedFiles);
} else if (surface === "terminal") {
  const r = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
  decision = buildDecision(r.decision, r.annotations, r.reviewedFiles);
}
if (decision !== null) {
  writeReviewDecision(reviewDecisionPath(ctx.cwd, rec.session_id), decision);
}
```

Add imports to `index.ts`:

```ts
import { buildReviewPageData, startReviewServer } from "./review-server.js";
import { openInBrowser, readSurfacePref, writeSurfacePref } from "./review-surface.js";
import type { Surface } from "./review-surface.js";
import type { ReviewDecisionPayload } from "./review-model.js";
```

- [ ] **Step 6: Typecheck + full TS suite**

Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: exit 0.
Run: `cd pi-ext/factory-watch && npx vitest run`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pi-ext/factory-watch/src/review-surface.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/review-surface.test.ts
git commit -m "feat: choose Terminal or Browser review surface at review time"
```

---

### Task 5: End-to-end verification of Plan B

**Files:** none (verification only).

- [ ] **Step 1: Full gates**

Run: `uv run python scripts/gates/all.py`
Expected: exit 0.
Run: `cd pi-ext/factory-watch && npx vitest run`
Expected: all pass.

- [ ] **Step 2: Manual smoke (documented for the human)**

Trigger a real review; choose **Browser**; confirm the tab opens, the file tree + diffs render, clicking `+` on a line adds a `file:line` comment visible in the sidebar with a live count, the reviewed checkbox works, **Reject** with a comment writes `review-decision.json` and the dev agent receives `src/x:NN [must-fix]: …`. Re-trigger review and confirm **Browser** is now the remembered default (listed first). Choose **Terminal** and confirm the TUI path still works and updates the remembered default back.

- [ ] **Step 3: Edge check — close without submitting**

Open Browser review, close the tab without clicking approve/reject, then in Pi confirm the TUI fallback appears (the server's `decision` resolves `null` only on `close()`; document that closing the tab alone does not auto-resolve — the human re-triggers review or the server is closed on the next review request). If auto-detection of a closed tab is desired later, that is a follow-up (out of scope).

- [ ] **Step 4: Commit any notes**

```bash
git add -A && git commit -m "chore: Plan B verification notes" || echo "nothing to commit"
```
