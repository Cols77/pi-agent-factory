import { spawn } from "node:child_process";
import { describe, expect, test, vi } from "vitest";
import { spawnTerminalWindow } from "../src/terminal-window.js";

vi.mock("node:child_process", () => ({ spawn: vi.fn(() => ({ unref: vi.fn() })) }));

describe("spawnTerminalWindow", () => {
  test("on win32, opens a new console window via cmd `start` with the command and args", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts", "--cwd", "/repo"], { cwd: "/repo" }, "win32");
    expect(spawn).toHaveBeenCalledWith(
      "cmd",
      ["/c", "start", "", "node", "dashboard.ts", "--cwd", "/repo"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("on win32 with empty args, still passes the start title token and command", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", [], { cwd: "/repo" }, "win32");
    expect(spawn).toHaveBeenCalledWith(
      "cmd",
      ["/c", "start", "", "node"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("on darwin, uses `open -a Terminal`", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "darwin");
    expect(spawn).toHaveBeenCalledWith(
      "open", ["-a", "Terminal", "node", "dashboard.ts"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("on linux, uses xterm -e", () => {
    vi.mocked(spawn).mockClear();
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "linux");
    expect(spawn).toHaveBeenCalledWith(
      "xterm", ["-e", "node", "dashboard.ts"],
      { cwd: "/repo", detached: true, stdio: "ignore" },
    );
  });

  test("unrefs the spawned child so it doesn't keep the parent process alive", () => {
    const unref = vi.fn();
    vi.mocked(spawn).mockReturnValue({ unref } as unknown as ReturnType<typeof spawn>);
    spawnTerminalWindow("node", ["dashboard.ts"], { cwd: "/repo" }, "win32");
    expect(unref).toHaveBeenCalled();
  });
});
