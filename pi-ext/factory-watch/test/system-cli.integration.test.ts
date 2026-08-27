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
  test("scope --json returns the current feature and bundle state for this repo", () => {
    const result = loadSystemScopes(REPO_ROOT);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.errors).toEqual([]);
      expect(result.value.scopes).toEqual(
        expect.arrayContaining([
          { kind: "bundle", ref: "bundle:FEAT-017" },
          { kind: "feat", ref: "feat:FEAT-017" },
        ]),
      );
    }
  }, 60_000);

  // "task:" is itself a scope kind `factory.system` recognizes (increment B
  // added it for `story`, commit 7c771a8/7c74b1c) -- but `brief` only ever
  // resolves bundle:/sr:, so the real CLI now reports this as "unsupported
  // scope kind" (query_brief's own guard), not the parser-level "invalid
  // scope ref" a wholly-unrecognized prefix would raise.
  test("brief --scope on a scope kind that brief does not support surfaces the real structured error", () => {
    const result = loadSystemBriefing(REPO_ROOT, "task:T-001");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("unsupported scope kind");
      expect(result.error).toContain("task");
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
