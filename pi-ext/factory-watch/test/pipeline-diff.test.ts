import { describe, expect, test } from "vitest";
import { diffBlocked, snapshotStates } from "../src/pipeline-diff.js";
import { loadNodeRegistry } from "../src/node-registry.js";
import type { StatusRecord } from "../src/status-format.js";

const registry = loadNodeRegistry();

function record(pipeline: Array<{ node: string; node_state: string }>): StatusRecord {
  return {
    session_id: "s1",
    task_id: "T-029",
    current_node: "dev",
    current_state: "running",
    pipeline: pipeline.map((e) => ({
      node: e.node,
      node_state: e.node_state,
      attempt: 1,
      max_attempts: 1,
      snippet: "",
      outcome: null,
      handoff: null,
      updated_at: "t",
    })),
    started_at: "t",
    updated_at: "t",
  };
}

describe("diffBlocked", () => {
  test("reports a grill that newly enters blocked", () => {
    const prev = record([{ node: "context-gather", node_state: "pass" }]);
    const next = record([
      { node: "context-gather", node_state: "pass" },
      { node: "grill", node_state: "blocked" },
    ]);
    expect(diffBlocked(snapshotStates(prev), snapshotStates(next), registry)).toEqual([
      { node: "grill", state: "blocked" },
    ]);
  });

  test("is nag-free: a node already blocked in prev is not re-reported", () => {
    const prev = record([
      { node: "grill", node_state: "blocked" },
    ]);
    const next = record([
      { node: "grill", node_state: "blocked" },
    ]);
    expect(diffBlocked(snapshotStates(prev), snapshotStates(next), registry)).toEqual([]);
  });

  test("first read from an empty prev offers a blocked grill (already-blocked at open)", () => {
    const next = record([{ node: "grill", node_state: "blocked" }]);
    expect(diffBlocked([], snapshotStates(next), registry)).toEqual([
      { node: "grill", state: "blocked" },
    ]);
  });

  test("ignores non-interactive nodes even when blocked", () => {
    const next = record([{ node: "dev", node_state: "running" }]);
    expect(diffBlocked([], snapshotStates(next), registry)).toEqual([]);
  });

  test("reports a freshly-blocked human-review too", () => {
    const prev = record([{ node: "review", node_state: "pass" }]);
    const next = record([
      { node: "review", node_state: "pass" },
      { node: "human-review", node_state: "blocked" },
    ]);
    expect(diffBlocked(snapshotStates(prev), snapshotStates(next), registry)).toEqual([
      { node: "human-review", state: "blocked" },
    ]);
  });

  test("ignores nodes absent from next", () => {
    const prev = record([{ node: "grill", node_state: "blocked" }]);
    const next = record([{ node: "dev", node_state: "running" }]);
    expect(diffBlocked(snapshotStates(prev), snapshotStates(next), registry)).toEqual([]);
  });
});
