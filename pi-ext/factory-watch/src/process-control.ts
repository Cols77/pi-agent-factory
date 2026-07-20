export interface Command {
  bin: string;
  args: string[];
}

export function buildRunCommand(provider: string, modelId: string, taskId?: string): Command {
  const args = [
    "run", "python", "-m", "factory.orchestrator", "run",
    "--provider", provider,
    "--model", modelId,
  ];
  if (taskId !== undefined) {
    args.push("--task", taskId);
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
