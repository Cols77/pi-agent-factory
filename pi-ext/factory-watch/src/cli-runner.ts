import { spawn, spawnSync } from "node:child_process";

// Shared subprocess + JSON shim for every `uv run python -m factory.<x> ...`
// CLI this extension calls. Holds process/JSON mechanics only -- no
// freshness, ranking, or provenance logic. Callers (trace-cli.ts,
// system-cli.ts) own their own command construction and any renaming of
// the `value` field to something domain-specific.
export type CliResult<T> = { ok: true; value: T } | { ok: false; error: string };

// Derives a short, stable label for error messages from a `uv run python -m
// <module> ...`-shaped argv, e.g. ["run","python","-m","factory.trace",...]
// yields "factory trace". Purely mechanical (the invoked module name with
// dots turned to spaces) -- it names which command failed, it does not
// interpret what the module does.
function commandLabel(args: string[]): string {
  const moduleIndex = args.indexOf("-m");
  const module = moduleIndex >= 0 ? args[moduleIndex + 1] : undefined;
  return module !== undefined ? module.replace(/\./g, " ") : args.join(" ");
}

function launchFailure(error: unknown): CliResult<never> {
  const message =
    typeof error === "object" && error !== null && "message" in error
      ? (error as { message?: unknown }).message
      : undefined;
  return { ok: false, error: String(message ?? error) };
}

function parseCliResult<T>(args: string[], status: number | null, stdout: string, stderr: string): CliResult<T> {
  const exitStatus = status ?? -1;
  if (exitStatus !== 0) {
    return {
      ok: false,
      error: `${commandLabel(args)} exited ${exitStatus}: ${stderr.trim()}`,
    };
  }
  try {
    return { ok: true, value: JSON.parse(stdout) as T };
  } catch (err) {
    return { ok: false, error: `could not parse ${commandLabel(args)} output: ${String(err)}` };
  }
}

export function runJsonCli<T>(cwd: string, bin: string, args: string[]): CliResult<T> {
  const result = spawnSync(bin, args, {
    cwd,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    return launchFailure(result.error);
  }
  return parseCliResult(args, result.status, result.stdout ?? "", result.stderr ?? "");
}

const MAX_OUTPUT_BYTES = 64 * 1024 * 1024;

export function runJsonCliAsync<T>(cwd: string, bin: string, args: string[]): Promise<CliResult<T>> {
  return new Promise((resolveResult) => {
    let settled = false;
    let stdoutSize = 0;
    let stderrSize = 0;
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];

    const settle = (result: CliResult<T>): void => {
      if (settled) return;
      settled = true;
      resolveResult(result);
    };
    const capture = (stream: "stdout" | "stderr", chunk: Buffer | string): void => {
      if (settled) return;
      const data = typeof chunk === "string" ? Buffer.from(chunk, "utf-8") : chunk;
      const size = stream === "stdout" ? stdoutSize : stderrSize;
      if (size + data.length > MAX_OUTPUT_BYTES) {
        settle({
          ok: false,
          error: `${commandLabel(args)} ${stream} exceeded ${MAX_OUTPUT_BYTES} byte output limit`,
        });
        return;
      }
      if (stream === "stdout") {
        stdoutSize += data.length;
        stdout.push(data);
      } else {
        stderrSize += data.length;
        stderr.push(data);
      }
    };

    try {
      const child = spawn(bin, args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
      child.stdout?.on("data", (chunk: Buffer | string) => capture("stdout", chunk));
      child.stderr?.on("data", (chunk: Buffer | string) => capture("stderr", chunk));
      child.once("error", (error) => settle(launchFailure(error)));
      child.once("close", (status) => {
        settle(parseCliResult(args, status, Buffer.concat(stdout).toString("utf-8"), Buffer.concat(stderr).toString("utf-8")));
      });
    } catch (error) {
      settle(launchFailure(error));
    }
  });
}
