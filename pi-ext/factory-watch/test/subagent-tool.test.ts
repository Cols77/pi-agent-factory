import { describe, expect, test } from "vitest";
import {
  createJsonlCollector,
  createIdleKeeper,
  deriveSubagentLabel,
  executeSubagent,
  probeFileHeartbeat,
  parseChildJsonl,
  renderChildOutcome,
  renderSubagentOutcome,
  spawnStreamedChild,
  subagentTool,
  summarizeSubagentTask,
  SUBAGENT_IDLE_GRACE_BREACHES,
  SUBAGENT_TIMEOUT_MS,
} from "../src/subagent-tool.js";
import { chmodSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

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
    // The child's own totalTimeoutMs is 10s, so a vitest budget above that
    // (not the suite default 5s) is what makes this wall-clock measurement
    // stable under parallel load: a 5s cap killed a passing test right at the
    // boundary whenever the rest of the suite contended for the CPU. The
    // assertions above are the real behavioural checks and are untouched.
  }, 20_000);

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

describe("liveness-aware idle keeper (T-029)", () => {
  test("a silent child is killed only after grace consecutive breaches", () => {
    // Fake clock: each call advances one full idle window.
    let t = 0;
    const now = () => t;
    const k = createIdleKeeper({ idleMs: 300, graceBreaches: 3, now });
    // Three silent windows (no probe -> no liveness) tripped the strike.
    expect(k.onElapsed()).toBe("keep-running");
    expect(k.onElapsed()).toBe("keep-running");
    expect(k.onElapsed()).toBe("keep-running");
    expect(k.onElapsed()).toBe("kill");
  });

  test("any reported output resets the breach count", () => {
    let t = 0;
    const now = () => t;
    const k = createIdleKeeper({ idleMs: 300, graceBreaches: 2, now });
    expect(k.onElapsed()).toBe("keep-running");
    k.noteLive(); // a tool-call / line arrived: alive again
    expect(k.breaches()).toBe(0);
    expect(k.onElapsed()).toBe("keep-running"); // window 1 after reset: b=1
    expect(k.onElapsed()).toBe("keep-running"); // window 2 after reset: b=2 <= grace
    expect(k.onElapsed()).toBe("kill"); // window 3 after reset: b=3 > grace=2
  });

  test("a file-write heartbeat probe keeps a silent child alive (plan authoring)", () => {
    let t = 0;
    const now = () => t;
    let lastProbeSince = -1;
    const k = createIdleKeeper({
      idleMs: 300,
      graceBreaches: 2,
      now,
      // Simulates the deliverable-dir mtime probe reporting fresh writes.
      probe: (since: number) => {
        lastProbeSince = since;
        return true; // files keep landing -> alive
      },
    });
    // Many silent windows: never trips idle because the probe stays live.
    for (let i = 0; i < 50; i++) {
      expect(k.onElapsed()).toBe("keep-running");
    }
    expect(k.breaches()).toBe(0);
  });

  test("the file-heartbeat probe sees fresh writes under watch dirs", () => {
    const dir = mkdtempSync(join(tmpdir(), "pif-pulse-"));
    const sub = join(dir, "plans");
    mkdirSync(sub, { recursive: true });
    // Future watermark: nothing is newer than it, so no heartbeat yet.
    expect(probeFileHeartbeat([sub], Date.now() + 60_000)).toBe(false);
    writeFileSync(join(sub, "plan.md"), "# plan - updated", "utf-8");
    // Past watermark: the fresh write is newer -> heartbeat alive.
    expect(probeFileHeartbeat([sub], Date.now() - 60_000)).toBe(true);
    // Future watermark again: no write after it -> quiet again.
    expect(probeFileHeartbeat([sub], Date.now() + 60_000)).toBe(false);
  });
});

describe("executeSubagent deps wiring (resolveRoot contract)", () => {
  test("a build-only override still gets a wired resolveRoot (regression guard)", async () => {
    const dir = mkdtempSync(join(tmpdir(), "pif-root-"));
    let capturedRoot: string | null = null;
    const build = (input: { root: string }) => {
      capturedRoot = input.root;
      throw new Error("BUILD_RAN"); // short-circuit before any real spawn
    };
    try {
      await executeSubagent("do the thing", { cwd: dir, model: { provider: "p", id: "m" } }, { build });
    } catch (err) {
      // If resolveRoot were left undefined (the old `deps.resolveRoot is
      // not a function` failure) we would never reach the build override.
      expect(String(err)).toContain("BUILD_RAN");
    }
    expect(capturedRoot).toBeTruthy(); // default resolveProjectRoot merged in
  });

  test("a label-only override still gets default build + resolveRoot", async () => {
    const dir = mkdtempSync(join(tmpdir(), "pif-root-"));
    let capturedRoot: string | null = null;
    const build = (input: { root: string }) => {
      capturedRoot = input.root;
      throw new Error("BUILD_RAN");
    };
    // Override build (as a stand-in for observing the merged root) while
    // passing only a label; defaults for build/resolveRoot stay intact.
    const depsWithoutRoot = { label: "dev" };
    try {
      await executeSubagent("do the thing", { cwd: dir, model: { provider: "p", id: "m" } }, { ...depsWithoutRoot, build });
    } catch (err) {
      expect(String(err)).toContain("BUILD_RAN");
    }
    expect(typeof capturedRoot).toBe("string");
    expect((capturedRoot ?? "").length).toBeGreaterThan(0);
  });
});

describe("subagent label + task summary (T-029 follow-up)", () => {
  test("the public tool accepts a label-only override while retaining default dependencies", async () => {
    const fakePiDir = mkdtempSync(join(tmpdir(), "pif-subagent-tool-"));
    const fakePi = join(fakePiDir, process.platform === "win32" ? "fake-pi.cmd" : "fake-pi");
    const childEvent = JSON.stringify({
      type: "message_end",
      message: { role: "assistant", content: [{ type: "text", text: "default dependencies used" }] },
    });
    if (process.platform === "win32") {
      writeFileSync(fakePi, `@echo off\r\necho ${childEvent}\r\n`, "utf-8");
    } else {
      writeFileSync(fakePi, `#!/bin/sh\nprintf '%s\\n' '${childEvent}'\n`, "utf-8");
      chmodSync(fakePi, 0o755);
    }
    const previousPi = process.env.PI_SUBAGENT_BIN;
    process.env.PI_SUBAGENT_BIN = fakePi;
    try {
      const result = await subagentTool.execute(
        "call-1",
        { task: "review the defaults", name: "custom-reviewer" },
        undefined,
        undefined,
        { cwd: process.cwd() },
      );
      expect(result.content[0]?.text).toContain("subagent[custom-reviewer]");
      expect(result.content[0]?.text).toContain("default dependencies used");
    } finally {
      if (previousPi === undefined) delete process.env.PI_SUBAGENT_BIN;
      else process.env.PI_SUBAGENT_BIN = previousPi;
      rmSync(fakePiDir, { recursive: true, force: true });
    }
  });

  test("derives a role label from task keywords", () => {
    expect(deriveSubagentLabel("Research how the runner resolves the lock")).toBe("researcher");
    expect(deriveSubagentLabel("Implement the process-tree kill in pi_backend")).toBe("dev");
    expect(deriveSubagentLabel("Review the diff for the coverage command")).toBe("reviewer");
    expect(deriveSubagentLabel("Draft the design doc for the new API")).toBe("docs");
  });

  test("an explicit fallback label wins over the derived one", () => {
    expect(deriveSubagentLabel("Implement the fix", "refactoring")).toBe("refactoring");
    expect(deriveSubagentLabel("", "dev")).toBe("dev");
  });

  test("unmatched or blank tasks fall back to worker", () => {
    expect(deriveSubagentLabel("")).toBe("worker");
    expect(deriveSubagentLabel("do the thing")).toBe("worker");
  });

  test("summarize collapses whitespace and truncates to the width", () => {
    expect(summarizeSubagentTask("one\n  two   three\nfour", 100)).toBe("one two three four");
    const long = "x".repeat(300);
    const s = summarizeSubagentTask(long, 50);
    expect(s.length).toBeLessThanOrEqual(50);
    expect(s.endsWith("…")).toBe(true);
  });

  test("summarize clamps a non-positive width to empty", () => {
    expect(summarizeSubagentTask("anything", 0)).toBe("");
    expect(summarizeSubagentTask("anything", -1)).toBe("");
  });
});
