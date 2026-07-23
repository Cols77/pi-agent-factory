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
    on: () => {},
  };
  pi.registerCommand("factory", { handler: async () => {} });
  expect(registered).toEqual(["factory"]);
});

// Vitest's own module resolution (esbuild-based) is far more permissive than
// plain `node <file>.ts` -- it happily accepts both TypeScript constructor
// parameter properties and ".js"-suffixed imports that actually point at
// sibling ".ts" files. Real `node <file>.ts` execution (exactly what
// terminal-window.ts's spawnTerminalWindow uses to launch these two
// standalone entry points) accepts neither: it throws
// ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX on parameter properties, and
// ERR_MODULE_NOT_FOUND on ".js" specifiers that don't exist on disk. Both
// bugs shipped and passed the full vitest suite for weeks because nothing
// exercised the real `node <file>.ts` path -- only vitest's import of these
// files. These tests run the files exactly the way spawnTerminalWindow does,
// omitting the required CLI arg so main() exits fast (after resolving every
// import) instead of mounting an interactive TUI that would hang the test.
const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

test("mission-control-dashboard.ts loads under real `node <file>.ts` execution (no args -> fast usage exit, not a module-load crash)", () => {
  const result = spawnSync("node", [join(SRC_DIR, "mission-control-dashboard.ts")], {
    encoding: "utf-8",
    timeout: 10_000,
  });
  expect(result.stderr).not.toMatch(/ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX|ERR_MODULE_NOT_FOUND/);
  expect(result.stderr).toContain("usage:");
  expect(result.status).toBe(1);
});

test("mission-control-transcript.ts loads under real `node <file>.ts` execution (no args -> fast usage exit, not a module-load crash)", () => {
  const result = spawnSync("node", [join(SRC_DIR, "mission-control-transcript.ts")], {
    encoding: "utf-8",
    timeout: 10_000,
  });
  expect(result.stderr).not.toMatch(/ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX|ERR_MODULE_NOT_FOUND/);
  expect(result.stderr).toContain("usage:");
  expect(result.status).toBe(1);
});
