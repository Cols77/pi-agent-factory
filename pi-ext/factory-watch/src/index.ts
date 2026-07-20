// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import { buildListCommand, buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus } from "./status-format.js";

const STATUS_FILE = "sessions/.factory-status.json";
const LOCK_FILE = "sessions/.factory-run.lock";
const LOG_FILE = "sessions/.factory-run.log";
const POLL_INTERVAL_MS = 1000;
const POSIX_GRACEFUL_TIMEOUT_MS = 3000;

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

export default function factoryWatch(pi: PiApi): void {
  let pollHandle: ReturnType<typeof setInterval> | undefined;

  function stopPolling(): void {
    if (pollHandle !== undefined) {
      clearInterval(pollHandle);
      pollHandle = undefined;
    }
  }

  pi.registerCommand("factory", {
    description: "Run the next todo factory task, watching progress live",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const statusPath = join(ctx.cwd, STATUS_FILE);

      const existingLockRaw = readFileIfExists(lockPath);
      if (existingLockRaw !== null) {
        const existingLock = parseLock(existingLockRaw);
        if (existingLock !== null && isPidAlive(existingLock.pid)) {
          ctx.ui.notify(
            `factory already running (pid ${existingLock.pid}) -- use /factory-stop first`,
            "warning",
          );
          return;
        }
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id);
      const logFd = openSync(join(ctx.cwd, LOG_FILE), "a");
      const child = spawn(cmd.bin, cmd.args, {
        cwd: ctx.cwd,
        detached: true,
        stdio: ["ignore", logFd, logFd],
      });
      child.unref();

      stopPolling();
      pollHandle = setInterval(() => {
        // ctx captured by this closure can outlive its session (e.g. a
        // single `-p` turn ending, or ctx.newSession()/fork()/reload() in an
        // interactive one) -- touching ctx.ui after that throws. Stop
        // polling instead of taking the whole host process down with an
        // uncaught exception on the next tick.
        try {
          const raw = readFileIfExists(statusPath);
          const record = raw === null ? null : parseStatus(raw);
          ctx.ui.setWidget("factory", formatStatusLines(record));

          const stillLocked = readFileIfExists(lockPath) !== null;
          if (!stillLocked) {
            stopPolling();
            ctx.ui.notify("factory run finished", "info");
          }
        } catch {
          stopPolling();
        }
      }, POLL_INTERVAL_MS);

      ctx.ui.notify(`factory started (${ctx.model.provider}/${ctx.model.id})`, "info");
    },
  });

  pi.registerCommand("factory-stop", {
    description: "Stop the currently running factory task",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const raw = readFileIfExists(lockPath);
      if (raw === null) {
        ctx.ui.notify("factory is not running", "info");
        return;
      }
      const lock = parseLock(raw);
      if (lock === null || !isPidAlive(lock.pid)) {
        ctx.ui.notify("factory lock is stale (process already gone)", "info");
        return;
      }

      if (process.platform === "win32") {
        spawnSync("taskkill", buildWindowsKillArgs(lock.pid));
      } else {
        try {
          process.kill(-lock.pid, "SIGTERM");
        } catch {
          // process group may already be gone; the liveness check below handles it
        }
        await new Promise((resolve) => setTimeout(resolve, POSIX_GRACEFUL_TIMEOUT_MS));
        if (isPidAlive(lock.pid)) {
          try {
            process.kill(-lock.pid, "SIGKILL");
          } catch {
            // already gone
          }
        }
      }

      stopPolling();
      ctx.ui.setWidget("factory", undefined);
      ctx.ui.notify("factory stopped", "info");
    },
  });

  pi.registerCommand("factory-tasks", {
    description: "List factory tasks grouped by status",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const cmd = buildListCommand();
      const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
      if (result.status !== 0) {
        ctx.ui.notify(`factory-tasks failed: ${result.stderr || "unknown error"}`, "error");
        return;
      }
      const lines = result.stdout.split(/\r?\n/).filter((line) => line.length > 0);
      ctx.ui.setWidget("factory-tasks", lines);
    },
  });
}
