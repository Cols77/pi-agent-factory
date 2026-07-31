import { describe, expect, test } from "vitest";
import { resolveEditorLaunch } from "../src/review-editor-launch.js";

describe("resolveEditorLaunch", () => {
  test("uses $VISUAL when it resolves to a GUI editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "code -w" }, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["-w"] });
  });

  test("falls back to $EDITOR when $VISUAL is unset", () => {
    const result = resolveEditorLaunch({ EDITOR: "code --wait" }, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["--wait"] });
  });

  test("rejects a known terminal editor in $VISUAL", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- vim can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });

  test("rejects emacs -nw specifically (not plain emacs)", () => {
    expect(resolveEditorLaunch({ VISUAL: "emacs -nw" }, true).ok).toBe(false);
  });

  test("falls back to code -w when neither env var is set and code is on PATH", () => {
    const result = resolveEditorLaunch({}, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "code", args: ["-w"] });
  });

  test("falls back to notepad on win32 when code is not on PATH", () => {
    const result = resolveEditorLaunch({}, false, "win32");
    expect(result).toEqual({ ok: true, useTmux: false, command: "notepad", args: [] });
  });

  test("fails when no GUI editor can be resolved on a non-Windows platform", () => {
    const result = resolveEditorLaunch({}, false, "linux");
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- set $VISUAL, or use tmux (see review UI docs)",
    });
  });

  test("uses the tmux path when $TMUX is set, even for a terminal editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim", TMUX: "/tmp/tmux-1000/default,1234,0" }, true);
    expect(result).toEqual({ ok: true, useTmux: true, command: "vim", args: [] });
  });

  test("rejects terminal editors invoked with arguments (vim with config)", () => {
    const result = resolveEditorLaunch({ VISUAL: "vim -u ~/.vimrc" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- vim can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });

  test("rejects terminal editors invoked with arguments (nvim with line number)", () => {
    const result = resolveEditorLaunch({ VISUAL: "nvim +42 file.txt" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- nvim can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });

  test("accepts plain emacs (without -nw) as a GUI editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "emacs" }, true);
    expect(result).toEqual({ ok: true, useTmux: false, command: "emacs", args: [] });
  });

  test("still rejects emacs -nw as a terminal editor", () => {
    const result = resolveEditorLaunch({ VISUAL: "emacs -nw" }, true);
    expect(result).toEqual({
      ok: false,
      error: "edit requires a GUI editor -- emacs can't safely share pi's terminal (set $VISUAL, or use tmux)",
    });
  });
});
