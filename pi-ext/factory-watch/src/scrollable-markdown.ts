import { Key, Markdown, matchesKey } from "@earendil-works/pi-tui";
import type { Component, MarkdownTheme } from "@earendil-works/pi-tui";

/** Minimal structural subset of pi-tui's TUI that this component actually needs. */
export interface TuiLike {
  terminal: { rows: number };
}

export class ScrollableMarkdown implements Component {
  private readonly markdown: Markdown;
  private scrollOffset = 0;
  private cachedWidth: number | undefined;
  private cachedLines: string[] = [];

  constructor(
    text: string,
    theme: MarkdownTheme,
    private readonly tui: TuiLike,
    private readonly onClose: () => void,
  ) {
    this.markdown = new Markdown(text, 0, 0, theme);
  }

  invalidate(): void {
    this.cachedWidth = undefined;
    this.markdown.invalidate();
  }

  handleInput(data: string): void {
    const viewportHeight = this.getViewportHeight();
    if (matchesKey(data, Key.down)) {
      this.scrollOffset += 1;
    } else if (matchesKey(data, Key.up)) {
      this.scrollOffset -= 1;
    } else if (matchesKey(data, Key.pageDown)) {
      this.scrollOffset += viewportHeight;
    } else if (matchesKey(data, Key.pageUp)) {
      this.scrollOffset -= viewportHeight;
    } else if (matchesKey(data, Key.home)) {
      this.scrollOffset = 0;
    } else if (matchesKey(data, Key.end)) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
    } else if (matchesKey(data, Key.escape) || data === "q") {
      this.onClose();
    }
  }

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  render(width: number): string[] {
    if (this.cachedWidth !== width) {
      this.cachedWidth = width;
      // pi-tui's Markdown unconditionally right-pads every rendered line to the
      // full requested width (see Markdown.render's padding step). Strip that
      // trailing padding so windowed lines reflect only actual content.
      this.cachedLines = this.markdown.render(width).map((line) => line.replace(/\s+$/, ""));
    }
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, this.cachedLines.length - viewportHeight);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);

    const visible = this.cachedLines.slice(this.scrollOffset, this.scrollOffset + viewportHeight);
    const lastShown = Math.min(this.scrollOffset + viewportHeight, this.cachedLines.length);
    const footer = `-- line ${this.scrollOffset + 1}-${lastShown} of ${this.cachedLines.length} (arrows/PgUp/PgDn/Home/End, q to close) --`;
    return [...visible, footer];
  }
}
