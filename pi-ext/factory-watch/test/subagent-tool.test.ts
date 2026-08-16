import { describe, expect, test } from "vitest";
import {
  parseChildJsonl,
  renderSubagentOutcome,
  SUBAGENT_MAX_BUFFER,
  SUBAGENT_TIMEOUT_MS,
} from "../src/subagent-tool.js";

const sessionEvent = (id = "ses-123") =>
  JSON.stringify({ type: "session", version: 3, id, cwd: "C:\\repo" });
const textEnd = (role: string, text: string) =>
  JSON.stringify({
    type: "message_end",
    message: { role, content: [{ type: "text", text }] },
  });
const thinkingEnd = (role: string, thinking: string) =>
  JSON.stringify({
    type: "message_end",
    message: { role, content: [{ type: "thinking", thinking }] },
  });

describe("parseChildJsonl", () => {
  test("extracts the final assistant text block from message_end events", () => {
    const stdout = [
      sessionEvent(),
      JSON.stringify({ type: "agent_start" }),
      textEnd("user", "TASK do x"),
      textEnd("assistant", "The answer is 42."),
      JSON.stringify({ type: "agent_end" }),
    ].join("\n");
    const answer = parseChildJsonl(stdout);
    expect(answer.text).toBe("The answer is 42.");
    expect(answer.thinkingOnly).toBe(false);
    expect(answer.assistantMessages).toBe(1);
    expect(answer.sessionId).toBe("ses-123");
    expect(answer.lastEventType).toBe("agent_end");
    expect(answer.jsonEvents).toBe(5);
  });

  test("keeps only the LAST assistant message (earlier turns are intermediate)", () => {
    const stdout = [
      textEnd("assistant", "Let me check that file."),
      textEnd("assistant", "Final answer."),
    ].join("\n");
    const answer = parseChildJsonl(stdout);
    expect(answer.text).toBe("Final answer.");
    expect(answer.assistantMessages).toBe(2);
  });

  test("falls back to thinking blocks when no text block was emitted", () => {
    const stdout = [thinkingEnd("assistant", "manifest json here")].join("\n");
    const answer = parseChildJsonl(stdout);
    expect(answer.text).toBe("manifest json here");
    expect(answer.thinkingOnly).toBe(true);
  });

  test("ignores user/custom messages, tool-call blocks, and non-JSON noise", () => {
    const stdout = [
      "some non-json banner line",
      textEnd("user", "prompt"),
      JSON.stringify({
        type: "message_end",
        message: { role: "assistant", content: [{ type: "tool_call", id: "t1", name: "bash" }] },
      }),
      JSON.stringify({ type: "custom_message", message: { role: "custom", customType: "factory-code-context" } }),
    ].join("\n");
    const answer = parseChildJsonl(stdout);
    expect(answer.text).toBe("");
    expect(answer.assistantMessages).toBe(1); // tool_call assistant message counted
    expect(answer.jsonEvents).toBe(3);
  });

  test("captures the first error-ish event as failureEvent", () => {
    const stdout = [
      JSON.stringify({ type: "error", error: "provider: model not found" }),
      textEnd("assistant", "unused"),
    ].join("\n");
    const answer = parseChildJsonl(stdout);
    expect(answer.failureEvent).toBe("provider: model not found");
    expect(answer.text).toBe("unused");
  });

  test("empty and garbage input parse to an empty answer", () => {
    const empty = parseChildJsonl("");
    expect(empty.text).toBe("");
    expect(empty.jsonEvents).toBe(0);
    const garbage = parseChildJsonl("not json\nstill not\n");
    expect(garbage.jsonEvents).toBe(0);
  });
});

describe("renderSubagentOutcome", () => {
  test("timeout is reported as a spawn failure with the budget", () => {
    const err = new Error("spawnSync pi ETIMEDOUT") as Error & { code?: string };
    err.code = "ETIMEDOUT";
    const msg = renderSubagentOutcome({
      status: null,
      signal: null,
      error: err,
      stdout: "",
      stderr: "",
    });
    expect(msg).toContain("subagent spawn failed");
    expect(msg).toContain(String(SUBAGENT_TIMEOUT_MS));
  });

  test("ENOBUFS (over-budget output) is reported distinctly, not as (no stderr)", () => {
    const err = new Error("spawnSync pi ENOBUFS") as Error & { code?: string };
    err.code = "ENOBUFS";
    const msg = renderSubagentOutcome({
      status: null,
      signal: null,
      error: err,
      stdout: "",
      stderr: "",
    });
    expect(msg).toContain("subagent spawn failed");
    expect(msg).toContain(String(SUBAGENT_MAX_BUFFER));
  });

  test("generic spawn error includes the message and code", () => {
    const err = new Error("spawnSync pi ENOENT") as Error & { code?: string };
    err.code = "ENOENT";
    const msg = renderSubagentOutcome({ status: null, signal: null, error: err, stdout: "", stderr: "" });
    expect(msg).toContain("subagent spawn failed");
    expect(msg).toContain("spawnSync pi ENOENT");
    expect(msg).toContain("(code ENOENT)");
  });

  test("non-zero exit uses stderr when present", () => {
    const msg = renderSubagentOutcome({
      status: 1,
      signal: null,
      error: null,
      stdout: "",
      stderr: "boom: bad thing",
    });
    expect(msg).toContain("subagent failed (exit 1)");
    expect(msg).toContain("boom: bad thing");
  });

  test("non-zero exit with empty stderr falls back to the JSONL error event", () => {
    const msg = renderSubagentOutcome({
      status: 1,
      signal: null,
      error: null,
      stdout: JSON.stringify({ type: "provider_error", error: "rate limited" }),
      stderr: "",
    });
    expect(msg).toContain("subagent failed (exit 1)");
    expect(msg).toContain("rate limited");
    expect(msg).not.toContain("(no stderr)");
  });

  test("non-zero exit with neither stderr nor error event falls back to stdout tail", () => {
    const msg = renderSubagentOutcome({
      status: 1,
      signal: null,
      error: null,
      stdout: "garbage that tells a story\n".repeat(200),
      stderr: "",
    });
    expect(msg).toContain("subagent failed (exit 1)");
    expect(msg).toContain("stdout tail");
  });

  test("reports the signal on a non-zero exit", () => {
    const msg = renderSubagentOutcome({
      status: null,
      signal: "SIGTERM",
      error: null,
      stdout: "",
      stderr: "killed",
    });
    expect(msg).toContain("signal SIGTERM");
  });

  test("exit 0 returns the extracted answer", () => {
    const stdout = [sessionEvent(), textEnd("assistant", "Done: all green.")].join("\n");
    const msg = renderSubagentOutcome({ status: 0, signal: null, error: null, stdout, stderr: "" });
    expect(msg).toBe("subagent output:\nDone: all green.");
  });

  test("exit 0 notes when the answer came from thinking blocks", () => {
    const stdout = [thinkingEnd("assistant", "json only")].join("\n");
    const msg = renderSubagentOutcome({ status: 0, signal: null, error: null, stdout, stderr: "" });
    expect(msg).toContain("json only");
    expect(msg).toContain("thinking block");
  });

  test("exit 0 with JSON but no assistant text reports a shape mismatch, not an empty run", () => {
    const stdout = [sessionEvent(), JSON.stringify({ type: "agent_end" })].join("\n");
    const msg = renderSubagentOutcome({ status: 0, signal: null, error: null, stdout, stderr: "" });
    expect(msg).toContain("possible event-shape mismatch");
    expect(msg).toContain("Raw tail");
  });

  test("exit 0 with genuinely nothing reports empty output", () => {
    const msg = renderSubagentOutcome({ status: 0, signal: null, error: null, stdout: "", stderr: "" });
    expect(msg).toContain("(empty output)");
  });
});
