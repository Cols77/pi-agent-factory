import { spawnSync } from "node:child_process";

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

export function runJsonCli<T>(cwd: string, bin: string, args: string[]): CliResult<T> {
  const result = spawnSync(bin, args, {
    cwd,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    return { ok: false, error: String(result.error.message ?? result.error) };
  }
  const status = result.status ?? -1;
  if (status !== 0) {
    return {
      ok: false,
      error: `${commandLabel(args)} exited ${status}: ${(result.stderr ?? "").trim()}`,
    };
  }
  try {
    return { ok: true, value: JSON.parse(result.stdout) as T };
  } catch (err) {
    return { ok: false, error: `could not parse ${commandLabel(args)} output: ${String(err)}` };
  }
}
