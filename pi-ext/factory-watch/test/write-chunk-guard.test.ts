import { appendFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { registerWriteChunkGuard, WRITE_GUIDANCE_APPEND } from "../src/write-chunk-guard.js";
import { WRITE_CHUNK_THRESHOLD_CHARS } from "../src/write-chunker.js";
import type {
  BeforeAgentStartEvent,
  BeforeAgentStartEventResult,
  EventCtx,
  PiApi,
  ToolCallEvent,
  ToolCallEventResult,
  ToolResultEvent,
  ToolResultEventResult,
} from "../src/pi-types.js";

vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return { ...actual, appendFileSync: vi.fn() };
});

function setup(): {
  toolCall: (event: ToolCallEvent, ctx: EventCtx) => ToolCallEventResult | void;
  toolResult: (event: ToolResultEvent) => ToolResultEventResult | void;
  beforeAgentStart: (event: BeforeAgentStartEvent) => BeforeAgentStartEventResult | void;
} {
  const handlers: Record<string, (...args: never[]) => unknown> = {};
  const pi: PiApi = {
    registerCommand: () => {},
    on: ((event: string, handler: (...args: never[]) => unknown) => {
      handlers[event] = handler;
    }) as PiApi["on"],
  };
  registerWriteChunkGuard(pi);
  return {
    toolCall: handlers["tool_call"] as (event: ToolCallEvent, ctx: EventCtx) => ToolCallEventResult | void,
    toolResult: handlers["tool_result"] as (event: ToolResultEvent) => ToolResultEventResult | void,
    beforeAgentStart: handlers["before_agent_start"] as (
      event: BeforeAgentStartEvent,
    ) => BeforeAgentStartEventResult | void,
  };
}

const ctx: EventCtx = { cwd: "/repo" };

describe("registerWriteChunkGuard", () => {
  beforeEach(() => {
    vi.mocked(appendFileSync).mockReset();
  });

  test("leaves a small write call untouched", () => {
    const { toolCall } = setup();
    const event: ToolCallEvent = {
      type: "tool_call",
      toolCallId: "call-1",
      toolName: "write",
      input: { path: "small.txt", content: "hello" },
    };
    const result = toolCall(event, ctx);
    expect(result).toBeUndefined();
    expect(event.input.content).toBe("hello");
  });

  test("ignores non-write tool calls even when large", () => {
    const { toolCall } = setup();
    const bigContent = "x".repeat(WRITE_CHUNK_THRESHOLD_CHARS + 1);
    const event: ToolCallEvent = {
      type: "tool_call",
      toolCallId: "call-2",
      toolName: "edit",
      input: { path: "big.txt", content: bigContent },
    };
    toolCall(event, ctx);
    expect(event.input.content).toBe(bigContent);
  });

  test("truncates an oversized write call to its first chunk and completes the rest on tool_result", () => {
    const { toolCall, toolResult } = setup();
    const bigContent =
      "a".repeat(WRITE_CHUNK_THRESHOLD_CHARS) + "b".repeat(WRITE_CHUNK_THRESHOLD_CHARS) + "c";
    const callEvent: ToolCallEvent = {
      type: "tool_call",
      toolCallId: "call-3",
      toolName: "write",
      input: { path: "big.txt", content: bigContent },
    };
    toolCall(callEvent, ctx);
    expect(callEvent.input.content).toBe("a".repeat(WRITE_CHUNK_THRESHOLD_CHARS));

    const resultEvent: ToolResultEvent = {
      type: "tool_result",
      toolCallId: "call-3",
      toolName: "write",
      input: callEvent.input,
      isError: false,
    };
    const result = toolResult(resultEvent);

    const expectedPath = resolve("/repo", "big.txt");
    expect(appendFileSync).toHaveBeenNthCalledWith(1, expectedPath, "b".repeat(WRITE_CHUNK_THRESHOLD_CHARS));
    expect(appendFileSync).toHaveBeenNthCalledWith(2, expectedPath, "c");
    expect(result?.content?.[0]?.text).toContain(String(bigContent.length));
    expect(result?.content?.[0]?.text).toContain("Do not retry");
  });

  test("does not append chunks when the truncated write itself failed", () => {
    const { toolCall, toolResult } = setup();
    const bigContent = "x".repeat(WRITE_CHUNK_THRESHOLD_CHARS + 10);
    const callEvent: ToolCallEvent = {
      type: "tool_call",
      toolCallId: "call-4",
      toolName: "write",
      input: { path: "big.txt", content: bigContent },
    };
    toolCall(callEvent, ctx);

    const resultEvent: ToolResultEvent = {
      type: "tool_result",
      toolCallId: "call-4",
      toolName: "write",
      input: callEvent.input,
      isError: true,
    };
    const result = toolResult(resultEvent);

    expect(appendFileSync).not.toHaveBeenCalled();
    expect(result).toBeUndefined();
  });

  test("ignores tool_result events with no pending chunked write", () => {
    const { toolResult } = setup();
    const resultEvent: ToolResultEvent = {
      type: "tool_result",
      toolCallId: "unknown-call",
      toolName: "write",
      input: { path: "small.txt", content: "hello" },
      isError: false,
    };
    const result = toolResult(resultEvent);
    expect(result).toBeUndefined();
    expect(appendFileSync).not.toHaveBeenCalled();
  });

  test("appends write-size guidance to the system prompt", () => {
    const { beforeAgentStart } = setup();
    const event: BeforeAgentStartEvent = { type: "before_agent_start", systemPrompt: "base prompt" };
    const result = beforeAgentStart(event);
    expect(result?.systemPrompt).toBe("base prompt" + WRITE_GUIDANCE_APPEND);
  });
});
