import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadSystemBriefing, loadSystemGuide, loadSystemScopes } from "../src/system-cli.js";

// No child_process mock: this drives the real `uv run python -m factory.system`
// against this repo, which is the only thing that proves the shim and the CLI
// agree on the real output shape -- including the real error shape on a bad
// scope ref. Mirrors trace-tools.integration.test.ts and
// docs-server.integration.test.ts.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

describe("system-cli against the real CLI", () => {
  test("scope --json returns the legitimate empty state for this repo", () => {
    // This repo currently has no bundles directory and no requirements
    // directory, so an empty scope list is correct, not an error.
    const result = loadSystemScopes(REPO_ROOT);
    expect(result).toEqual({ ok: true, value: { scopes: [], errors: [] } });
  }, 60_000);

  test("brief --scope on a non-scope kind surfaces the real structured error", () => {
    const result = loadSystemBriefing(REPO_ROOT, "task:T-001");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("invalid scope ref");
      expect(result.error).toContain("task:T-001");
      expect(result.error).toContain("ScopeKindError");
    }
  }, 60_000);

  test("brief --scope on a well-formed but nonexistent sr surfaces ScopeNotFoundError", () => {
    const result = loadSystemBriefing(REPO_ROOT, "sr:SR-DOES-NOT-EXIST");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("sr not found");
      expect(result.error).toContain("ScopeNotFoundError");
    }
  }, 60_000);

  test("guide --scope on a well-formed but nonexistent sr surfaces ScopeNotFoundError", () => {
    const result = loadSystemGuide(REPO_ROOT, "sr:SR-DOES-NOT-EXIST");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("sr not found");
      expect(result.error).toContain("ScopeNotFoundError");
    }
  }, 60_000);
});
