// test/smoke.test.ts
import { expect, test } from "vitest";
import type { PiApi } from "../src/pi-types.js";

test("types import and a fake PiApi can register a handler", () => {
  const registered: string[] = [];
  const pi: PiApi = { on: (name) => registered.push(name) };
  pi.on("tool_call", () => undefined);
  expect(registered).toEqual(["tool_call"]);
});
