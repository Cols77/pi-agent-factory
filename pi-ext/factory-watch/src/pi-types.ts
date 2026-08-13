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
import type { Theme, ToolDefinition } from "@earendil-works/pi-coding-agent";

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
  confirm(title: string, message: string): Promise<boolean>;
  editor(title: string, prefill?: string): Promise<string | undefined>;
  custom<T>(
    factory: (tui: TUI, theme: Theme, keybindings: KeybindingsManager, done: (result: T) => void) => Component,
    options?: { overlay?: boolean; overlayOptions?: OverlayOptions },
  ): Promise<T>;
}

export interface ExtCommandCtx {
  cwd: string;
  ui: UiApi;
  model: ModelInfo | undefined;
  hasUI: boolean;
  reload(): Promise<void>;
  newSession(options?: {
    withSession?: (ctx: ReplacedSessionCtx) => Promise<void>;
  }): Promise<{ cancelled: boolean }>;
}

export interface CommandDef {
  description?: string;
  handler: (args: string, ctx: ExtCommandCtx) => Promise<void>;
}

// Minimal structural subset of Pi's real event ctx (ExtensionContext) --
// only the field these hooks actually read.
export interface EventCtx {
  cwd: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  toolCallId: string;
  toolName: string;
  input: Record<string, unknown>;
}

export interface ToolCallEventResult {
  block?: boolean;
  reason?: string;
}

export interface TextContent {
  type: "text";
  text: string;
}

export interface ToolResultEvent {
  type: "tool_result";
  toolCallId: string;
  toolName: string;
  input: Record<string, unknown>;
  isError: boolean;
}

export interface ToolResultEventResult {
  content?: TextContent[];
}

export interface BeforeAgentStartEvent {
  type: "before_agent_start";
  systemPrompt: string;
}

export interface BeforeAgentStartEventResult {
  systemPrompt?: string;
}

export interface SessionShutdownEvent {
  type: "session_shutdown";
  reason: string;
  targetSessionFile?: string;
}

export interface PiApi {
  registerCommand(name: string, def: CommandDef): void;
  // Imported rather than hand-declared, for the same reason as TUI/Theme above:
  // a minimal re-declaration would be assignability risk with no benefit, and
  // type-compat-check.ts would not catch drift in a shape we invented.
  registerTool(tool: ToolDefinition<any, any, any>): void;
  on(
    event: "tool_call",
    handler: (event: ToolCallEvent, ctx: EventCtx) => ToolCallEventResult | void,
  ): void;
  on(
    event: "tool_result",
    handler: (event: ToolResultEvent, ctx: EventCtx) => ToolResultEventResult | void,
  ): void;
  on(
    event: "before_agent_start",
    handler: (event: BeforeAgentStartEvent, ctx: EventCtx) => BeforeAgentStartEventResult | void,
  ): void;
  on(
    event: "session_shutdown",
    handler: (event: SessionShutdownEvent, ctx: EventCtx) => void,
  ): void;
}
