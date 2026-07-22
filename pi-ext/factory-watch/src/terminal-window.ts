import { spawn } from "node:child_process";

export function spawnTerminalWindow(
  command: string,
  args: string[],
  options: { cwd: string },
  platform: NodeJS.Platform = process.platform,
): void {
  let child: ReturnType<typeof spawn>;
  if (platform === "win32") {
    const argList = args.map((a) => `'${a}'`).join(",");
    child = spawn(
      "powershell",
      ["-NoExit", "-Command", `Start-Process ${command} -ArgumentList ${argList}`],
      { cwd: options.cwd, detached: true, stdio: "ignore" },
    );
  } else if (platform === "darwin") {
    child = spawn("open", ["-a", "Terminal", command, ...args], {
      cwd: options.cwd, detached: true, stdio: "ignore",
    });
  } else {
    child = spawn("xterm", ["-e", command, ...args], {
      cwd: options.cwd, detached: true, stdio: "ignore",
    });
  }
  child.unref();
}
