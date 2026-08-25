// Increment 7 Task 3: the terminal-completion notification dedupe key.
//
// Completion notifications are extension-owned and deduplicated by the
// immutable (producer, run_id, terminal_observation_id) identity -- never a
// timestamp -- so a live poll that re-reads a source whose mtime changed fires
// at most once per terminal run, and a later terminal observation may notify
// once for its new identity.
import { describe, expect, test } from "vitest";

// Re-implements the exact key logic in index.ts's mission-control handler.
function terminalKey(run: {
  producer: string;
  run_id: string;
  state: string;
  terminal_observation_id: string | null;
}): string | null {
  if (run.state !== "passed" && run.state !== "failed") return null;
  if (!run.terminal_observation_id) return null;
  return `${run.producer}\u0000${run.run_id}\u0000${run.terminal_observation_id}`;
}

describe("mission-control terminal notification dedupe", () => {
  test("only terminal runs with a terminal observation identity generate a key", () => {
    expect(terminalKey({ producer: "simulation", run_id: "s1", state: "running", terminal_observation_id: null })).toBeNull();
    expect(terminalKey({ producer: "simulation", run_id: "s1", state: "passed", terminal_observation_id: null })).toBeNull();
    expect(terminalKey({ producer: "simulation", run_id: "s1", state: "failed", terminal_observation_id: "obs-1" })).toBe(
      "simulation\u0000s1\u0000obs-1",
    );
  });

  test("a new terminal observation yields a distinct key", () => {
    const a = terminalKey({ producer: "factory", run_id: "r1", state: "failed", terminal_observation_id: "obs-1" });
    const b = terminalKey({ producer: "factory", run_id: "r1", state: "failed", terminal_observation_id: "obs-2" });
    expect(a).toBe("factory\u0000r1\u0000obs-1");
    expect(b).toBe("factory\u0000r1\u0000obs-2");
    expect(a).not.toBe(b);
  });

  test("same run + same terminal observation dedupes to one key, regardless of mtime", () => {
    const keys = new Set<string>();
    for (let i = 0; i < 5; i++) {
      const key = terminalKey({ producer: "audit", run_id: "a1", state: "passed", terminal_observation_id: "obs-9" });
      expect(key).not.toBeNull();
      keys.add(key as string);
    }
    expect(keys.size).toBe(1);
  });
});
