import { spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import type { CliResult } from "./cli-runner.js";

// Long-lived execution engine for /api/system/*: one `factory.system worker`
// process per served repo root, speaking the JSON-lines protocol defined in
// src/factory/system/worker.py. Amortizes interpreter boot + module import
// (~1-1.5s per process today) across every request, and keeps each request
// off Node's event loop without a fresh spawn. This file holds process and
// protocol mechanics only -- it never re-derives freshness, ordering, or
// provenance, and it never interprets a payload. When the worker is
// unusable (spawn failure, crash, hang, protocol corruption) the caller
// falls back to the existing one-shot CLI runner; `null` is how this module
// says "not usable now -- use the fallback".
//
// Lifecycle: lazily spawned on first request, killed by stopSystemWorker()
// (called from stopDocsServer). A killed/hung worker is discarded and the
// next request spawns a fresh one.
export interface WorkerRequest {
  cmd: string;
  params: Record<string, string>;
}

interface RunningWorker {
  cwd: string;
  child: ChildProcessWithoutNullStreams;
  seq: number;
  pending: Map<number, (value: CliResult<unknown> | null) => void>;
}

let worker: RunningWorker | null = null;

const REQUEST_TIMEOUT_MS = 20_000;

function buildWorkerCommand(cwd: string): { bin: string; args: string[] } {
  return {
    bin: "uv",
    // `-u` (unbuffered) plus the worker's own per-line flush: a piped stdout
    // must never sit in a buffer while the caller waits for its response.
    args: ["run", "python", "-u", "-m", "factory.system", "worker", "--repo-root", cwd],
  };
}

function rejectAllPending(target: RunningWorker, reason: null): void {
  for (const resolve of target.pending.values()) resolve(reason);
  target.pending.clear();
}

/** Drop the current worker (if any), rejecting every pending request with
 * `null` so each caller takes its fallback path. */
export function stopSystemWorker(): void {
  if (worker === null) return;
  const current = worker;
  worker = null;
  rejectAllPending(current, null);
  try {
    current.child.stdin.end();
  } catch {
    // stdin already closed -- nothing to end.
  }
  current.child.kill();
}

/** Spawn a worker for `cwd` if none is running. Returns false when spawning
 * is impossible (e.g. `uv` missing) -- the caller then uses its fallback. */
function ensureWorker(cwd: string): RunningWorker | null {
  if (worker !== null) {
    if (worker.cwd === cwd && worker.child.exitCode === null) return worker;
    stopSystemWorker();
  }
  const { bin, args } = buildWorkerCommand(cwd);
  let child: ChildProcessWithoutNullStreams;
  try {
    child = spawn(bin, args, {
      cwd,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
  } catch {
    return null;
  }
  const running: RunningWorker = { cwd, child, seq: 0, pending: new Map() };
  worker = running;

  // stdout is the protocol: one JSON response line per request. Anything
  // unparseable is protocol corruption -- discard the worker and fall back,
  // never half-parse a response. If the readline setup itself fails (e.g. an
  // unusual spawn shim), discard the worker rather than leaving a
  // half-registered one behind.
  let lines: ReturnType<typeof createInterface>;
  try {
    lines = createInterface({ input: child.stdout });
  } catch {
    if (worker === running) worker = null;
    try {
      child.kill();
    } catch {
      // best effort
    }
    return null;
  }
  lines.on("line", (raw) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      stopSystemWorker();
      return;
    }
    if (typeof parsed !== "object" || parsed === null) {
      stopSystemWorker();
      return;
    }
    const record = parsed as { id?: unknown; ok?: unknown; value?: unknown; error?: unknown };
    if (typeof record.id !== "number") {
      // Not one of our responses (or a malformed one) -- protocol corruption.
      stopSystemWorker();
      return;
    }
    const resolve = running.pending.get(record.id);
    if (resolve === undefined) {
      // A response for a request we already gave up on (timed out): ignore.
      return;
    }
    running.pending.delete(record.id);
    if (record.ok === true) {
      resolve({ ok: true, value: record.value as unknown });
    } else {
      resolve({
        ok: false,
        error: typeof record.error === "string" ? record.error : "worker command failed",
      });
    }
  });

  child.once("error", () => {
    if (worker === running) worker = null;
    rejectAllPending(running, null);
  });
  child.once("exit", () => {
    if (worker === running) worker = null;
    rejectAllPending(running, null);
  });

  // Stderr is diagnostics only -- never part of the protocol.
  child.stderr.on("data", () => {
    // swallow: the worker's stderr carries startup noise and warnings.
  });
  return running;
}

/** Ask the worker for one read-only projection.
 *
 * Resolves with:
 * - `CliResult<T>` (non-null) when the worker answered -- including structured
 *   domain errors like an unresolvable scope, which the route reports as a
 *   503 exactly as the one-shot CLI would;
 * - `null` when the worker was unusable (not running, crashed, hung,
 *   protocol corruption) -- the caller falls back to the one-shot CLI.
 */
export function systemWorkerRequest<T>(
  cwd: string,
  request: WorkerRequest,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<CliResult<T> | null> {
  const running = ensureWorker(cwd);
  if (running === null) return Promise.resolve(null);
  const id = ++running.seq;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      running.pending.delete(id);
      // A hung worker would wedge every later request: discard it so the
      // next request respawns a fresh process.
      stopSystemWorker();
      resolve(null);
    }, timeoutMs);
    running.pending.set(id, (value) => {
      clearTimeout(timer);
      resolve(value as CliResult<T> | null);
    });
    running.child.stdin.write(JSON.stringify({ id, ...request }) + "\n");
  });
}