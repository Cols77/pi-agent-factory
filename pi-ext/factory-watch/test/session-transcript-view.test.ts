import { visibleWidth } from "@earendil-works/pi-tui";
import { describe, expect, test, vi } from "vitest";
import { SessionTranscriptView } from "../src/session-transcript-view.js";

const tui = { terminal: { rows: 10 } };

test("q closes, o pops out", () => {
  const onClose = vi.fn(), onPopOut = vi.fn();
  const v = new SessionTranscriptView(["a", "b"], tui, onClose, onPopOut);
  v.handleInput("q");
  expect(onClose).toHaveBeenCalledTimes(1);
  v.handleInput("o");
  expect(onPopOut).toHaveBeenCalledTimes(1);
});

test("render truncates lines to width and shows a footer", () => {
  const v = new SessionTranscriptView(["x".repeat(200)], tui, () => {}, () => {});
  const lines = v.render(40);
  for (const line of lines) expect(visibleWidth(line)).toBeLessThanOrEqual(40);
  expect(lines[lines.length - 1]).toContain("o open in pi --session");
});
