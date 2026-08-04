import { describe, it, expect } from "vitest";
import { visibleWidth } from "@earendil-works/pi-tui";
import { renderPolishPanel, keyToCommand, PolishOverlay } from "../src/polish-overlay.js";

const state = {
  usecase: "sign-in",
  entrypoints: ["http://localhost:3000"],
  queue_size: 2,
  gate1_ids: ["g1-1"],
  gate1: [{ gid: "g1-1", description: "sign-in broken", sr: "SR-010" }],
  gate2: [
    {
      gid: "g2-1",
      task_id: "T-007",
      description: "fix login",
      sr: "SR-010",
      status: "landed" as const,
      verdict: "pending" as const,
    },
  ],
};

describe("renderPolishPanel", () => {
  it("shows usecase, queue depth, and both gates", () => {
    const lines = renderPolishPanel(state, { typing: false, cursor: 0 }).join("\n");
    expect(lines).toContain("sign-in");
    expect(lines).toContain("queue: 2");
    expect(lines).toContain("sign-in broken"); // gate 1
    expect(lines).toContain("T-007"); // gate 2 landed change
  });

  it("renders (none) for empty gates", () => {
    const empty = { ...state, gate1: [], gate2: [] };
    const lines = renderPolishPanel(empty, { typing: false, cursor: 0 }).join("\n");
    expect(lines).toContain("(none)");
  });
});

describe("keyToCommand", () => {
  it("maps 'a' on a Gate-1 row to an accept command", () => {
    const cmd = keyToCommand("a", state, { typing: false, cursor: 0, focus: "gate1" });
    expect(cmd).toEqual({ kind: "accept", args: { gid: "g1-1" } });
  });

  it("maps 't' on a Gate-2 row to a tick command", () => {
    const cmd = keyToCommand("t", state, { typing: false, cursor: 0, focus: "gate2" });
    expect(cmd).toEqual({ kind: "tick", args: { gid: "g2-1" } });
  });

  it("returns null for an unmapped key", () => {
    expect(keyToCommand("z", state, { typing: false, cursor: 0, focus: "gate1" })).toBeNull();
  });

  it("returns null when the cursor points past the end of a gate", () => {
    expect(keyToCommand("a", state, { typing: false, cursor: 9, focus: "gate1" })).toBeNull();
  });

  it("does not apply a Gate-2 key while Gate 1 is focused", () => {
    expect(keyToCommand("t", state, { typing: false, cursor: 0, focus: "gate1" })).toBeNull();
  });
});

describe("PolishOverlay", () => {
  const fakeTui = { terminal: { rows: 24 } };

  it("writes an accept command when 'a' is pressed on a Gate-1 row", () => {
    const written: unknown[] = [];
    const o = new PolishOverlay(
      fakeTui,
      (c) => written.push(c),
      () => {},
    );
    o.update(state); // focus defaults to gate1, cursor 0
    o.handleInput("a");
    expect(written).toEqual([{ kind: "accept", args: { gid: "g1-1" } }]);
  });

  it("returns a feedback action via done() when 'f' is pressed", () => {
    let action: unknown = null;
    const o = new PolishOverlay(
      fakeTui,
      () => {},
      (a) => {
        action = a;
      },
    );
    o.update(state);
    o.handleInput("f");
    expect(action).toEqual({ type: "feedback" });
  });

  it("returns quit on 'q'", () => {
    let action: unknown = null;
    const o = new PolishOverlay(
      fakeTui,
      () => {},
      (a) => {
        action = a;
      },
    );
    o.update(state);
    o.handleInput("q");
    expect(action).toEqual({ type: "quit" });
  });

  it("Tab switches gate focus so Gate-2 keys apply", () => {
    const written: unknown[] = [];
    const o = new PolishOverlay(
      fakeTui,
      (c) => written.push(c),
      () => {},
    );
    o.update(state);
    o.handleInput("\t");
    o.handleInput("t");
    expect(written).toEqual([{ kind: "tick", args: { gid: "g2-1" } }]);
  });

  it("clamps the cursor when an update shrinks the focused gate", () => {
    const written: unknown[] = [];
    const twoRows = {
      ...state,
      gate1: [
        { gid: "g1-1", description: "a", sr: null },
        { gid: "g1-2", description: "b", sr: null },
      ],
    };
    const o = new PolishOverlay(
      fakeTui,
      (c) => written.push(c),
      () => {},
    );
    o.update(twoRows);
    o.handleInput("j"); // cursor -> 1
    o.update(state); // gate1 shrinks back to one row
    o.handleInput("a");
    expect(written).toEqual([{ kind: "accept", args: { gid: "g1-1" } }]);
  });

  it("never emits a line wider than the viewport", () => {
    const o = new PolishOverlay(
      fakeTui,
      () => {},
      () => {},
    );
    o.update(state);
    // pi-tui throws on over-width lines and measures *visible* width: the
    // truncated string carries ANSI resets, so .length overstates it.
    for (const line of o.render(20)) {
      expect(visibleWidth(line)).toBeLessThanOrEqual(20);
    }
  });
});
