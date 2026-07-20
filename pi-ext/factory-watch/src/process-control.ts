export interface Command {
  bin: string;
  args: string[];
}

export function buildRunCommand(provider: string, modelId: string): Command {
  return {
    bin: "uv",
    args: [
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", provider,
      "--model", modelId,
    ],
  };
}

export function buildListCommand(): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator", "list"],
  };
}

export function buildWindowsKillArgs(pid: number): string[] {
  return ["/PID", String(pid), "/T", "/F"];
}
