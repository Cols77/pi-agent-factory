import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";

export interface TuiLike { terminal: { rows: number } }

export class SessionTranscriptView implements Component {
  private scrollOffset = 0;
  private readonly lines: string[];
  private readonly tui: TuiLike;
  private readonly onClose: () => void;
  private readonly onPopOut: () => void;

  constructor(lines: string[], tui: TuiLike, onClose: () => void, onPopOut: () => void) {
    this.lines = lines;
    this.tui = tui;
    this.onClose = onClose;
    this.onPopOut = onPopOut;
  }

  invalidate(): void {}

  private viewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  handleInput(data: string): void {
    const h = this.viewportHeight();
    if (matchesKey(data, Key.down)) this.scrollOffset += 1;
    else if (matchesKey(data, Key.up)) this.scrollOffset -= 1;
    else if (matchesKey(data, Key.pageDown)) this.scrollOffset += h;
    else if (matchesKey(data, Key.pageUp)) this.scrollOffset -= h;
    else if (matchesKey(data, Key.home)) this.scrollOffset = 0;
    else if (matchesKey(data, Key.end)) this.scrollOffset = Number.MAX_SAFE_INTEGER;
    else if (matchesKey(data, Key.escape) || data === "q") this.onClose();
    else if (data === "o") this.onPopOut();
  }

  render(width: number): string[] {
    const h = this.viewportHeight();
    const maxOffset = Math.max(0, this.lines.length - h);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);
    const visible = this.lines.slice(this.scrollOffset, this.scrollOffset + h);
    const last = Math.min(this.scrollOffset + h, this.lines.length);
    const footer = `${this.scrollOffset + 1}-${last}/${this.lines.length} -- o open in pi --session`;
    return [...visible, footer].map((line) => truncateToWidth(line, width));
  }
}
