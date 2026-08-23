import { mkdtempSync } from "node:fs";
import { EventEmitter } from "node:events";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { PassThrough } from "node:stream";
import { afterEach, describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
const spawn = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawn, spawnSync }));

import { ensureDocsServer, stopDocsServer } from "../src/docs-server.js";
import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = {
  scopes: [{ kind: "bundle", ref: "bundle:evidence-lifecycle" }],
  errors: [{ path: "bundles/bad.yaml", bundle_id: "bad", error: "missing label" }],
};

const BRIEF = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  claims: [
    {
      kind: "recorded",
      text: "Evidence lifecycle",
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.yaml", sha256: "a".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
    {
      kind: "missing",
      text: "spec:2026-08-08-does-not-exist.md",
      citations: [],
      spans: [],
      freshness: { state: "n/a", reason: "bundle member does not exist in repo", dependencies: [] },
    },
  ],
  degraded: true,
  degraded_reasons: ["1 declared member(s) do not exist in the repo"],
};

const MATRIX = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  rows: [
    {
      subject: { kind: "sr", ref: "sr:SR-001" },
      status: "passed",
      evidence: ["validation/validation-report.json"],
      freshness: { state: "stale", reason: "requirement content changed", dependencies: [] },
      summary: "metric=x assert=y value=1",
    },
  ],
};

const TIMELINE = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  events: [
    {
      at: null,
      sequence: 1,
      actor: "not-recorded",
      action: "not-recorded",
      subject: { kind: "task", ref: "task:T-001" },
      citation: { kind: "decision", path: "evidence/runs/run-1.json", sha256: "b".repeat(64), anchor: "reviews[0]" },
      freshness: { state: "degraded", reason: "no actor recorded", dependencies: [] },
    },
  ],
  degraded: true,
  degraded_reasons: ["1 event(s) do not have a recorded actor"],
};

const GUIDE = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  sections: [
    {
      kind: "synthesized",
      text: 'This guide covers the declared bundle "Evidence lifecycle".',
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.json", sha256: "a".repeat(64), anchor: null }],
      spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
    {
      kind: "recorded",
      text: "- task:T-001",
      citations: [],
      spans: [],
      freshness: { state: "degraded", reason: null, dependencies: [] },
    },
  ],
};

const HEALTH = {
  health: { classes: [], satisfied: 0, expected: 0, percent: 0, dangling: 0, deferred: 0, proposed: 0 },
  coverage: { total: 0, bundled: 0, unbundled: 0, kinds: [] },
  bundles: [],
  unbundled: {},
  ordering_available: true,
  sr_listed: true,
  degraded: [],
};

const TRAVERSAL = {
  requirement: ["sr:SR-001"],
  tasks: ["task:T-001"],
  design: ["design:DD-001"],
  files: ["src/example.ts"],
};

function childProcess(): EventEmitter & { stdout: PassThrough; stderr: PassThrough; stdin: PassThrough } {
  // stdin + kill + exitCode: the docs server now runs a long-lived
  // `factory.system worker` process whose stdin carries JSON-lines requests,
  // so the fake child must be shaped like the real one.
  return Object.assign(new EventEmitter(), {
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    stdin: new PassThrough(),
    kill: vi.fn(() => true),
    exitCode: null as number | null,
  });
}

function closeChild(
  child: ReturnType<typeof childProcess>,
  stdout: string,
  status = 0,
  stderr = "",
): void {
  queueMicrotask(() => {
    child.stdout.end(stdout);
    child.stderr.end(stderr);
    child.emit("close", status);
  });
}

function crashChild(child: ReturnType<typeof childProcess>): void {
  // Exit on a microtask so the worker's own exit listeners are attached
  // before the event fires (a synchronous emit during spawn would be lost).
  queueMicrotask(() => child.emit("exit", 1, null));
}

// Serves the JSON-lines worker protocol against a fake child: one response
// line per request line, values from `handlers` keyed by worker command.
function serveWorker(
  child: ReturnType<typeof childProcess>,
  handlers: Record<string, unknown>,
): void {
  const lines = createInterface({ input: child.stdin });
  lines.on("line", (raw) => {
    const req = JSON.parse(raw) as { id: number; cmd: string };
    if (Object.prototype.hasOwnProperty.call(handlers, req.cmd)) {
      child.stdout.write(JSON.stringify({ id: req.id, ok: true, value: handlers[req.cmd] }) + "\n");
    } else {
      child.stdout.write(
        JSON.stringify({
          id: req.id,
          ok: false,
          error: `unexpected worker cmd: ${req.cmd}`,
          kind: "WorkerProtocolError",
        }) + "\n",
      );
    }
  });
}

// The docs server spawns exactly one long-lived worker process; when the
// worker answers, the one-shot per-command spawn is never used.
function isWorkerArgv(args: string[]): boolean {
  return args[4] === "coherence.navigate" && args[5] === "worker";
}

function mockAsyncSystemCli(): void {
  spawn.mockImplementation((_bin: string, args: string[]) => {
    const child = childProcess();
    if (isWorkerArgv(args)) {
      serveWorker(child, { health: HEALTH, traversal: TRAVERSAL });
      return child;
    }
    closeChild(child, "", 1, `unexpected sub: ${String(args[4])}`);
    return child;
  });
}

function mockSystemCli(): void {
  spawnSync.mockImplementation((_bin: string, args: string[]) => {
    const sub = args[4];
    if (sub === "scope") return { status: 0, stdout: JSON.stringify(SCOPE_LIST), stderr: "" };
    if (sub === "brief") return { status: 0, stdout: JSON.stringify(BRIEF), stderr: "" };
    if (sub === "matrix") return { status: 0, stdout: JSON.stringify(MATRIX), stderr: "" };
    if (sub === "timeline") return { status: 0, stdout: JSON.stringify(TIMELINE), stderr: "" };
    if (sub === "guide") return { status: 0, stdout: JSON.stringify(GUIDE), stderr: "" };
    return { status: 1, stdout: "", stderr: `unexpected sub: ${String(sub)}` };
  });
}

function repo(): string {
  return mkdtempSync(join(tmpdir(), "system-page-"));
}

afterEach(() => {
  stopDocsServer();
  vi.clearAllMocks();
  // clearAllMocks keeps implementations installed by earlier tests; a stale
  // worker-shaped spawn would leak into the spawnSync-fallback tests, so the
  // bare mock is restored too (each test installs what it needs).
  spawn.mockReset();
  spawnSync.mockReset();
});

describe("renderSystemPageHtml", () => {
  const html = renderSystemPageHtml();

  test("is a complete, self-contained document", () => {
    expect(html).toContain("<!doctype html>");
    expect(html).toContain("</html>");
    expect(html).not.toMatch(/src="https?:/);
    expect(html).not.toMatch(/href="https?:/);
  });

  test("never truncates a Matrix chip title -- .matrix-row is its own per-row grid so wrapping cannot break alignment", () => {
    // Regression pin for the CSS override that clipped ref-chip titles on
    // the Matrix tab (`.matrix-subject .chip-title { ... white-space:
    // nowrap }`). `.ref-chip .chip-title { overflow-wrap: anywhere }`
    // (which makes long titles wrap instead of clip) must not be beaten by
    // a nowrap/ellipsis rule scoped to `.matrix-subject`.
    expect(html).not.toMatch(/\.matrix-subject\s+\.chip-title\s*\{[^}]*white-space:\s*nowrap/);
    expect(html).not.toMatch(/\.matrix-subject\s+\.chip-title\s*\{[^}]*text-overflow:\s*ellipsis/);
    expect(html).toMatch(/\.ref-chip\s+\.chip-title\s*\{[^}]*overflow-wrap:\s*anywhere/);
  });

  test("offers a scope picker and brief/matrix/timeline/guide tabs", () => {
    for (const id of [
      "picker", "scopeList", "scopeErrors", "content",
      "tabBrief", "tabMatrix", "tabTimeline", "tabGuide",
      "panelBrief", "panelMatrix", "panelTimeline", "panelGuide",
    ]) {
      expect(html).toContain(`id="${id}"`);
    }
  });

  test("fetches only the declared local system apis", () => {
    expect(html).toContain("/api/system/health");
    expect(html).toContain("/api/system/brief?scope=");
    expect(html).toContain("/api/system/matrix?scope=");
    expect(html).toContain("/api/system/timeline?scope=");
    expect(html).toContain("/api/system/guide?scope=");
    // The browser never has an export affordance -- export is CLI-only,
    // explicit, user-initiated (design SS4.5).
    expect(html).not.toContain("--export");
    // Inc 3B Task 7: `--why-required` obligation data is surfaced only
    // through the eng_present agent tool (eng-context-tool-format.ts); the
    // /system page has no projection for it and must never fetch or expect
    // a worker `present` action.
    expect(html).not.toContain("/api/system/present");
  });

  test("the guide tab falls back to a plain notice, never synthesizes prose client-side, if its own fetch fails", () => {
    expect(html).toContain("renderGuideFallback");
    // A failed guide fetch must not be folded into the shared failure gate
    // that hides brief/matrix/timeline too -- only these three participate.
    expect(html, "searchGo@" + html.indexOf("searchGo") + " gate@" + html.indexOf("[briefRes, matrixRes, timelineRes].find((r) => !r.ok)") + " len=" + html.length).toContain("[briefRes, matrixRes, timelineRes].find((r) => !r.ok)");
  });

  test("renders every claim kind distinctly, from the payload's own kind field", () => {
    // The label must come straight from claim.kind -- no TypeScript-side
    // remapping or filtering of recorded/derived/synthesized/missing. The kind
    // class is built by concatenating 'claim claim-' with the payload field;
    // the regex tolerates the compiler's whitespace choices in the assembled
    // inline script (SP-B Task 5 split embeds module sources).
    expect(html).toContain("claim.kind");
    expect(html).toMatch(/claim claim-[\"']\s*\+\s*claim\.kind/);
  });

  test("never hides missing rows", () => {
    expect(html).not.toMatch(/kind\s*===?\s*['"]missing['"]\s*\)\s*return/);
    expect(html).not.toContain("filter(claim => claim.kind !== 'missing')");
  });

  test("text-labels freshness state, not colour alone", () => {
    expect(html).toContain("freshness.state");
    expect(html).toContain("createTextNode(freshness.state)");
  });

  test("escapes all payload-derived text via DOM text nodes, never raw innerHTML interpolation", () => {
    expect(html).toContain("createTextNode");
    // innerHTML may only ever be reset to a quoted literal (to clear a
    // container before repopulating it via createTextNode/appendChild) --
    // never assigned an expression built from fetched JSON.
    expect(html).not.toMatch(/\.innerHTML\s*=\s*[^\s'"]/);
  });

  test("never recomputes ordering -- events and rows are rendered in payload order", () => {
    expect(html).not.toContain(".sort(");
  });

  test("a health metric tile's rule comes straight from the vocabulary entry's denominator_rule field, never a browser-side regex slice of the full definition", () => {
    expect(html).not.toContain("firstSentence");
    expect(html).toContain("term.denominator_rule");
  });

  test("shows a degraded/stale banner from the payload, not a colour-only cue", () => {
    expect(html).toContain("degraded_reasons");
    expect(html).toContain("degraded");
  });

  test("the page inlines the vocabulary and remediation tables", () => {
    expect(html).toContain("var VOCABULARY =");
    expect(html).toContain("var REMEDIATION =");
    expect(html).toContain('"recorded"');
    expect(html).toContain('"sr_unsatisfied"');
  });

  test("the page declares mutable label bindings and a setter", () => {
    expect(html).toContain("var LABELS =");
    expect(html).toContain("var ALIASES =");
    expect(html).toContain("function setLabels(");
  });

  test("gloss text uses --text-muted, never --text-dim", () => {
    const gloss = html.match(/\.gloss\s*\{[^}]*\}/)?.[0] ?? "";
    expect(gloss).toContain("--text-muted");
    expect(gloss).not.toContain("--text-dim");
  });

  // Task 9: refChip must reach the page, and must be declared after the
  // bindings it reads.
  test("refChip is inlined into the page after the label bindings", () => {
    expect(html).toContain("function refChip");
    expect(html.indexOf("var LABELS =")).toBeLessThan(html.indexOf("function refChip"));
  });
});

describe("GET /system and /api/system/*", () => {
  test("serves the navigator shell on /system", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/system`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("<!doctype html>");
  });

  test("serves the same shell when a scope query param is present", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/system?scope=bundle:evidence-lifecycle`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("<!doctype html>");
  });

  test("does not become the default landing page", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const res = await fetch(server.url);
    const body = await res.text();
    expect(body).toContain("<title>Docs</title>");
  });

  test("serves the declared scope list, including the legitimate empty state", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ scopes: [], errors: [] }), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/scope`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ scopes: [], errors: [] });
  });

  test("serves scope errors alongside resolvable scopes", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const body = await (await fetch(`${server.url}/api/system/scope`)).json();
    expect(body).toEqual(SCOPE_LIST);
  });

  test("serves health and traversal JSON through the long-lived worker", async () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "sync runner must not be used" });
    mockAsyncSystemCli();
    const server = await ensureDocsServer(repo());

    const health = await fetch(`${server.url}/api/system/health`);
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual(HEALTH);
    const traversal = await fetch(`${server.url}/api/system/traversal?scope=sr:SR-001`);
    expect(traversal.status).toBe(200);
    expect(await traversal.json()).toEqual(TRAVERSAL);
    // One long-lived worker process served both projections; the one-shot
    // per-command CLI was never spawned (and the sync runner never used).
    expect(spawn).toHaveBeenCalledTimes(1);
    expect(spawn).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-u", "-m", "coherence.navigate", "worker", "--repo-root", expect.any(String)],
      expect.objectContaining({ stdio: ["pipe", "pipe", "pipe"] }),
    );
    expect(spawnSync).not.toHaveBeenCalled();
  });

  test("reports a worker-served command failure as JSON", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(HEALTH), stderr: "" });
    spawn.mockImplementation((_bin: string, args: string[]) => {
      const child = childProcess();
      if (isWorkerArgv(args)) serveWorker(child, {}); // every command is unknown
      return child;
    });
    const server = await ensureDocsServer(repo());

    const res = await fetch(`${server.url}/api/system/health`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("unexpected worker cmd");
  });

  test("reports an async traversal CLI failure as JSON", async () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "sync runner must not be used" });
    spawn.mockImplementation((_bin: string, args: string[]) => {
      const child = childProcess();
      if (isWorkerArgv(args)) crashChild(child);
      else closeChild(child, "", 1, "traversal unavailable"); // the fallback one-shot
      return child;
    });
    const server = await ensureDocsServer(repo());

    const res = await fetch(`${server.url}/api/system/traversal?scope=bundle:one`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("traversal unavailable");
  });

  test("a crashed worker never starves a route: requests fall back to the one-shot CLI", async () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "sync runner must not be used" });
    spawn.mockImplementation((_bin: string, args: string[]) => {
      const child = childProcess();
      if (isWorkerArgv(args)) {
        crashChild(child);
      } else if (args[4] === "health") {
        closeChild(child, JSON.stringify(HEALTH));
      } else if (args[4] === "traversal") {
        closeChild(child, JSON.stringify(TRAVERSAL));
      } else {
        closeChild(child, "", 1, `unexpected sub: ${String(args[4])}`);
      }
      return child;
    });
    const server = await ensureDocsServer(repo());

    const health = await fetch(`${server.url}/api/system/health`);
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual(HEALTH);
    const traversal = await fetch(`${server.url}/api/system/traversal?scope=sr:SR-001`);
    expect(traversal.status).toBe(200);
    expect(await traversal.json()).toEqual(TRAVERSAL);
    // The worker was attempted for each request and crashed; every request
    // still answered through the one-shot async CLI fallback.
    expect(spawn.mock.calls.some((call) => isWorkerArgv(call[1] as string[]))).toBe(true);
    expect(spawn.mock.calls.some((call) => !isWorkerArgv(call[1] as string[]))).toBe(true);
  });

  test("serves brief/matrix/timeline/guide JSON for a scope", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const brief = await (await fetch(`${server.url}/api/system/brief?scope=bundle:evidence-lifecycle`)).json();
    expect(brief).toEqual(BRIEF);
    const matrix = await (await fetch(`${server.url}/api/system/matrix?scope=bundle:evidence-lifecycle`)).json();
    expect(matrix).toEqual(MATRIX);
    const timeline = await (await fetch(`${server.url}/api/system/timeline?scope=bundle:evidence-lifecycle`)).json();
    expect(timeline).toEqual(TIMELINE);
    const guide = await (await fetch(`${server.url}/api/system/guide?scope=bundle:evidence-lifecycle`)).json();
    expect(guide).toEqual(GUIDE);
  });

  test("reports a Python guide failure as json, distinctly from a hard 404", async () => {
    spawnSync.mockImplementation((_bin: string, args: string[]) => {
      const sub = args[4];
      if (sub === "scope") return { status: 0, stdout: JSON.stringify(SCOPE_LIST), stderr: "" };
      if (sub === "guide") {
        return { status: 1, stdout: "", stderr: JSON.stringify({ error: "synthesis failed", kind: "RuntimeError" }) };
      }
      return { status: 1, stdout: "", stderr: `unexpected sub: ${String(sub)}` };
    });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/guide?scope=bundle:evidence-lifecycle`);
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("synthesis failed");
  });

  test("reports a Python CLI failure as json instead of crashing", async () => {
    spawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: JSON.stringify({ error: "invalid scope ref: 'task:T-001' (expected bundle:<id> or sr:<id>)", kind: "ScopeKindError" }),
    });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/brief?scope=task:T-001`);
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toContain("invalid scope ref");
  });

  test("rejects arbitrary sub-paths instead of falling through to a handler", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    expect((await fetch(`${server.url}/api/system/../secret`)).status).toBe(404);
    expect((await fetch(`${server.url}/api/system/export`)).status).toBe(404);
    expect((await fetch(`${server.url}/system/../../etc/passwd`)).status).toBe(404);
  });

  test("has no worker `present` route: obligation data stays agent-tool-only (Inc 3B Task 7)", async () => {
    // `--why-required` obligations flow through eng_present (eng-context-
    // tools.ts) -> loadSystemPresent (system-cli.ts) -> formatObligationLines
    // (eng-context-tool-format.ts), never through the /system page's worker
    // protocol. No route or worker cmd named "present" exists here.
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    expect((await fetch(`${server.url}/api/system/present`)).status).toBe(404);
  });

  test("stays loopback-only", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    expect(server.url).toContain("127.0.0.1");
  });
});
