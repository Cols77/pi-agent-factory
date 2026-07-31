import { spawn } from "node:child_process";

export function spawnTerminalWindow(
  command: string,
  args: string[],
  options: { cwd: string },
  platform: NodeJS.Platform = process.platform,
): void {
  let child: ReturnType<typeof spawn>;
  if (platform === "win32") {
    // Open a brand-new console window via cmd's `start`. This is the only
    // approach that works when the parent has no usable console of its own --
    // which is exactly our case: the pi extension host owns pi's TUI, so the
    // process calling this is effectively console-less. From such a parent,
    // `powershell Start-Process <console-app>` creates a new console the
    // child immediately exits from (the window flashes and dies); `start`
    // allocates a proper new console the app runs in normally. The empty ""
    // is start's window-title argument (required first token, otherwise start
    // treats a later quoted path as the title and never launches the app).
    child = spawn("cmd", ["/c", "start", "", command, ...args], {
      cwd: options.cwd, detached: true, stdio: "ignore",
    });
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
