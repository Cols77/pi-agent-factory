import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

// A fake `spawn` that returns an EventEmitter-shaped child so the protocol
// mechanics (request line written, id-matched responses, crash/timeout
// fallback) are tested without ever spawning a process.
class FakeStream extends EventEmitter {
  write = vi.fn<() => boolean>();
  end = vi.fn<() => void>();
}

// readline requires a real Readable on its input side (needs resume/ pushing);
// small subclass keeps the protocol test honest without a child process.
class FakeStdout extends Readable {
  _read(): void {
    // Data is pushed manually via pushLine; nothing to fetch.
  }
  pushLine(line: string): void {
    this.push(line + "\n");
  }
}

function fakeChild() {
  const child = new EventEmitter() as FakeChild & { emitLine(line: string): void; emitExit(code?: number): void };
  Object.assign(child, {
    stdin: new FakeStream(),
    stdout: new FakeStdout(),
    stderr: new FakeStream(),
    exitCode: null,
    kill: vi.fn<() => boolean>(),
  });
  child.emitLine = (line: string) => {
    child.stdout.pushLine(line);
  };
  child.emitExit = (code = 0) => {
    child.exitCode = code;
    child.emit("exit", code, null);
  };
  return child;
}

interface FakeChild extends EventEmitter {
  stdin: FakeStream;
  stdout: FakeStdout;
  stderr: FakeStream;
  exitCode: number | null;
  kill: ReturnType<typeof vi.fn>;
  emitLine(line: string): void;
  emitExit(code?: number): void;
}

const spawnMock = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawn: spawnMock, spawnSync: vi.fn() }));

import { stopSystemWorker, systemWorkerRequest } from "../src/system-worker.js";

function lastChild(): FakeChild {
  expect(spawnMock).toHaveBeenCalled();
  return spawnMock.mock.results[spawnMock.mock.results.length - 1]!.value as FakeChild;
}

function requestLine(child: FakeChild): string {
  const writes = (child.stdin.write as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0] as string);
  return writes[writes.length - 1]!;
}

const tick = (): Promise<void> => new Promise((r) => setImmediate(r));

afterEach(() => {
  stopSystemWorker();
  spawnMock.mockReset();
  // mockReset drops any implementation; restore it for the next test.
  spawnMock.mockImplementation(() => fakeChild());
});

beforeEach(() => {
  spawnMock.mockImplementation(() => fakeChild());
});

describe("system worker protocol", () => {
  test("spawns one long-lived factory.system worker for a repo root", async () => {
    const result = systemWorkerRequest<{ n: number }>("/repo", { cmd: "scope", params: {} });
    const child = lastChild();
    child.emitLine(JSON.stringify({ id: 1, ok: true, value: { n: 1 } }));
    await expect(result).resolves.toEqual({ ok: true, value: { n: 1 } });
    expect(spawnMock).toHaveBeenCalledTimes(1);
    expect(spawnMock).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-u", "-m", "coherence.navigate", "worker", "--repo-root", "/repo"],
      expect.objectContaining({ cwd: "/repo", stdio: ["pipe", "pipe", "pipe"] }),
    );
    // The request line is the documented JSON protocol with a monotonic id.
    expect(JSON.parse(requestLine(child))).toEqual({ id: 1, cmd: "scope", params: {} });
  });

  test("reuses the running worker for subsequent requests (no re-spawn)", async () => {
    systemWorkerRequest("/repo", { cmd: "scope", params: {} });
    const child = lastChild();
    child.emitLine(JSON.stringify({ id: 1, ok: true, value: {} }));
    await tick();
    const second = systemWorkerRequest("/repo", { cmd: "labels", params: {} });
    child.emitLine(JSON.stringify({ id: 2, ok: true, value: { labels: {} } }));
    await expect(second).resolves.toEqual({ ok: true, value: { labels: {} } });
    expect(spawnMock).toHaveBeenCalledTimes(1);
  });

  test("surfaces a structured domain error as a non-null CliResult", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "brief", params: { scope: "bundle:missing" } });
    const child = lastChild();
    child.emitLine(JSON.stringify({
      id: 1, ok: false, error: "bundle not found: 'missing'", kind: "ScopeNotFoundError",
    }));
    await expect(result).resolves.toEqual({
      ok: false,
      error: "bundle not found: 'missing'",
    });
  });

  test("matches concurrent responses by id, out of order", async () => {
    const a = systemWorkerRequest<{ tag: string }>("/repo", { cmd: "brief", params: { scope: "a" } });
    const child = lastChild();
    const b = systemWorkerRequest<{ tag: string }>("/repo", { cmd: "matrix", params: { scope: "b" } });
    expect(JSON.parse(requestLine(child))).toEqual({ id: 2, cmd: "matrix", params: { scope: "b" } });
    child.emitLine(JSON.stringify({ id: 2, ok: true, value: { tag: "matrix-b" } }));
    child.emitLine(JSON.stringify({ id: 1, ok: true, value: { tag: "brief-a" } }));
    await expect(b).resolves.toEqual({ ok: true, value: { tag: "matrix-b" } });
    await expect(a).resolves.toEqual({ ok: true, value: { tag: "brief-a" } });
  });

  test("a crashed worker releases every pending request as null (fallback)", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "scope", params: {} });
    const child = lastChild();
    child.emitExit(1);
    await expect(result).resolves.toBeNull();
    // The next request spawns a fresh worker instead of reusing the corpse.
    const again = systemWorkerRequest("/repo", { cmd: "scope", params: {} });
    expect(spawnMock).toHaveBeenCalledTimes(2);
    const child2 = lastChild();
    child2.emitLine(JSON.stringify({ id: 1, ok: true, value: {} }));
    await expect(again).resolves.toEqual({ ok: true, value: {} });
  });

  test("a timed-out request falls back and discards the hung worker", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "scope", params: {} }, 30);
    const child = lastChild();
    await expect(result).resolves.toBeNull();
    expect(child.kill).toHaveBeenCalled();
  });

  test("stopSystemWorker rejects in-flight requests with null", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "scope", params: {} });
    stopSystemWorker();
    await expect(result).resolves.toBeNull();
  });

  test("a spawn failure resolves null immediately (caller falls back)", async () => {
    spawnMock.mockImplementation(() => {
      throw new Error("uv not found");
    });
    await expect(systemWorkerRequest("/repo", { cmd: "scope", params: {} })).resolves.toBeNull();
  });

  test("unparseable stdout is treated as protocol corruption, not a parse", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "scope", params: {} });
    const child = lastChild();
    child.stdout.emit("data", "not json at all\n");
    await expect(result).resolves.toBeNull();
    expect(child.kill).toHaveBeenCalled();
  });

  test("a response for an unknown id is ignored (already timed out)", async () => {
    const result = systemWorkerRequest("/repo", { cmd: "scope", params: {} }, 20);
    const child = lastChild();
    await expect(result).resolves.toBeNull();
    // A late stale response must not resolve anything or crash the worker.
    child.emitLine(JSON.stringify({ id: 1, ok: true, value: {} }));
    await tick();
    expect(child.kill).toHaveBeenCalled(); // timed out request already discarded worker
  });
});
