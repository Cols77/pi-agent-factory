import { describe, expect, test } from "vitest";
import {
  createJsonlCollector,
  parseChildJsonl,
  renderChildOutcome,
  renderSubagentOutcome,
  spawnStreamedChild,
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

  test("incremental collector agrees with one-shot parse", () => {
    const stdout = [
      sessionEvent(),
      textEnd("user", "TASK"),
      thinkingEnd("assistant", "thinking..."),
      textEnd("assistant", "Final."),
    ].join("\n");
    const collector = createJsonlCollector();
    for (const line of stdout.split(/\r?\n/)) collector.pushLine(line);
    const incremental = collector.answer();
    const oneShot = parseChildJsonl(stdout);
    expect(incremental.text).toBe(oneShot.text);
    expect(incremental.thinkingOnly).toBe(oneShot.thinkingOnly);
    expect(incremental.jsonEvents).toBe(oneShot.jsonEvents);
    expect(incremental.assistantMessages).toBe(oneShot.assistantMessages);
    expect(incremental.sessionId).toBe(oneShot.sessionId);
    expect(incremental.text).toBe("Final.");
  });
});

// Real subprocesses: prove the streaming runner survives streams the old
// sync maxBuffer (1 MiB) would have killed with ENOBUFS, and that both
// timeout budgets really kill a stalled child.
describe("spawnStreamedChild", () => {
  const node = process.execPath;

  test("extracts the answer from a real child stream", async () => {
    const script = [
      `console.log(${JSON.stringify(JSON.stringify({ type: "session", id: "real-1" }))});`,
      `console.log(${JSON.stringify(
        JSON.stringify({
          type: "message_end",
          message: { role: "assistant", content: [{ type: "text", text: "real answer" }] },
        }),
      )});`,
    ].join("\n");
    const run = await spawnStreamedChild(node, ["-e", script], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      idleTimeoutMs: 5_000,
      totalTimeoutMs: 5_000,
    });
    expect(run.status).toBe(0);
    expect(run.killedFor).toBeNull();
    expect(run.answer.text).toBe("real answer");
    expect(run.answer.sessionId).toBe("real-1");
  });

  test("survives a multi-MB stream (old ENOBUFS failure mode) with bounded tails", async () => {
    const line = `JSON.stringify({ type: "tool_execution_end", toolName: "bash", result: ${'"x".repeat(100)'} })`;
    const answer = `JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "big stream done" }] } })`;
    const script = `const line = ${line};\nfor (let i = 0; i < 20000; i++) console.log(line);\nconsole.log(${answer});`;
    const run = await spawnStreamedChild(node, ["-e", script], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      idleTimeoutMs: 10_000,
      totalTimeoutMs: 10_000,
    });
    expect(run.status).toBe(0);
    expect(run.killedFor).toBeNull();
    expect(run.answer.text).toBe("big stream done");
    // ~2.4 MB streamed; only bounded tails retained.
    expect(run.stdoutTail.length).toBeLessThanOrEqual(2100);
    expect(run.stdoutTail).toContain("big stream done");
  });

  test("idle timeout kills a child that goes silent", async () => {
    const run = await spawnStreamedChild(node, ["-e", "console.log('hi'); setTimeout(()=>{}, 60000)"], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      idleTimeoutMs: 400,
      totalTimeoutMs: 10_000,
    });
    expect(run.killedFor).toBe("idle");
    expect(run.status).not.toBe(0);
  });

  test("total timeout kills a child that keeps producing", async () => {
    const run = await spawnStreamedChild(node, ["-e", "setInterval(()=>console.log('tick'), 50)"], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      idleTimeoutMs: 10_000,
      totalTimeoutMs: 500,
    });
    expect(run.killedFor).toBe("total");
  });

  test("spawn error surfaces on the run", async () => {
    const run = await spawnStreamedChild("definitely-not-a-real-binary-xyz", [], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      idleTimeoutMs: 2_000,
      totalTimeoutMs: 2_000,
    });
    expect(run.error).not.toBeNull();
  });
});

describe("renderChildOutcome", () => {
  test("idle kill is reported distinctly", () => {
    const msg = renderChildOutcome({
      status: null,
      signal: "SIGTERM",
      error: null,
      answer: parseChildJsonl(""),
      stdoutTail: "",
      stderrTail: "",
      killedFor: "idle",
    });
    expect(msg).toContain("subagent killed");
    expect(msg).toContain("idle timeout");
  });

  test("total kill is reported distinctly", () => {
    const msg = renderChildOutcome({
      status: null,
      signal: "SIGTERM",
      error: null,
      answer: parseChildJsonl(""),
      stdoutTail: "",
      stderrTail: "",
      killedFor: "total",
    });
    expect(msg).toContain("subagent killed");
    expect(msg).toContain("total timeout");
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
    expect(msg).toContain("streamed"); // streaming makes ENOBUFS unreachable
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
