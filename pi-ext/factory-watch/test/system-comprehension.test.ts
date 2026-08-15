import { JSDOM } from "jsdom";
import { beforeEach, expect, test, vi } from "vitest";
import {
  boundedList,
  closeOpenCard,
  ensureCardController,
  infoCard,
  refCardFields,
  refChip,
} from "../src/system-comprehension.js";

const T060 = {
  ref: "task:T-060", id: "T-060", kind: "task",
  title: "Wire the safety governor into the planner loop",
  description: null, description_source: null, deferral_reason: null,
  status: "done", relations: { satisfies: ["sr:SR-121"] },
  path: "tasks/T-060.md", scope_href: "/system?scope=task%3AT-060",
};

const SR121 = {
  ref: "sr:SR-121", id: "SR-121", kind: "sr",
  title: "Battery-aware return",
  description: "The rover must return to base before battery falls below 15%.",
  description_source: "statement", deferral_reason: null,
  status: null, relations: {},
  path: "requirements/SR-121.md", scope_href: null,
};

beforeEach(() => {
  const dom = new JSDOM("<!doctype html><body></body>", { pretendToBeVisual: true });
  (globalThis as any).window = dom.window;
  (globalThis as any).document = dom.window.document;
  (globalThis as any).LABELS = { "task:T-060": T060, "sr:SR-121": SR121 };
  (globalThis as any).ALIASES = {
    "T-060": "task:T-060", "task:T-060": "task:T-060",
    "SR-121": "sr:SR-121", "sr:SR-121": "sr:SR-121",
  };
});

test("a known ref renders id and title inline", () => {
  const el = refChip("task:T-060");
  expect(el.querySelector(".chip-id")?.textContent).toBe("T-060");
  expect(el.querySelector(".chip-title")?.textContent).toBe(
    "Wire the safety governor into the planner loop",
  );
});

test("a bare id resolves through the alias map", () => {
  expect(refChip("T-060").querySelector(".chip-title")?.textContent).toBe(
    "Wire the safety governor into the planner loop",
  );
});

test("an unknown ref says so and is never guessed", () => {
  const el = refChip("T-999");
  expect(el.textContent).toContain("T-999");
  expect(el.textContent).toContain("not in the label index");
  expect(el.className).toContain("is-absent");
});

test("an unresolved chip carries no ref dataset and is not focusable", () => {
  const el = refChip("T-999");
  expect(el.dataset.ref).toBeUndefined();
  expect(el.tabIndex).not.toBe(0);
});

test("bounded list shows five rows and hides the rest behind a disclosure", () => {
  const refs = Array.from({ length: 15 }, (_, i) => `SR-${i}`);
  const el = boundedList(refs);
  expect(el.querySelectorAll(":scope > .ref-chip").length).toBe(5);
  const details = el.querySelector("details");
  expect(details?.querySelector("summary")?.textContent).toBe("+ 10 more");
});

test("bounded list under the limit renders no disclosure", () => {
  expect(boundedList(["T-060"]).querySelector("details")).toBeNull();
});

test("refCardFields orders id/kind/status, title, description, from, path, open", () => {
  const fields = refCardFields(SR121);
  expect(fields.map((f) => f.className)).toEqual([
    "info-card-meta",
    "info-card-title",
    "info-card-description",
    "info-card-from",
    "info-card-path",
  ]);
  expect(fields[0]?.text).toBe("SR-121 · sr");
  expect(fields[3]?.text).toBe("from: statement");
});

test("refCardFields never blanks a missing description or a missing Open link", () => {
  const fields = refCardFields(T060);
  const description = fields.find((f) => f.className?.includes("info-card-description"));
  expect(description?.text).toBe("No description recorded.");
  expect(description?.className).toContain("info-card-empty");
  // T-060 has a status and a scope_href, so both the status and Open fields appear.
  expect(fields.map((f) => f.className)).toContain("info-card-open");
  expect(fields.find((f) => f.className === "info-card-meta")?.text).toBe("T-060 · task · done");
});

test("infoCard renders each field as a line, with href fields as links", () => {
  const card = infoCard(refCardFields(SR121));
  expect(card.className).toBe("info-card");
  expect(card.querySelectorAll(".info-card-line").length).toBe(5);
  const meta = card.querySelector(".info-card-meta");
  expect(meta?.textContent).toBe("SR-121 · sr");
});

test("infoCard renders an Open link as an anchor to scope_href", () => {
  const card = infoCard(refCardFields(T060));
  const open = card.querySelector(".info-card-open a") as HTMLAnchorElement | null;
  expect(open?.getAttribute("href")).toBe("/system?scope=task%3AT-060");
  expect(open?.textContent).toBe("Open");
});

test("hovering a chip opens its card after the delay, not before", () => {
  vi.useFakeTimers();
  try {
    const chip = refChip("T-060");
    document.body.appendChild(chip);
    chip.dispatchEvent(new (window as any).MouseEvent("mouseover", { bubbles: true }));
    expect(document.querySelector(".info-card")).toBeNull();
    vi.advanceTimersByTime(119);
    expect(document.querySelector(".info-card")).toBeNull();
    vi.advanceTimersByTime(1);
    expect(document.querySelector(".info-card")).not.toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

test("focusing a chip via keyboard opens its card immediately", () => {
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
});

test("clicking a chip toggles the card open then closed", () => {
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelector(".info-card")).toBeNull();
});

test("only one card is open at a time", () => {
  const a = refChip("T-060");
  const b = refChip("SR-121");
  document.body.appendChild(a);
  document.body.appendChild(b);
  a.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelectorAll(".info-card").length).toBe(1);
  b.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelectorAll(".info-card").length).toBe(1);
  expect(document.querySelector(".info-card")?.textContent).toContain("Battery-aware return");
});

test("Escape closes the open card and returns focus to the trigger", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  chip.focus();
  expect(document.querySelector(".info-card")).not.toBeNull();
  document.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  expect(document.querySelector(".info-card")).toBeNull();
  expect(document.activeElement).toBe(chip);
});

test("a keydown outside the card (e.g. Alt+2 tab navigation) closes the open card", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
  document.dispatchEvent(
    new (window as any).KeyboardEvent("keydown", { key: "2", altKey: true, bubbles: true }),
  );
  expect(document.querySelector(".info-card")).toBeNull();
});

test("a keydown originating inside the open card does not close it", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  const card = document.querySelector(".info-card") as HTMLElement | null;
  expect(card).not.toBeNull();
  card!.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
});

test("a keydown that closes the card outside it does not steal focus", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  chip.focus();
  const other = document.createElement("input");
  document.body.appendChild(other);
  other.focus();
  other.dispatchEvent(
    new (window as any).KeyboardEvent("keydown", { key: "2", altKey: true, bubbles: true }),
  );
  expect(document.querySelector(".info-card")).toBeNull();
  expect(document.activeElement).toBe(other);
});

test("aria-expanded flips to true when the card opens and back to false when it closes", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  expect(chip.getAttribute("aria-expanded")).toBe("false");
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  chip.focus();
  expect(chip.getAttribute("aria-expanded")).toBe("true");
  document.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  expect(chip.getAttribute("aria-expanded")).toBe("false");
});

test("closeOpenCard closes the currently open card without moving focus", () => {
  ensureCardController();
  const chip = refChip("T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
  closeOpenCard();
  expect(document.querySelector(".info-card")).toBeNull();
  expect(chip.getAttribute("aria-expanded")).toBe("false");
});
