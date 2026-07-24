import { describe, expect, test, vi } from "vitest";
import { ConfirmPrompt } from "../src/confirm-prompt.ts";

describe("ConfirmPrompt", () => {
  test("renders the title and message", () => {
    const prompt = new ConfirmPrompt("Approve task?", "T-001: mark this task done?", () => {});
    const lines = prompt.render(80).join("\n");
    expect(lines).toContain("Approve task?");
    expect(lines).toContain("T-001: mark this task done?");
  });

  test("'y' confirms", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("y");
    expect(onDecide).toHaveBeenCalledWith(true);
  });

  test("Enter confirms", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("\r");
    expect(onDecide).toHaveBeenCalledWith(true);
  });

  test("'n' cancels", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("n");
    expect(onDecide).toHaveBeenCalledWith(false);
  });

  test("Escape cancels", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("\x1b");
    expect(onDecide).toHaveBeenCalledWith(false);
  });

  test("other keys are ignored", () => {
    const onDecide = vi.fn();
    new ConfirmPrompt("t", "m", onDecide).handleInput("x");
    expect(onDecide).not.toHaveBeenCalled();
  });

  test("invalidate is a safe no-op", () => {
    const prompt = new ConfirmPrompt("t", "m", () => {});
    expect(() => prompt.invalidate()).not.toThrow();
  });
});
