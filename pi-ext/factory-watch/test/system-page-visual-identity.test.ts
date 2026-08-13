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

function loadDom(fetchMock: ReturnType<typeof vi.fn>): JSDOM {
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously",
    resources: "usable",
    url: "http://localhost/system",
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
