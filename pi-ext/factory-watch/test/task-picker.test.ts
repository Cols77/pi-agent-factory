import { describe, expect, test } from "vitest";
import { formatTaskOption, parseTaskIdFromOption } from "../src/task-picker.js";

describe("formatTaskOption", () => {
  test("formats id and title as a single picker line", () => {
    expect(formatTaskOption({ id: "T-003", title: "Add battery-aware RTB", status: "todo" })).toBe(
      "T-003  Add battery-aware RTB",
    );
  });
});

describe("parseTaskIdFromOption", () => {
  test("recovers the id from a formatted option", () => {
    expect(parseTaskIdFromOption("T-003  Add battery-aware RTB")).toBe("T-003");
  });

  test("handles a title with no spaces", () => {
    expect(parseTaskIdFromOption("T-003  X")).toBe("T-003");
  });
});
