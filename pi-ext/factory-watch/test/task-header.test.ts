import { describe, expect, test } from "vitest";
import { formatTaskHeader, parseTaskFrontmatter } from "../src/task-header.js";

const TASK_MD = `---
id: T-001
title: "Example: FlightController.goto reaches waypoint"
status: todo
dod:
  - "goto(x,y,z) moves pose to within 0.5m of target in the fake"
  - "unit test covers success and battery decrement"
---

Implement \`goto\` waypoint behavior on the fake and pybullet controllers.
`;

const TASK_SCALAR_DOD_MD = `---
id: T-002
title: Single-line task
status: done
dod: a single scalar criterion
---
body here
`;

const NOT_A_TASK_MD = "# Just a doc\n\nNo frontmatter here.\n";

describe("parseTaskFrontmatter", () => {
  test("parses a task with a list dod", () => {
    const parsed = parseTaskFrontmatter(TASK_MD);
    expect(parsed).toEqual({
      id: "T-001",
      title: "Example: FlightController.goto reaches waypoint",
      status: "todo",
      dod: [
        "goto(x,y,z) moves pose to within 0.5m of target in the fake",
        "unit test covers success and battery decrement",
      ],
      body: "Implement `goto` waypoint behavior on the fake and pybullet controllers.",
    });
  });

  test("parses a task with a scalar dod", () => {
    const parsed = parseTaskFrontmatter(TASK_SCALAR_DOD_MD);
    expect(parsed).toEqual({
      id: "T-002",
      title: "Single-line task",
      status: "done",
      dod: ["a single scalar criterion"],
      body: "body here",
    });
  });

  test("returns null when there's no frontmatter block", () => {
    expect(parseTaskFrontmatter(NOT_A_TASK_MD)).toBeNull();
  });

  test("returns null when a required field is missing", () => {
    const missingTitle = "---\nid: T-003\nstatus: todo\ndod: x\n---\nbody\n";
    expect(parseTaskFrontmatter(missingTitle)).toBeNull();
  });
});

describe("formatTaskHeader", () => {
  test("formats id, title, status, and dod as a clean header", () => {
    const parsed = parseTaskFrontmatter(TASK_MD)!;
    expect(formatTaskHeader(parsed)).toBe(
      "Task T-001 -- Example: FlightController.goto reaches waypoint\n" +
        "Status: todo\n" +
        "DoD:\n" +
        "- goto(x,y,z) moves pose to within 0.5m of target in the fake\n" +
        "- unit test covers success and battery decrement",
    );
  });
});
