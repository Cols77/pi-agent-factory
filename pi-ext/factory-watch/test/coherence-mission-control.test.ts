// Increment 7 Task 5 (cross-layer fixture): the mission-control run-status
// protocol. `coherence.runs.transport.serialize_run_statuses` emits
// `{"runs": [...]}` rows DISCRIMINATED by `producer` (factory | audit |
// measurement | simulation | experiment), each carrying a nullable
// `resume_cmd` (the native-run resume) and a distinct
// `blocking_obligation_resolve_cmd` (an array -- the obligation's resolve
// tuple). The dashboard must:
//   * render producer-specific rows and the obligation's resolve-command items
//     (each array item as its own command item);
//   * render a resume control ONLY when `resume_cmd` is a non-empty string;
//   * when `resume_cmd` is null, retain obligation/resolve UI but emit NO
//     resume label, no control, and never "undefined", an empty command, or a
//     stale previous resume value.
// This mirrors the python contract in
// src/coherence/runs/transport.py: a None resume_cmd is emitted as JSON null
// (never omitted) and blocking_obligation_resolve_cmd is preserved as an
// array, never joined into a string.
import { describe, expect, test } from "vitest";
import { RunStatusDashboard } from "../src/mission-control-dashboard.js";
import {
  parseRunStatuses,
  formatRunStatusLines,
  obligationResolveCommands,
  resumeCommand,
  producerLabel,
} from "../src/status-format.js";
import type { RunStatus, RunStatusesPayload } from "../src/status-format.js";

function runRow(overrides: Partial<RunStatus>): RunStatus {
  return {
    producer: "simulation",
    run_id: "sim-1",
    state: "failed",
    observation_ref: "obs:sim-1",
    artifacts: [],
    resume_cmd: null,
    updated_at: "2026-08-25T00:00:00Z",
    diagnostics: [],
    terminal_observation_id: null,
    blocking_obligation: null,
    blocking_obligation_resolve_cmd: null,
    rerun_allowed: false,
    ...overrides,
  };
}

function rendered(payload: RunStatusesPayload | null, width = 120): string[] {
  return new RunStatusDashboard(payload, () => {}).render(width);
}

function joined(payload: RunStatusesPayload | null): string {
  return rendered(payload).join("\n");
}

describe("parseRunStatuses", () => {
  test("consumes the canonical {'runs': [...]} payload shape", () => {
    const payload = { runs: [runRow({ producer: "factory", resume_cmd: "python -m factory" })] };
    const parsed = parseRunStatuses(JSON.stringify(payload));
    expect(parsed).toEqual(payload);
    expect(parsed?.runs[0]?.producer).toBe("factory");
  });

  test("returns null for malformed JSON or a non-runs object", () => {
    expect(parseRunStatuses("not json")).toBeNull();
    expect(parseRunStatuses("42")).toBeNull();
    expect(parseRunStatuses('{"foo": 1}')).toBeNull();
  });
});

describe("producer-aware status", () => {
  test("formatRunStatusLines anchors each row by its producer", () => {
    const payload: RunStatusesPayload = {
      runs: [
        runRow({
          producer: "audit",
          run_id: "aud-1",
          state: "running",
          resume_cmd: "python -m coherence audit run",
          blocking_obligation: "SR-X:verification_result",
          blocking_obligation_resolve_cmd: ["c1", "c2"],
          rerun_allowed: true,
        }),
      ],
    };
    const lines = formatRunStatusLines(payload);
    expect(lines[0]).toContain("[audit]");
    expect(lines.some((l) => l.includes("resume: python -m coherence audit run"))).toBe(true);
    expect(lines.some((l) => l.includes("obligation: SR-X:verification_result"))).toBe(true);
    expect(lines.some((l) => l.includes("resolve: c1"))).toBe(true);
    expect(lines.some((l) => l.includes("resolve: c2"))).toBe(true);
  });

  test("producerLabel returns the producer name for every source", () => {
    for (const p of ["factory", "audit", "measurement", "simulation", "experiment"]) {
      expect(producerLabel(p)).toBe(p);
    }
  });
});

describe("resume vs. obligation resolve command (Task 5)", () => {
  const OBLIGATION = "SR-X:verification_result";

  test("renders producer row, obligation, resolve items, and the non-empty resume command together", () => {
    const payload: RunStatusesPayload = {
      runs: [
        runRow({
          producer: "simulation",
          run_id: "sim-1",
          state: "failed",
          resume_cmd: "python -m something",
          blocking_obligation: OBLIGATION,
          blocking_obligation_resolve_cmd: ["c1", "c2"],
          rerun_allowed: true,
        }),
      ],
    };
    expect(resumeCommand(payload.runs[0]!)).toBe("python -m something");
    expect(obligationResolveCommands(payload.runs[0]!)).toEqual(["c1", "c2"]);

    const lines = rendered(payload);
    const text = lines.join("\n");
    // source-specific row label discriminates by producer
    expect(lines.some((l) => l.includes("[simulation") && l.includes("sim-1"))).toBe(true);
    // obligation + resolve items (each item its own command item)
    expect(text).toContain(`obligation: ${OBLIGATION}`);
    expect(text).toContain("resolve: c1");
    expect(text).toContain("resolve: c2");
    // non-empty resume command rendered
    expect(text).toContain("resume: python -m something");
    expect(text).toContain("rerun allowed");
  });

  test("re-render with resume_cmd null keeps obligation/resolve UI but drops ALL resume UI (no undefined/empty/stale)", () => {
    const dash = new RunStatusDashboard(
      {
        runs: [
          runRow({
            producer: "measurement",
            run_id: "meas-1",
            state: "failed",
            resume_cmd: "python -m measure",
            blocking_obligation: OBLIGATION,
            blocking_obligation_resolve_cmd: ["c1", "c2"],
            rerun_allowed: true,
          }),
        ],
      },
      () => {},
    );

    const before = dash.render(120).join("\n");
    expect(before).toContain("resume: python -m measure");

    // Re-render with resume_cmd -> null, same resolve array still present.
    dash.update({
      runs: [
        runRow({
          producer: "measurement",
          run_id: "meas-1",
          state: "failed",
          resume_cmd: null,
          blocking_obligation: OBLIGATION,
          blocking_obligation_resolve_cmd: ["c1", "c2"],
          rerun_allowed: true,
        }),
      ],
    });
    const after = dash.render(120);
    const text = after.join("\n");

    // Obligation / resolve UI retained.
    expect(text).toContain(`obligation: ${OBLIGATION}`);
    expect(text).toContain("resolve: c1");
    expect(text).toContain("resolve: c2");

    // NO resume label, no control, and none of the forbidden leaks.
    expect(text).not.toContain("resume:");
    expect(text).not.toContain("python -m measure"); // no stale previous value
    expect(text).not.toContain("undefined");
    // No empty resume command line ("    resume: " as a bare label).
    expect(after.every((l) => l.trim() !== "resume:" && !l.includes("resume: "))).toBe(true);
  });

  test("both resume_cmd and resolve array may be present together and stay distinct", () => {
    const payload: RunStatusesPayload = {
      runs: [
        runRow({
          blocking_obligation: OBLIGATION,
          blocking_obligation_resolve_cmd: ["coherence audit run", "--dry-run"],
          resume_cmd: "python -m simulation run --resume",
        }),
      ],
    };
    const text = joined(payload);
    expect(text).toContain("resume: python -m simulation run --resume");
    // each resolve array item rendered separately, never shell-joined
    expect(text).toContain("resolve: coherence audit run");
    expect(text).toContain("resolve: --dry-run");
    expect(text).not.toContain("resolve: coherence audit run --dry-run");
  });

  test("a resume_cmd of only whitespace is treated as absent", () => {
    const payload: RunStatusesPayload = {
      runs: [runRow({ resume_cmd: "   " })],
    };
    const text = joined(payload);
    expect(resumeCommand(payload.runs[0]!)).toBeNull();
    expect(text).not.toContain("resume:");
  });
});
