// test/smoke.test.ts
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
