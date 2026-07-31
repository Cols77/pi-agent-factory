import { appendFileSync } from "node:fs";
import { resolve } from "node:path";
import { splitContent, WRITE_CHUNK_THRESHOLD_CHARS } from "./write-chunker.js";
import type {
  BeforeAgentStartEvent,
  BeforeAgentStartEventResult,
  EventCtx,
  PiApi,
  TextContent,
  ToolCallEvent,
  ToolCallEventResult,
  ToolResultEvent,
  ToolResultEventResult,
} from "./pi-types.js";

// Mitigates a real, unresolved-upstream failure mode (earendil-works/pi
// #4408, #4430) where a single oversized write/edit tool call can arrive
// corrupted -- missing `path`, truncated `content` -- because the model
// ran out of its configured max output tokens mid-generation. We can't fix
// that (it already happened before any extension sees the call), but we
// CAN stop the model from ever needing to attempt one huge write: once a
// large-but-intact write call reaches us, mutate it down to a small first
// chunk (safe for the built-in write tool to execute), then finish writing
// the rest ourselves directly -- the model never has to generate more
// tool calls for the remaining content.
export const WRITE_GUIDANCE_APPEND =
  "\n\nWhen writing a file whose content would exceed roughly " +
  `${WRITE_CHUNK_THRESHOLD_CHARS} characters, prefer writing an initial ` +
  "section and appending the rest with edit calls, rather than one large " +
  "write -- very large single write calls are more likely to fail on some models.";

interface PendingWrite {
  absolutePath: string;
  remainingChunks: string[];
  totalChars: number;
  chunkCount: number;
}

function isWriteInput(input: Record<string, unknown>): input is { path: string; content: string } {
  return typeof input.path === "string" && typeof input.content === "string";
}

export function registerWriteChunkGuard(pi: PiApi): void {
  const pending = new Map<string, PendingWrite>();

  pi.on("tool_call", (event: ToolCallEvent, ctx: EventCtx): ToolCallEventResult | void => {
    if (event.toolName !== "write" || !isWriteInput(event.input)) {
      return;
    }
    const { path, content } = event.input;
    if (content.length <= WRITE_CHUNK_THRESHOLD_CHARS) {
      return;
    }

    const chunks = splitContent(content, WRITE_CHUNK_THRESHOLD_CHARS);
    const firstChunk = chunks[0] ?? "";
    const remainingChunks = chunks.slice(1);
    pending.set(event.toolCallId, {
      absolutePath: resolve(ctx.cwd, path),
      remainingChunks,
      totalChars: content.length,
      chunkCount: chunks.length,
    });
    event.input.content = firstChunk;
  });

  pi.on("tool_result", (event: ToolResultEvent): ToolResultEventResult | void => {
    const state = pending.get(event.toolCallId);
    if (state === undefined) {
      return;
    }
    pending.delete(event.toolCallId);
    if (event.isError) {
      return;
    }

    for (const chunk of state.remainingChunks) {
      appendFileSync(state.absolutePath, chunk);
    }

    const text: TextContent = {
      type: "text",
      text:
        `Wrote ${state.totalChars} chars to ${state.absolutePath} ` +
        `(split into ${state.chunkCount} chunks to avoid a known large-write ` +
        "failure mode). Do not retry this write.",
    };
    return { content: [text] };
  });

  pi.on(
    "before_agent_start",
    (event: BeforeAgentStartEvent): BeforeAgentStartEventResult => ({
      systemPrompt: event.systemPrompt + WRITE_GUIDANCE_APPEND,
    }),
  );
}
