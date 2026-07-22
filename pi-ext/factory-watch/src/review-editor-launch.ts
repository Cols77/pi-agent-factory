const KNOWN_TERMINAL_EDITORS = ["vim", "nvim", "vi", "nano", "emacs -nw"];

export type EditorLaunchPlan =
  | { ok: true; useTmux: boolean; command: string; args: string[] }
  | { ok: false; error: string };

function splitCommand(spec: string): { command: string; args: string[] } {
  const parts = spec.trim().split(/\s+/);
  return { command: parts[0]!, args: parts.slice(1) };
}

export function resolveEditorLaunch(
  env: NodeJS.ProcessEnv,
  hasCodeOnPath: boolean,
  platform: NodeJS.Platform = process.platform,
): EditorLaunchPlan {
  const spec = env.VISUAL ?? env.EDITOR;
  const useTmux = Boolean(env.TMUX);

  if (spec !== undefined) {
    const { command, args } = splitCommand(spec);
    const isKnownTerminalEditor = KNOWN_TERMINAL_EDITORS.some((known) => spec.trim() === known);
    if (isKnownTerminalEditor && !useTmux) {
      return {
        ok: false,
        error: `edit requires a GUI editor -- ${command} can't safely share pi's terminal (set $VISUAL, or use tmux)`,
      };
    }
    return { ok: true, useTmux: isKnownTerminalEditor && useTmux, command, args };
  }

  if (hasCodeOnPath) {
    return { ok: true, useTmux: false, command: "code", args: ["-w"] };
  }
  if (platform === "win32") {
    return { ok: true, useTmux: false, command: "notepad", args: [] };
  }
  return { ok: false, error: "edit requires a GUI editor -- set $VISUAL, or use tmux (see review UI docs)" };
}
