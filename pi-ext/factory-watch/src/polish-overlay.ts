import type { Component } from "@earendil-works/pi-tui";
import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";
import type { PolishCommand, PolishState } from "./polish-model.js";

export interface PanelMode {
  typing: boolean;
  cursor: number;
  focus?: "gate1" | "gate2";
}

export function renderPolishPanel(state: PolishState, mode: PanelMode): string[] {
  const lines: string[] = [];
  lines.push(`Polish - ${state.usecase}    queue: ${state.queue_size}`);
  lines.push(`app: ${state.entrypoints.join("  ")}`);
  lines.push("");

  const g1active = mode.focus === "gate1";
  lines.push(`${g1active ? "> " : "  "}Gate 1 - review before fixing  [a]ccept [e]dit [d]iscard`);
  if (state.gate1.length === 0) lines.push("    (none)");
  state.gate1.forEach((g, i) => {
    const cur = g1active && i === mode.cursor ? "* " : "  ";
    lines.push(`  ${cur}${g.description}${g.sr ? `  (${g.sr})` : ""}`);
  });
  lines.push("");

  const g2active = mode.focus === "gate2";
  lines.push(`${g2active ? "> " : "  "}Gate 2 - landed changes  [t]ick done  [c]omment wrong`);
  if (state.gate2.length === 0) lines.push("    (none)");
  state.gate2.forEach((r, i) => {
    const mark =
      r.verdict === "accepted"
        ? "v"
        : r.verdict === "wrong"
          ? "x"
          : r.status === "failed"
            ? "!"
            : " ";
    const cur = g2active && i === mode.cursor ? "* " : "  ";
    lines.push(`  ${cur}${mark} ${r.task_id}  ${r.description}${r.sr ? `  (${r.sr})` : ""}`);
  });
  lines.push("");
  lines.push("up/down move  Tab switch gate  [f] feedback  [q] quit");
  return lines;
}

export function keyToCommand(
  key: string,
  state: PolishState,
  mode: PanelMode,
): PolishCommand | null {
  const row1 = state.gate1[mode.cursor];
  const row2 = state.gate2[mode.cursor];
  if (mode.focus === "gate1" && row1) {
    if (key === "a") return { kind: "accept", args: { gid: row1.gid } };
    if (key === "d") return { kind: "discard", args: { gid: row1.gid } };
  }
  if (mode.focus === "gate2" && row2) {
    if (key === "t") return { kind: "tick", args: { gid: row2.gid } };
  }
  return null;
}

export type PolishAction =
  | { type: "feedback" }
  | { type: "edit"; gid: string; description: string }
  | { type: "comment"; gid: string }
  | { type: "quit" };

interface TuiLike {
  terminal: { rows: number };
}

const EMPTY_STATE: PolishState = {
  usecase: "",
  entrypoints: [],
  queue_size: 0,
  gate1_ids: [],
  gate1: [],
  gate2: [],
};

export class PolishOverlay implements Component {
  private state: PolishState = EMPTY_STATE;
  private cursor = 0;
  private focus: "gate1" | "gate2" = "gate1";

  // Explicit field assignment (not TS parameter properties) -- same reason as
  // ReviewOverlay: this module is also reachable via a plain `node <file>.ts`
  // import chain.
  private readonly tui: TuiLike;
  private readonly write: (cmd: PolishCommand) => void;
  private readonly done: (a: PolishAction) => void;

  constructor(tui: TuiLike, write: (cmd: PolishCommand) => void, done: (a: PolishAction) => void) {
    this.tui = tui;
    this.write = write;
    this.done = done;
  }

  update(state: PolishState): void {
    this.state = state;
    const rows = this.rowsFor(this.focus);
    if (this.cursor >= rows) this.cursor = Math.max(0, rows - 1);
  }

  invalidate(): void {}

  private rowsFor(focus: "gate1" | "gate2"): number {
    return focus === "gate1" ? this.state.gate1.length : this.state.gate2.length;
  }

  handleInput(data: string): void {
    if (matchesKey(data, Key.escape) || data === "q") {
      this.done({ type: "quit" });
      return;
    }
    if (data === "\t") {
      this.focus = this.focus === "gate1" ? "gate2" : "gate1";
      this.cursor = 0;
      return;
    }
    if (matchesKey(data, Key.down) || data === "j") {
      this.cursor = Math.min(this.cursor + 1, Math.max(0, this.rowsFor(this.focus) - 1));
      return;
    }
    if (matchesKey(data, Key.up) || data === "k") {
      this.cursor = Math.max(this.cursor - 1, 0);
      return;
    }
    if (data === "f") {
      this.done({ type: "feedback" });
      return;
    }
    if (data === "e" && this.focus === "gate1") {
      const row = this.state.gate1[this.cursor];
      if (row) this.done({ type: "edit", gid: row.gid, description: row.description });
      return;
    }
    if (data === "c" && this.focus === "gate2") {
      const row = this.state.gate2[this.cursor];
      if (row) this.done({ type: "comment", gid: row.gid });
      return;
    }
    const cmd = keyToCommand(data, this.state, {
      typing: false,
      cursor: this.cursor,
      focus: this.focus,
    });
    // accept / discard / tick -- stays open; the poll reflects the new state
    if (cmd) this.write(cmd);
  }

  render(width: number): string[] {
    const lines = renderPolishPanel(this.state, {
      typing: false,
      cursor: this.cursor,
      focus: this.focus,
    });
    // pi-tui hard-throws on any over-width line -- truncate, exactly like ReviewOverlay.render.
    return lines.map((l) => truncateToWidth(l, width));
  }
}
