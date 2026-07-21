import { describe, expect, test, vi } from "vitest";
import type { MarkdownTheme } from "@earendil-works/pi-tui";
import { ScrollableMarkdown } from "../src/scrollable-markdown.js";

const IDENTITY_THEME: MarkdownTheme = {
  heading: (t) => t,
  link: (t) => t,
  linkUrl: (t) => t,
  code: (t) => t,
  codeBlock: (t) => t,
  codeBlockBorder: (t) => t,
  quote: (t) => t,
  quoteBorder: (t) => t,
  hr: (t) => t,
  listBullet: (t) => t,
  bold: (t) => t,
  italic: (t) => t,
  strikethrough: (t) => t,
  underline: (t) => t,
};

function fakeTui(rows: number): { terminal: { rows: number } } {
  return { terminal: { rows } };
}

function manyLinesText(n: number): string {
  return Array.from({ length: n }, (_, i) => `line ${i + 1}`).join("\n");
}

describe("ScrollableMarkdown", () => {
  test("renders a windowed slice sized to the terminal's row count, plus a footer", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    const lines = view.render(80);
    // 10 rows - 2 reserved for the footer = 8 content lines + 1 footer line = 9
    expect(lines.length).toBe(9);
    expect(lines[0]).toBe("line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("Down arrow scrolls forward, Up arrow scrolls back", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[B"); // Down
    const after = view.render(80);
    expect(after[0]).toBe("line 2");
    view.handleInput("\x1b[A"); // Up
    const back = view.render(80);
    expect(back[0]).toBe("line 1");
  });

  test("cannot scroll above the top", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[A"); // Up, already at top
    const lines = view.render(80);
    expect(lines[0]).toBe("line 1");
  });

  test("End jumps to the bottom, clamped so the last page is full", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[F"); // End
    const lines = view.render(80);
    expect(lines[lines.length - 2]).toBe("line 50");
  });

  test("q closes the view", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.handleInput("q");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("Escape closes the view", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.handleInput("\x1b");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
