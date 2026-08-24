import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { buildCoherenceRouteCommand, loadCoherenceRoute } from "../src/coherence-router.js";
import type { RouteResult } from "../src/coherence-router.js";

const MATCHED: RouteResult = { route: { intent: "VERIFY_CLAIM", scope_ref: "sr:SR-001", score: 3 } };
const UNMATCHED: RouteResult = { route: null };

describe("buildCoherenceRouteCommand", () => {
  test("invokes the modern coherence module directly, with the text as a positional arg", () => {
    expect(buildCoherenceRouteCommand("verify sr:SR-001")).toEqual({
      bin: "uv",
      args: ["run", "python", "-m", "coherence", "route", "verify sr:SR-001", "--json"],
    });
  });
});

describe("loadCoherenceRoute", () => {
  test("parses a matched route, exposing intent/scope_ref/score unmodified", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(MATCHED), stderr: "" });
    const result = loadCoherenceRoute("/repo", "verify sr:SR-001");
    expect(result).toEqual({ ok: true, value: MATCHED });
  });

  test("parses a null route (no match/tie/below-threshold) without error", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(UNMATCHED), stderr: "" });
    const result = loadCoherenceRoute("/repo", "the weather is nice today");
    expect(result).toEqual({ ok: true, value: UNMATCHED });
  });

  test("invokes coherence route <text> --json in the given cwd", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(UNMATCHED), stderr: "" });
    loadCoherenceRoute("/repo", "some text");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "coherence", "route", "some text", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("surfaces a CLI failure as a structured error, not a thrown exception", () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "boom" });
    const result = loadCoherenceRoute("/repo", "some text");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("boom");
    }
  });
});
