import { describe, expect, test } from "vitest";
import { TranscriptViewer } from "../src/mission-control-transcript.js";

function manyLines(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `line ${i + 1}`);
}

describe("TranscriptViewer", () => {
  test("renders a windowed slice sized to the terminal's row count, plus a footer", () => {
    const view = new TranscriptViewer(manyLines(50), { terminal: { rows: 10 } });
    const lines = view.render(80);
    expect(lines.length).toBe(9); // 10 rows - 2 reserved -> 8 content + 1 footer
    expect(lines[0]).toBe("line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("appendLines grows the content and End follows it (tail -f style)", () => {
    const view = new TranscriptViewer(manyLines(20), { terminal: { rows: 10 } });
    view.handleInput("\x1b[F"); // End -- jump to bottom
    view.appendLines(["line 21", "line 22"]);
    const lines = view.render(80);
    expect(lines[lines.length - 2]).toBe("line 22");
  });

  // ScrollableMarkdown (src/scrollable-markdown.ts) starts at scrollOffset 0
  // (the top), not "following the bottom" -- there is no default-follow
  // behavior to inherit. So to exercise "user scrolled away from the bottom,
  // appendLines should not force-follow", this test first jumps to the
  // bottom via End (matching the "tail -f" test above), then scrolls away
  // with Up, before appending.
  test("Down/Up scroll manually; appendLines does not force-follow if the user scrolled away from the bottom", () => {
    const view = new TranscriptViewer(manyLines(20), { terminal: { rows: 10 } });
    view.handleInput("\x1b[F"); // End -- jump to bottom, start following
    view.render(80); // settle scrollOffset/followingBottom at the bottom
    view.handleInput("\x1b[A"); // Up -- scroll away from the bottom
    view.appendLines(["line 21"]);
    const lines = view.render(80);
    // viewport height = 10 - 2 = 8; bottom offset for 20 lines is 12; Up
    // moves to 11, i.e. showing "line 12" first -- NOT jumping to follow
    // the newly appended "line 21".
    expect(lines[0]).toBe("line 12");
    expect(lines[lines.length - 1]).toContain("of 21");
  });

  test("shows a 'not started yet' placeholder for empty content", () => {
    const view = new TranscriptViewer([], { terminal: { rows: 10 } });
    expect(view.render(80).join("\n")).toContain("not started yet");
  });
});
