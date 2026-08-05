import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, test } from "vitest";
import { ensureDocsServer, stopDocsServer } from "../src/docs-server.js";

// No child_process mock here on purpose: this exercises the real
// `uv run python -m factory.trace graph --json` against this repo, which is the
// only thing that proves the TypeScript and Python halves actually agree.
// Mirrors the review-diff.integration.test.ts convention.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

afterAll(() => {
  stopDocsServer();
});

describe("docs server against the real trace CLI", () => {
  test("serves a graph whose shape matches what the page consumes", async () => {
    const server = await ensureDocsServer(REPO_ROOT);
    const res = await fetch(`${server.url}/api/graph`);
    expect(res.status).toBe(200);
    const graph = await res.json();

    expect(graph.nodes.length).toBeGreaterThan(50);
    expect(graph.health.classes.map((c: { name: string }) => c.name)).toContain("task->plan");
    // This repo has tasks that declare no satisfies, so gaps must be non-empty --
    // an empty list would mean the two halves disagree about the schema.
    expect(graph.gaps.length).toBeGreaterThan(0);
    for (const gap of graph.gaps) {
      expect(["pending", "exempt", "deferred"]).toContain(gap.disposition);
    }
  }, 120_000);

  test("lays out the real graph and renders a real document", async () => {
    const server = await ensureDocsServer(REPO_ROOT);

    const layout = await (await fetch(`${server.url}/api/layout`)).json();
    expect(layout.nodes.length).toBeGreaterThan(50);
    expect(layout.width).toBeGreaterThan(0);

    // Take the path from the graph rather than hardcoding one: that is exactly
    // what the page does, so it also proves Python's node.path values are
    // servable by the TypeScript side.
    const graph = await (await fetch(`${server.url}/api/graph`)).json();
    const plan = graph.nodes.find((n: { kind: string }) => n.kind === "plan");
    expect(plan).toBeDefined();

    const res = await fetch(`${server.url}/api/doc?path=${encodeURIComponent(plan.path)}`);
    expect(res.status).toBe(200);
    const doc = await res.json();
    expect(typeof doc.html).toBe("string");
    expect(doc.html.length).toBeGreaterThan(0);
    expect(Array.isArray(doc.toc)).toBe(true);
  }, 120_000);

  test("refuses to serve a path outside the repository", async () => {
    const server = await ensureDocsServer(REPO_ROOT);
    const res = await fetch(`${server.url}/api/doc?path=../../etc/passwd`);
    expect(res.status).toBe(403);
  }, 120_000);
});
