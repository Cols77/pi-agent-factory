export interface Command {
  bin: string;
  args: string[];
}

export function buildRunCommand(
  provider: string,
  modelId: string,
  taskId?: string,
  force = false,
): Command {
  const args = [
    "run", "python", "-m", "factory.orchestrator", "run",
    "--provider", provider,
    "--model", modelId,
  ];
  if (taskId !== undefined) {
    args.push("--task", taskId);
  }
  if (force) {
    args.push("--force");
  }
  return { bin: "uv", args };
}

export function buildListCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list"],
  };
}

export function buildListJsonCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list", "--json"],
  };
}

export function buildWindowsKillArgs(pid: number): string[] {
  return ["/PID", String(pid), "/T", "/F"];
}

// The `system` command is repointed (user ruling, 2026-08-08; design section
// 6.4): it now opens the docs browser directly on the `/system` route,
// instead of aliasing the generic docs-browser command. Pure and testable in
// isolation from ensureDocsServer's real listener, mirroring this file's
// existing buildXCommand convention -- `index.ts` supplies the running
// server's own `url` and only appends `/system`, never anything else
// (no query params: unlike the checkpoint-focused docs URL, a bundle/SR
// scope has no natural checkpoint to focus on, so the navigator opens on
// its own scope picker).
export function buildSystemNavigatorUrl(baseUrl: string): string {
  const url = new URL(baseUrl);
  url.pathname = "/system";
  url.search = "";
  return url.toString();
}
