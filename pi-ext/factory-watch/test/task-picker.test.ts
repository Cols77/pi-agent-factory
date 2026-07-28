import { describe, expect, test } from "vitest";
import { formatTaskOption, parseTaskIdFromOption, humanizeAge } from "../src/task-picker.js";

const NOW = new Date("2026-07-28T13:08:16Z");

describe("humanizeAge", () => {
  test("boundaries", () => {
    expect(humanizeAge(30)).toBe("just now");
    expect(humanizeAge(5 * 60)).toBe("5m ago");
    expect(humanizeAge(2 * 3600)).toBe("2h ago");
    expect(humanizeAge(3 * 86400)).toBe("3d ago");
  });
});

describe("formatTaskOption", () => {
  test("clean todo with no run history", () => {
    expect(formatTaskOption({ id: "T-036", title: "ScriptedPerception", status: "todo" }, NOW)).toBe(
      "T-036  ScriptedPerception",
    );
  });

  test("annotates a stopped task with node/state, age and reason", () => {
    const line = formatTaskOption({
      id: "T-037", title: "DirectiveExecutor", status: "todo",
      last_run: { node: "dev", state: "fail", outcome: "escalated", handoff: "unit tests still red", updated_at: "2026-07-28T11:08:16Z" },
    }, NOW);
    expect(line).toBe("T-037  DirectiveExecutor  — ⚠ stopped: dev fail (2h ago): unit tests still red");
  });

  test("omits the reason clause when handoff is null", () => {
    const line = formatTaskOption({
      id: "T-5", title: "X", status: "todo",
      last_run: { node: "review", state: "changes-requested", outcome: null, handoff: null, updated_at: "2026-07-28T13:07:17Z" },
    }, NOW);
    expect(line).toBe("T-5  X  — ⚠ stopped: review changes-requested (just now)");
  });

  test("annotates a done-outside-factory task when deliverables exist but no run history", () => {
    expect(formatTaskOption({ id: "T-29", title: "Foo", status: "todo", already_done: true }, NOW)).toBe(
      "T-29  Foo  — deliverables present (will route to review)",
    );
  });
});

describe("parseTaskIdFromOption", () => {
  test("recovers the id from an annotated option", () => {
    expect(parseTaskIdFromOption("T-037  DirectiveExecutor  — ⚠ stopped: dev fail (2h ago): unit tests still red")).toBe("T-037");
  });
});
