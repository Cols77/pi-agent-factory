// Minimal structural subset of Pi's real ExtensionAPI/ExtensionContext that
// this extension actually uses. Pinned against the real
// @earendil-works/pi-coding-agent package's types by type-compat-check.ts
// (Task 5) so drift is caught at typecheck time, not discovered later.

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
