// Minimal structural subset of Pi's real ExtensionAPI/ExtensionContext that
// this extension actually uses. Pinned against the real
// @earendil-works/pi-coding-agent package's types by type-compat-check.ts
// so drift is caught at typecheck time, not discovered later.
//
// TUI/Component/OverlayOptions/KeybindingsManager (from @earendil-works/pi-tui)
// and Theme (from @earendil-works/pi-coding-agent) are imported directly
// rather than hand-duplicated -- they're exactly the real types
// ScrollableMarkdown and the /review-plans command interoperate with, so
// redeclaring minimal subsets of them would be pure risk with no benefit.

import type { Component, KeybindingsManager, OverlayOptions, TUI } from "@earendil-works/pi-tui";
import type { Theme } from "@earendil-works/pi-coding-agent";

export interface ModelInfo {
  provider: string;
  id: string;
}

export interface ReplacedSessionCtx {
  sendUserMessage(
    content: string,
    options?: { deliverAs?: "steer" | "followUp" },
  ): Promise<void>;
}

export interface UiApi {
  notify(message: string, type?: "info" | "warning" | "error"): void;
  setStatus(key: string, text: string | undefined): void;
  setWidget(key: string, content: string[] | undefined): void;
  select(title: string, options: string[]): Promise<string | undefined>;
  custom<T>(
    factory: (tui: TUI, theme: Theme, keybindings: KeybindingsManager, done: (result: T) => void) => Component,
    options?: { overlay?: boolean; overlayOptions?: OverlayOptions },
  ): Promise<T>;
}

export interface ExtCommandCtx {
  cwd: string;
  ui: UiApi;
  model: ModelInfo | undefined;
  newSession(options?: {
    withSession?: (ctx: ReplacedSessionCtx) => Promise<void>;
  }): Promise<{ cancelled: boolean }>;
}

export interface CommandDef {
  description?: string;
  handler: (args: string, ctx: ExtCommandCtx) => Promise<void>;
}

export interface PiApi {
  registerCommand(name: string, def: CommandDef): void;
}
