import { expect, test } from "vitest";
import { formatPresent } from "../src/eng-context-tool-format.js";
import type { PresentResult } from "../src/system-cli.js";

function basePresent(): PresentResult {
  return {
    artifact: "sr:SR-001",
    focus: null,
    level: "INSPECT",
    intent: { artifact: "sr:SR-001", focus: null },
    resolution: "resolved",
    adapter: null,
    target: null,
    note: "",
  };
}

test("formats a no-policy-scope note", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: null,
    obligations_note: "no policy scope for this artifact kind",
  });
  expect(rendered).toContain("obligations: no policy scope for this artifact kind");
});

test("formats an unresolved obligation error", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [],
    obligations_error: "profile cannot be resolved",
  });
  expect(rendered).toContain("obligations: unresolved (profile cannot be resolved)");
});

test("formats explanations in the received obligation order", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:human",
        scope_ref: "sr:SR-001",
        kind: "human_review",
        requiredness: "required",
        reason: "review the result",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: null,
        why: "the profile requires a human review",
      },
      {
        id: "ob:ci",
        scope_ref: "project",
        kind: "ci_verification",
        requiredness: "blocking",
        reason: "run CI",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: null,
        why: null,
      },
    ],
  });
  expect(rendered.indexOf("[human_review] required")).toBeLessThan(
    rendered.indexOf("[ci_verification] blocking"),
  );
  expect(rendered).toContain("why: the profile requires a human review");
});

test("renders resolve_cmd when present", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:ci",
        scope_ref: "project",
        kind: "ci_verification",
        requiredness: "blocking",
        reason: "run CI",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: ["pi ci run --scope project"],
        why: null,
      },
    ],
  });
  expect(rendered).toContain("resolve: pi ci run --scope project");
});

test("joins a multi-command resolve_cmd array into one readable line", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:ci",
        scope_ref: "project",
        kind: "ci_verification",
        requiredness: "blocking",
        reason: "run CI",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: ["pytest -m unit -q", "ruff check ."],
        why: null,
      },
    ],
  });
  expect(rendered).toContain("resolve: pytest -m unit -q && ruff check .");
});

test("omits resolve_cmd when it is an empty array", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:ci",
        scope_ref: "project",
        kind: "ci_verification",
        requiredness: "blocking",
        reason: "run CI",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: [],
        why: null,
      },
    ],
  });
  expect(rendered).not.toContain("resolve:");
});

test("omits resolve_cmd when null", () => {
  const rendered = formatPresent({
    ...basePresent(),
    obligations: [
      {
        id: "ob:human",
        scope_ref: "sr:SR-001",
        kind: "human_review",
        requiredness: "required",
        reason: "review the result",
        source_policy: "prototype",
        state: "open",
        resolve_cmd: null,
        why: null,
      },
    ],
  });
  expect(rendered).not.toContain("resolve:");
});

test("marks malformed optional obligation payloads without throwing", () => {
  const malformedArray = { ...basePresent(), obligations: "not-an-array" } as unknown as PresentResult;
  expect(() => formatPresent(malformedArray)).not.toThrow();
  expect(formatPresent(malformedArray)).toContain("obligations: unavailable (malformed payload)");

  const malformedEntry = {
    ...basePresent(),
    obligations: [{ kind: "ci_verification" }],
  } as unknown as PresentResult;
  expect(() => formatPresent(malformedEntry)).not.toThrow();
  expect(formatPresent(malformedEntry)).toContain("obligations: unavailable (malformed payload)");
});
