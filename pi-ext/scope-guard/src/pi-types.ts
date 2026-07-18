// Minimal structural subset of Pi's ExtensionAPI we depend on.
// At runtime Pi passes its real ExtensionAPI (a superset); this keeps the
// extension typecheckable/testable without installing the Pi package.
// Swap `PiApi` for `import type { ExtensionAPI }` once the dep is present.

export interface ToolCallEvent {
  toolName: string;
  input: { path?: string; command?: string };
}

export interface ExtCtx {
  cwd: string;
  hasUI?: boolean;
  mode?: "tui" | "rpc" | "json" | "print";
}

export type ToolCallResult = { block: true; reason: string } | undefined;

export type ToolCallHandler = (
  event: ToolCallEvent,
  ctx: ExtCtx,
) => Promise<ToolCallResult> | ToolCallResult;

export interface PiApi {
  on(event: "tool_call", handler: ToolCallHandler): void;
}
