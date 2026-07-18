import { describe, expect, test } from "vitest";
import { parseBashPolicy, decide } from "../src/policy.js";
import type { ToolCallEvent, ExtCtx } from "../src/pi-types.js";

const ctx: ExtCtx = { cwd: "C:/repo", hasUI: false, mode: "print" };
const ev = (toolName: string, input: ToolCallEvent["input"]): ToolCallEvent => ({ toolName, input });

describe("parseBashPolicy", () => {
  test("only 'allow' allows; else deny (fail-closed)", () => {
    expect(parseBashPolicy("allow")).toBe("allow");
    expect(parseBashPolicy("Allow")).toBe("deny");
    expect(parseBashPolicy(undefined)).toBe("deny");
  });
});

describe("decide", () => {
  test("allows in-scope write", () => {
    expect(decide(ev("write", { path: "src/x.py" }), ctx, ["src/**"], "deny")).toBeUndefined();
  });
  test("blocks out-of-scope write", () => {
    const r = decide(ev("edit", { path: "secrets/.env" }), ctx, ["src/**"], "deny");
    expect(r?.block).toBe(true);
  });
  test("blocks write with missing path (fail-closed)", () => {
    const r = decide(ev("write", {}), ctx, ["src/**"], "deny");
    expect(r?.block).toBe(true);
  });
  test("blocks bash when policy deny", () => {
    expect(decide(ev("bash", { command: "ls" }), ctx, [], "deny")?.block).toBe(true);
  });
  test("allows bash when policy allow", () => {
    expect(decide(ev("bash", { command: "pytest" }), ctx, [], "allow")).toBeUndefined();
  });
  test("ignores unrelated read tools", () => {
    expect(decide(ev("read", { path: "anything" }), ctx, [], "deny")).toBeUndefined();
  });
});
