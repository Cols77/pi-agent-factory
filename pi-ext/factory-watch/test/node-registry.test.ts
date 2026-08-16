import { describe, expect, test } from "vitest";
import {
  loadNodeRegistry,
  stageOrder,
  labelForNode,
  isAgentNode,
  isInteractiveNode,
} from "../src/node-registry.js";

describe("loadNodeRegistry", () => {
  test("loads a registry whose order covers the full pipeline including grill", () => {
    const reg = loadNodeRegistry();
    expect(Array.isArray(reg.order)).toBe(true);
    expect(reg.order).toEqual([
      "context-gather",
      "grill",
      "dev",
      "validation",
      "review",
      "human-review",
      "session-review",
    ]);
    expect(reg.nodes.length).toBeGreaterThanOrEqual(7);
  });

  test("every id in order has a matching node entry", () => {
    const reg = loadNodeRegistry();
    const ids = new Set(reg.nodes.map((n) => n.id));
    for (const id of reg.order) {
      expect(ids.has(id)).toBe(true);
    }
  });

  test("grill and human-review are marked interactive", () => {
    const reg = loadNodeRegistry();
    const grill = reg.nodes.find((n) => n.id === "grill");
    const hr = reg.nodes.find((n) => n.id === "human-review");
    expect(grill?.interactive).toBe(true);
    expect(hr?.interactive).toBe(true);
  });
});

describe("registry helpers", () => {
  test("stageOrder returns the registry order", () => {
    expect(stageOrder()).toContain("grill");
    expect(stageOrder()[1]).toBe("grill");
  });

  test("labelForNode returns registry labels", () => {
    expect(labelForNode("context-gather")).toBe("context-gatherer");
    expect(labelForNode("grill")).toBe("grill");
    expect(labelForNode("session-review")).toBe("session-reviewer");
    expect(labelForNode("unknown-node")).toBe("unknown-node");
  });

  test("isAgentNode / isInteractiveNode reflect the registry", () => {
    expect(isAgentNode("dev")).toBe(true);
    expect(isAgentNode("grill")).toBe(false);
    expect(isInteractiveNode("grill")).toBe(true);
    expect(isInteractiveNode("dev")).toBe(false);
    expect(isInteractiveNode("missing")).toBe(false);
  });
});
