import { afterEach, describe, expect, test } from "vitest";
import scopeGuard from "../src/index.js";
import type { PiApi, ToolCallHandler, ToolCallEvent, ExtCtx } from "../src/pi-types.js";

function capture(): { handler: ToolCallHandler; pi: PiApi } {
  let handler: ToolCallHandler | undefined;
  const pi: PiApi = { on: (_e, h) => (handler = h) };
  scopeGuard(pi);
  if (!handler) throw new Error("no handler registered");
  return { handler, pi };
}

const ctx: ExtCtx = { cwd: "C:/repo", hasUI: false, mode: "print" };
const ev = (toolName: string, input: ToolCallEvent["input"]): ToolCallEvent => ({ toolName, input });

afterEach(() => {
  delete process.env.PI_SCOPE_ALLOW;
  delete process.env.PI_SCOPE_BASH;
});

describe("scope-guard handler", () => {
  test("blocks write outside PI_SCOPE_ALLOW", async () => {
    process.env.PI_SCOPE_ALLOW = "src/**";
    const { handler } = capture();
    const r = await handler(ev("write", { path: "kb/secret.md" }), ctx);
    expect(r?.block).toBe(true);
  });

  test("allows write inside PI_SCOPE_ALLOW", async () => {
    process.env.PI_SCOPE_ALLOW = "src/**,tests/**";
    const { handler } = capture();
    expect(await handler(ev("write", { path: "tests/x.test.py" }), ctx)).toBeUndefined();
  });

  test("no allow env means all writes blocked (read-only role)", async () => {
    const { handler } = capture();
    expect((await handler(ev("edit", { path: "src/x.py" }), ctx))?.block).toBe(true);
  });

  test("bash blocked by default, allowed when PI_SCOPE_BASH=allow", async () => {
    const { handler } = capture();
    expect((await handler(ev("bash", { command: "ls" }), ctx))?.block).toBe(true);
    process.env.PI_SCOPE_BASH = "allow";
    expect(await handler(ev("bash", { command: "ls" }), ctx)).toBeUndefined();
  });
});
