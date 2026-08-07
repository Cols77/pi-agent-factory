import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

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

function mockSystemCli(): void {
  spawnSync.mockImplementation((_bin: string, args: string[]) => {
    const sub = args[4];
    if (sub === "scope") return { status: 0, stdout: JSON.stringify(SCOPE_LIST), stderr: "" };
    if (sub === "brief") return { status: 0, stdout: JSON.stringify(BRIEF), stderr: "" };
    if (sub === "matrix") return { status: 0, stdout: JSON.stringify(MATRIX), stderr: "" };
    if (sub === "timeline") return { status: 0, stdout: JSON.stringify(TIMELINE), stderr: "" };
    return { status: 1, stdout: "", stderr: `unexpected sub: ${String(sub)}` };
  });
}

function repo(): string {
  return mkdtempSync(join(tmpdir(), "system-page-"));
}

afterEach(() => {
  stopDocsServer();
  vi.clearAllMocks();
});

describe("renderSystemPageHtml", () => {
  const html = renderSystemPageHtml();

  test("is a complete, self-contained document", () => {
    expect(html).toContain("<!doctype html>");
    expect(html).toContain("</html>");
    expect(html).not.toMatch(/src="https?:/);
    expect(html).not.toMatch(/href="https?:/);
  });

  test("offers a scope picker and brief/matrix/timeline tabs", () => {
    for (const id of ["picker", "scopeList", "scopeErrors", "content", "tabBrief", "tabMatrix", "tabTimeline", "panelBrief", "panelMatrix", "panelTimeline"]) {
      expect(html).toContain(`id="${id}"`);
    }
  });

  test("fetches only the declared local system apis", () => {
    expect(html).toContain("/api/system/scope");
    expect(html).toContain("/api/system/brief?scope=");
    expect(html).toContain("/api/system/matrix?scope=");
    expect(html).toContain("/api/system/timeline?scope=");
  });

  test("renders every claim kind distinctly, from the payload's own kind field", () => {
    // The label must come straight from claim.kind -- no TypeScript-side
    // remapping or filtering of recorded/derived/synthesized/missing.
    expect(html).toContain("claim.kind");
    expect(html).toContain("claim-' + claim.kind");
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

  test("shows a degraded/stale banner from the payload, not a colour-only cue", () => {
    expect(html).toContain("degraded_reasons");
    expect(html).toContain("degraded");
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

  test("serves brief/matrix/timeline JSON for a scope", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    const brief = await (await fetch(`${server.url}/api/system/brief?scope=bundle:evidence-lifecycle`)).json();
    expect(brief).toEqual(BRIEF);
    const matrix = await (await fetch(`${server.url}/api/system/matrix?scope=bundle:evidence-lifecycle`)).json();
    expect(matrix).toEqual(MATRIX);
    const timeline = await (await fetch(`${server.url}/api/system/timeline?scope=bundle:evidence-lifecycle`)).json();
    expect(timeline).toEqual(TIMELINE);
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
    expect((await fetch(`${server.url}/api/system/guide?scope=bundle:x`)).status).toBe(404);
    expect((await fetch(`${server.url}/system/../../etc/passwd`)).status).toBe(404);
  });

  test("stays loopback-only", async () => {
    mockSystemCli();
    const server = await ensureDocsServer(repo());
    expect(server.url).toContain("127.0.0.1");
  });
});
