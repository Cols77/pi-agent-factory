import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";
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
    expect(html).toContain(".readiness-strong { border-left-color: var(--fresh); }");
    expect(html).toContain(".readiness-medium { border-left-color: var(--signal); }");
  });

  it("becomes one column on narrow viewports", () => {
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#tabs\s*\{[^}]*overflow-x:\s*auto/);
    expect(html).toMatch(/body\.focus\.picker-open #picker nav[\s\S]*display:\s*block/);
  });

  it("lets the header and banner consume their real height without clipping content", () => {
    expect(html).toMatch(/body\s*\{[^}]*display:\s*grid[^}]*grid-template-rows:\s*auto auto minmax\(0, 1fr\)/);
    expect(html).toMatch(/body\s*\{[^}]*height:\s*100dvh/);
    expect(html).toMatch(/#layout\s*\{[^}]*min-height:\s*0/);
    expect(html).not.toContain("calc(100vh -");
  });

  it("keeps operational metadata at a readable twelve-pixel minimum", () => {
    expect(html).toMatch(/\.eyebrow, \.section-heading > span\s*\{[^}]*font:\s*650 12px/);
    expect(html).toMatch(/\.badge\s*\{[^}]*font:\s*650 12px/);
    expect(html).toMatch(/\.trace-spine-label\s*\{[^}]*font:\s*650 12px/);
    expect(html).not.toMatch(/(?:font|font-size):[^;}]*\b(?:10|11)px\b/);
  });

  it("relates tabs and panels accessibly", () => {
    expect(html).toContain('id="panelBrief" class="panel" role="tabpanel" aria-labelledby="tabBrief"');
    expect(html).toContain('id="tabBrief" class="tab" role="tab" tabindex="0"');
    expect(html).toContain('id="tabMatrix" class="tab" role="tab" tabindex="-1"');
  });
});

const HEALTH = {
  health: {
    classes: ["bound", "covered", "current", "deferred", "validated"].map((name) => ({
      name,
      satisfied: 0,
      expected: 0,
      exempt: 0,
    })),
    satisfied: 0,
    expected: 0,
    percent: 100,
  },
  bundles: [{
    id: "safety-governor",
    label: "Deterministic safety governor",
    readiness: "weak",
    readiness_counts: {
      sr_total: 15,
      bound: 8,
      covered: 5,
      current: 3,
      deferred: 1,
      validated: 2,
    },
    members: 15,
  }],
  unbundled: {},
};

function jsonResponse(body: unknown): Promise<Response> {
  return Promise.resolve({ ok: true, status: 200, json: async () => body } as Response);
}

function scopeResponse(pathname: string): Promise<Response> {
  const scope = { kind: "bundle", ref: "bundle:safety-governor" };
  if (pathname === "/api/system/brief") return jsonResponse({ scope, claims: [], degraded: false, degraded_reasons: [] });
  if (pathname === "/api/system/matrix") return jsonResponse({ scope, rows: [] });
  if (pathname === "/api/system/timeline") return jsonResponse({ scope, events: [], degraded: false, degraded_reasons: [] });
  if (pathname === "/api/system/guide") return jsonResponse({ scope, sections: [] });
  return Promise.reject(new Error(`unmocked fetch: ${pathname}`));
}

function loadDom(fetchMock: ReturnType<typeof vi.fn>, url = "http://localhost/system"): JSDOM {
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously",
    resources: "usable",
    url,
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("system navigator landing and focus modes", () => {
  it("reveals a cleared current-scope workspace while core evidence is pending", async () => {
    let resolveBrief!: (response: Response) => void;
    const pendingBrief = new Promise<Response>((resolve) => { resolveBrief = resolve; });
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/brief") return pendingBrief;
      return scopeResponse(url.pathname);
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());

    (doc.querySelector(".feature-row") as HTMLElement).click();

    expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(false);
    expect((doc.querySelector("#landingPanel") as HTMLElement).hidden).toBe(true);
    expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:safety-governor");
    expect((doc.querySelector("#loading") as HTMLElement).hidden).toBe(false);
    expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("true");
    expect(doc.querySelector("#panelBrief")?.textContent).not.toContain("No claims recorded");

    resolveBrief(await scopeResponse("/api/system/brief"));
  });

  it("loads the current trace when a deep link initially selects Trace", async () => {
    const graph = {
      nodes: [
        { id: "SR-NEW", kind: "sr", title: "Current requirement", path: "requirements/SR-NEW.md" },
        { id: "T-NEW", kind: "task", title: "Current task", path: "tasks/T-NEW.md" },
      ],
      edges: [{ src: "T-NEW", dst: "SR-NEW", kind: "satisfies" }],
    };
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/graph") return jsonResponse(graph);
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "sr", ref: "sr:SR-NEW" }, claims: [], rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock, "http://localhost/system?scope=sr%3ASR-NEW#trace");
    const doc = dom.window.document;

    await vi.waitFor(() => expect(doc.querySelector("#panelTrace")?.textContent).toContain("T-NEW"));
    expect(doc.querySelector("#tabTrace")?.getAttribute("aria-selected")).toBe("true");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/graph"), expect.anything());
  });

  it("clears prior traversal and trace evidence as soon as another scope starts", async () => {
    let resolveStory!: (response: Response) => void;
    const pendingStory = new Promise<Response>((resolve) => { resolveStory = resolve; });
    const graph = {
      nodes: [
        { id: "SR-OLD", kind: "sr", title: "Old requirement", path: "requirements/SR-OLD.md" },
        { id: "T-OLD", kind: "task", title: "Old trace task", path: "tasks/T-OLD.md" },
      ],
      edges: [{ src: "T-OLD", dst: "SR-OLD", kind: "satisfies" }],
    };
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      const scope = url.searchParams.get("scope");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/graph") return jsonResponse(graph);
      if (url.pathname === "/api/system/story") return pendingStory;
      if (url.pathname === "/api/system/traversal") {
        return jsonResponse({ requirement: "SR-OLD", tasks: ["T-OLD"], design: ["old-design"], files: ["old.ts"] });
      }
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "sr", ref: scope }, claims: [],
          rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock, "http://localhost/system?scope=sr%3ASR-OLD#trace");
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector("#traversalPath")?.textContent ?? "").toContain("old.ts"));
    await vi.waitFor(() => expect(doc.querySelector("#panelTrace")?.textContent ?? "").toContain("T-OLD"));

    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "task:T-NEW";
    doc.querySelector<HTMLElement>("#searchGo")!.click();

    expect(doc.querySelector("#traversalPath")?.textContent).not.toContain("old.ts");
    expect(doc.querySelector("#panelTrace")?.textContent).not.toContain("T-OLD");
    expect(doc.querySelector("#scopeRef")?.textContent).toBe("task:T-NEW");
    expect((doc.querySelector("#loading") as HTMLElement).hidden).toBe(false);

    resolveStory(await jsonResponse({ scope: { kind: "task", ref: "task:T-NEW" }, task: { id: "T-NEW" }, runs: [] }));
  });
  it("aborts a stalled health scan and exposes an actionable retry", async () => {
    vi.useFakeTimers();
    let healthSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname !== "/api/system/health") return scopeResponse(url.pathname);
      healthSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        healthSignal?.addEventListener("abort", () => reject(new Error("aborted")));
      });
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;

    await vi.advanceTimersByTimeAsync(15_000);
    expect(healthSignal?.aborted).toBe(true);
    expect(doc.querySelector("#healthStatus")?.textContent).toContain("taking longer than expected");
    expect((doc.querySelector("#retryHealth") as HTMLButtonElement).hidden).toBe(false);
    expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false");
    vi.useRealTimers();
  });

  it("renders honest zero metrics and an actionable feature directory", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      return scopeResponse(url.pathname);
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;

    await vi.waitFor(() => expect(doc.querySelectorAll(".health-metric")).toHaveLength(5));
    expect(doc.querySelector("#landingPanel")?.hasAttribute("hidden")).toBe(false);
    expect(doc.querySelector("#scopeWorkspace")?.hasAttribute("hidden")).toBe(true);
    expect(doc.querySelector("#healthSummary")?.textContent).toContain("No measurable evidence");
    const feature = doc.querySelector(".feature-row");
    expect(feature?.textContent).toContain("Deterministic safety governor");
    expect(feature?.textContent).toContain("15 artifacts");
    expect(feature?.textContent).toContain("15 SR");
    expect(feature?.textContent).toContain("weak");
    expect(doc.querySelector(".scope-group-title")?.tagName).toBe("BUTTON");

    (feature as HTMLElement).click();
    expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("true");
    expect((doc.querySelector("#loading") as HTMLElement).hidden).toBe(false);
    await vi.waitFor(() => expect(doc.querySelector("#scopeWorkspace")?.hasAttribute("hidden")).toBe(false));
    expect(doc.querySelector("#landingPanel")?.hasAttribute("hidden")).toBe(true);
    expect(feature?.getAttribute("aria-current")).toBe("page");
    expect(doc.querySelector("#scopeHeader")?.textContent).toBe("Deterministic safety governor");
    expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:safety-governor");
    expect((doc.querySelector("#tabBrief") as HTMLElement).hidden).toBe(false);
    expect((doc.querySelector("#tabMatrix") as HTMLElement).hidden).toBe(false);
    expect((doc.querySelector("#tabStory") as HTMLElement).hidden).toBe(true);
    expect((doc.querySelector("#tabReverse") as HTMLElement).hidden).toBe(true);

    const brief = doc.querySelector("#tabBrief") as HTMLElement;
    const matrix = doc.querySelector("#tabMatrix") as HTMLElement;
    brief.focus();
    brief.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(doc.activeElement).toBe(matrix);
    expect(matrix.getAttribute("aria-selected")).toBe("true");
    expect(matrix.getAttribute("tabindex")).toBe("0");
    expect(brief.getAttribute("tabindex")).toBe("-1");

    matrix.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "End", bubbles: true }));
    expect(doc.activeElement).toBe(doc.querySelector("#tabTrace"));
    (doc.activeElement as HTMLElement).dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    expect(doc.activeElement).toBe(brief);
  });

  it("shows contextual bundle content while bounding the optional traversal", async () => {
    vi.useFakeTimers();
    let traversalSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/traversal") {
        traversalSignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          traversalSignal?.addEventListener("abort", () => reject(new Error("aborted")));
        });
      }
      return scopeResponse(url.pathname);
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());

    (doc.querySelector(".feature-row") as HTMLElement).click();
    await vi.waitFor(() => expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(false));
    expect((doc.querySelector("#tabBrief") as HTMLElement).hidden).toBe(false);
    expect((doc.querySelector("#tabStory") as HTMLElement).hidden).toBe(true);
    expect((doc.querySelector("#tabReverse") as HTMLElement).hidden).toBe(true);
    expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("true");
    expect((doc.querySelector("#loading") as HTMLElement).hidden).toBe(false);

    await vi.advanceTimersByTimeAsync(8_000);
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    expect(traversalSignal?.aborted).toBe(true);
    expect((doc.querySelector("#loading") as HTMLElement).hidden).toBe(true);
    expect(doc.querySelector("#panelBrief")?.textContent).toContain("No claims recorded");
    expect(doc.querySelector("#traversalPath")?.textContent).toContain("unavailable for this scope");
  });

  it("ignores an older scope response that settles after a newer navigation", async () => {
    let resolveOldBrief!: (response: Response) => void;
    const oldBrief = new Promise<Response>((resolve) => { resolveOldBrief = resolve; });
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      const scope = url.searchParams.get("scope") ?? "";
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/brief" && scope === "bundle:older") return oldBrief;
      if (url.pathname === "/api/system/traversal") {
        return jsonResponse({ requirement: scope, tasks: [], design: [], files: [`${scope}.ts`] });
      }
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "bundle", ref: scope }, claims: [], rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());
    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;

    input.value = "bundle:older";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    input.value = "bundle:newer";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:newer"));
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));

    resolveOldBrief(await jsonResponse({
      scope: { kind: "bundle", ref: "bundle:older" }, claims: [], degraded: false, degraded_reasons: [],
    }));
    await Promise.resolve();
    await Promise.resolve();

    expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:newer");
    expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(false);
    expect(doc.querySelector("#traversalPath")?.textContent).toContain("bundle:newer.ts");
  });

  it("does not let a late older failure return a valid newer scope to landing", async () => {
    let rejectOldBrief!: (error: Error) => void;
    const oldBrief = new Promise<Response>((_resolve, reject) => { rejectOldBrief = reject; });
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      const scope = url.searchParams.get("scope") ?? "";
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/brief" && scope === "bundle:older") return oldBrief;
      if (url.pathname === "/api/system/traversal") {
        return jsonResponse({ requirement: scope, tasks: [], design: [], files: [] });
      }
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "bundle", ref: scope }, claims: [], rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());
    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "bundle:older";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    input.value = "bundle:newer";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));

    rejectOldBrief(new Error("older scope failed late"));
    await Promise.resolve();
    await Promise.resolve();

    expect((doc.querySelector("#landingPanel") as HTMLElement).hidden).toBe(true);
    expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(false);
    expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:newer");
    expect(doc.querySelector("#banner")?.textContent).not.toContain("older scope failed late");
  });

  it("restores scopes and tabs with Back and Forward without duplicating history", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      const scope = url.searchParams.get("scope") ?? "";
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/traversal") {
        return jsonResponse({ requirement: scope, tasks: [], design: [], files: [] });
      }
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "bundle", ref: scope }, claims: [], rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());
    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "bundle:first";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    doc.querySelector<HTMLElement>("#tabMatrix")!.click();
    expect(dom.window.location.hash).toBe("#matrix");

    input.value = "bundle:second";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:second"));
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    expect(dom.window.history.length).toBe(3);

    dom.window.history.back();
    await vi.waitFor(() => expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:first"));
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    expect(doc.querySelector("#tabMatrix")?.getAttribute("aria-selected")).toBe("true");
    expect(dom.window.history.length).toBe(3);

    dom.window.history.forward();
    await vi.waitFor(
      () => expect(doc.querySelector("#scopeRef")?.textContent).toBe("bundle:second"),
      { timeout: 2_000 },
    );
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    expect(doc.querySelector("#tabBrief")?.getAttribute("aria-selected")).toBe("true");
    expect(dom.window.history.length).toBe(3);
  });

  it("restores the landing when Back removes the scope without adding history", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      const scope = url.searchParams.get("scope") ?? "";
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/traversal") {
        return jsonResponse({ requirement: scope, tasks: [], design: [], files: [] });
      }
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        return jsonResponse({
          scope: { kind: "bundle", ref: scope }, claims: [], rows: [], events: [], sections: [],
          degraded: false, degraded_reasons: [],
        });
      }
      return Promise.reject(new Error(`unmocked fetch: ${url.pathname}`));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());
    (doc.querySelector(".feature-row") as HTMLElement).click();
    await vi.waitFor(() => expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false"));
    expect(dom.window.history.length).toBe(2);

    dom.window.history.back();
    await vi.waitFor(() => expect((doc.querySelector("#landingPanel") as HTMLElement).hidden).toBe(false));
    expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(true);
    expect(dom.window.location.search).toBe("");
    expect(dom.window.history.length).toBe(2);
  });

  it("keeps a truthful close control visible while the mobile scope sheet is open", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      return scopeResponse(url.pathname);
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());
    (doc.querySelector(".feature-row") as HTMLElement).click();
    await vi.waitFor(() => expect(doc.body.classList.contains("focus")).toBe(true));

    const toggle = doc.querySelector("#scopeToggle") as HTMLButtonElement;
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toBe("Browse scopes");
    toggle.click();
    expect(doc.body.classList.contains("focus")).toBe(true);
    expect(doc.body.classList.contains("picker-open")).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(toggle.textContent).toBe("Close scopes");
    toggle.click();
    expect(doc.body.classList.contains("picker-open")).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toBe("Browse scopes");
  });

  it("keeps the landing available and retries a failed health scan", async () => {
    let healthAttempts = 0;
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") {
        healthAttempts += 1;
        return healthAttempts === 1 ? Promise.reject(new Error("health unavailable")) : jsonResponse(HEALTH);
      }
      return scopeResponse(url.pathname);
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;

    await vi.waitFor(() => expect(doc.querySelector("#healthStatus")?.textContent).toContain("Project evidence is unavailable"));
    const retry = doc.querySelector("#retryHealth") as HTMLButtonElement;
    expect(retry.hidden).toBe(false);
    expect(doc.querySelector("#landingPanel")?.hasAttribute("hidden")).toBe(false);

    retry.click();
    await vi.waitFor(() => expect(doc.querySelector("#healthStatus")?.hasAttribute("hidden")).toBe(true));
    expect(retry.hidden).toBe(true);
    expect(healthAttempts).toBe(2);
  });

  it("routes an exact ref through the scope API without fetching a bare ref URL", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn((input: string | URL) => {
      calls.push(String(input));
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (["/api/system/brief", "/api/system/matrix", "/api/system/timeline", "/api/system/guide"].includes(url.pathname)) {
        const scope = { kind: "sr", ref: "sr:SR-137" };
        return jsonResponse({ scope, claims: [], rows: [], events: [], sections: [], degraded: false, degraded_reasons: [] });
      }
      if (String(input) === "sr:SR-137") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-137" } });
      return Promise.reject(new Error(`unmocked fetch: ${String(input)}`));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelectorAll(".health-metric")).toHaveLength(5));

    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "SR-137";
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(calls).toContain("/api/system/brief?scope=sr%3ASR-137"));
    expect(calls).not.toContain("sr:SR-137");
  });

  it("returns to the browse state when a scope request rejects", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      return Promise.reject(new Error("scope transport failed"));
    });
    const dom = loadDom(fetchMock);
    const doc = dom.window.document;
    await vi.waitFor(() => expect(doc.querySelector(".feature-row")).not.toBeNull());

    (doc.querySelector(".feature-row") as HTMLElement).click();
    await vi.waitFor(() => expect(doc.querySelector("#banner")?.textContent).toContain("could not resolve scope"));
    expect((doc.querySelector("#landingPanel") as HTMLElement).hidden).toBe(false);
    expect((doc.querySelector("#scopeWorkspace") as HTMLElement).hidden).toBe(true);
    expect(doc.querySelector("#content")?.getAttribute("aria-busy")).toBe("false");
  });
});
