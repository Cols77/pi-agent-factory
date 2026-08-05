// test/smoke.test.ts
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";
import type { PiApi } from "../src/pi-types.js";

test("types import and a fake PiApi can register a command", () => {
  const registered: string[] = [];
  const pi: PiApi = {
    registerCommand: (name) => registered.push(name),
    registerTool: () => {},
    on: () => {},
  };
  pi.registerCommand("factory", { handler: async () => {} });
  expect(registered).toEqual(["factory"]);
});

// Vitest's own module resolution (esbuild-based) is far more permissive than
// plain `node <file>.ts` -- it happily accepts both TypeScript constructor
// parameter properties and ".js"-suffixed imports that actually point at
// sibling ".ts" files. Real `node <file>.ts` execution (exactly what
// terminal-window.ts's spawnTerminalWindow uses to launch standalone entry
// points) accepts neither: it throws ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX on
// parameter properties, and ERR_MODULE_NOT_FOUND on ".js" specifiers that
// don't exist on disk. Both bugs shipped and passed the full vitest suite for
// weeks because nothing exercised the real `node <file>.ts` path -- only
// vitest's import of these files. This test runs the file exactly the way
// spawnTerminalWindow does, omitting the required CLI arg so main() exits
// fast (after resolving every import) instead of mounting an interactive TUI
// that would hang the test.
//
// mission-control-dashboard.ts no longer has an equivalent test here: its
// standalone `main()` + CLI bootstrap were deleted when the dashboard moved
// in-session (it's now driven purely via `pi`'s ctx.ui.custom action loop in
// index.ts, never invoked via a bare `node <file>.ts`).
const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

test("mission-control-review.ts loads under real `node <file>.ts` execution (no args -> fast usage exit, not a module-load crash)", () => {
  const result = spawnSync("node", [join(SRC_DIR, "mission-control-review.ts")], {
    encoding: "utf-8",
    // 30s (was 10s): under full-suite parallel load, cold `node <file>.ts`
    // type-stripping + import-chain resolution can exceed 10s and SIGTERM the
    // child before it prints, producing a spurious empty-stderr failure. The
    // work itself is near-instant unloaded; this is headroom, not new behavior.
    timeout: 30_000,
  });
  expect(result.stderr).not.toMatch(/ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX|ERR_MODULE_NOT_FOUND/);
  expect(result.stderr).toContain("usage:");
  expect(result.status).toBe(1);
});
