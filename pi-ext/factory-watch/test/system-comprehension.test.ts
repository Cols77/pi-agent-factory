import { JSDOM } from "jsdom";
import { beforeEach, expect, test, vi } from "vitest";
import {
  boundedList,
  closeOpenCard,
  definitionCardFields,
  definitionTrigger,
  ensureCardController,
  glossFor,
  infoCard,
  refCardFields,
  refChip,
  renderVocabularyPanel,
} from "../src/system-comprehension.js";
import { badge, badgeSpan, freshnessBadge } from "../src/system-renderers.js";

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

const RECORDED_TERM = {
  term: "recorded", group: "claim-kind", label: "recorded",
  gloss: "straight from a file, not inferred",
  definition: "Copied verbatim out of an artifact file.",
  siblings: ["derived"], computed_by: ["src/factory/system/queries.py"],
};

const FRESH_TERM = {
  term: "fresh", group: "freshness", label: "fresh",
  gloss: "cited inputs still match what is recorded now",
  definition: "Every dependency still matches its recorded current state.",
  siblings: ["stale", "degraded", "n/a"], computed_by: ["src/factory/system/models.py"],
};

beforeEach(() => {
  const dom = new JSDOM("<!doctype html><body><div id=\"vocabularyGroups\"></div></body>", {
    pretendToBeVisual: true,
  });
  (globalThis as any).window = dom.window;
  (globalThis as any).document = dom.window.document;
  (globalThis as any).LABELS = { "task:T-060": T060, "sr:SR-121": SR121 };
  (globalThis as any).ALIASES = {
    "T-060": "task:T-060", "task:T-060": "task:T-060",
    "SR-121": "sr:SR-121", "sr:SR-121": "sr:SR-121",
  };
  (globalThis as any).VOCABULARY = { terms: {} };
  // badge()/freshnessBadge() (system-renderers.ts) and renderVocabularyPanel()
  // reference these as free variables, exactly as they do in the assembled
  // page (system-shell.ts's clientSource()) -- wiring them onto globalThis
  // here reproduces that same page-scope resolution for a unit test.
  (globalThis as any).badgeSpan = badgeSpan;
  (globalThis as any).glossFor = glossFor;
  (globalThis as any).definitionTrigger = definitionTrigger;
  (globalThis as any).clear = (el: HTMLElement) => { el.innerHTML = ""; };
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

// --- Task 11: badge glosses, definition cards and the vocabulary panel ---

test("a badge carries its gloss inline and a definition trigger", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM } };
  const el = badge("recorded", "kind-recorded");
  expect(el.textContent).toContain("recorded");
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".gloss")?.textContent)
    .toBe("straight from a file, not inferred");
  expect(wrap.querySelector(".info-trigger")?.getAttribute("aria-label"))
    .toBe("What does recorded mean?");
});

test("the badge's own contract word is untouched by the gloss wrap", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM } };
  const el = badge("recorded", "kind-recorded");
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".badge")?.textContent).toBe("recorded");
  expect(wrap.querySelector(".badge")?.className).toBe("badge kind-recorded");
});

test("an unknown term renders the badge with no gloss and no trigger", () => {
  (globalThis as any).VOCABULARY = { terms: {} };
  const el = badge("mystery", "");
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".gloss")).toBeNull();
  expect(wrap.querySelector(".info-trigger")).toBeNull();
  // Renders exactly as today: no wrapper at all, the plain badge itself.
  expect(el.className).toBe("badge");
  expect(el.parentElement).toBeNull();
});

test("freshnessBadge carries its gloss inline too, keyed off freshness.state", () => {
  (globalThis as any).VOCABULARY = { terms: { fresh: FRESH_TERM } };
  const el = freshnessBadge({ state: "fresh", reason: null });
  const wrap = el.parentElement ?? el;
  expect(wrap.querySelector(".freshness")?.textContent).toBe("fresh");
  expect(wrap.querySelector(".gloss")?.textContent)
    .toBe("cited inputs still match what is recorded now");
});

test("freshnessBadge with an unrecorded state (n/a) still renders plainly with no VOCABULARY entry", () => {
  (globalThis as any).VOCABULARY = { terms: {} };
  const el = freshnessBadge({ state: "n/a", reason: null });
  expect(el.className).toBe("freshness freshness-n-a");
  expect(el.parentElement).toBeNull();
});

test("Escape closes the definition card and returns focus to the trigger", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM } };
  const wrap = badge("recorded", "kind-recorded");
  document.body.appendChild(wrap);
  const trigger = wrap.querySelector(".info-trigger") as HTMLElement;
  expect(trigger).not.toBeNull();
  trigger.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  trigger.focus();
  expect(document.querySelector(".info-card")).not.toBeNull();
  document.dispatchEvent(new (window as any).KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  expect(document.querySelector(".info-card")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

test("clicking the info trigger opens a definition card with the definition, siblings and computed_by", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM } };
  const wrap = badge("recorded", "kind-recorded");
  document.body.appendChild(wrap);
  const trigger = wrap.querySelector(".info-trigger") as HTMLElement;
  trigger.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  const card = document.querySelector(".info-card");
  expect(card).not.toBeNull();
  expect(card?.querySelector(".info-card-badge .badge")?.textContent).toBe("recorded");
  expect(card?.querySelector(".info-card-definition")?.textContent).toBe(RECORDED_TERM.definition);
  expect(card?.querySelector(".info-card-siblings")?.textContent).toBe("siblings: derived");
  expect(card?.querySelector(".info-card-computed-by")?.textContent)
    .toBe("computed by: src/factory/system/queries.py");
});

test("definitionCardFields orders badge, definition, siblings, computed_by", () => {
  const fields = definitionCardFields(RECORDED_TERM);
  expect(fields.map((f) => f.className)).toEqual([
    "info-card-badge",
    "info-card-definition",
    "info-card-siblings",
    "info-card-computed-by",
  ]);
  expect(fields[0]?.node?.textContent).toBe("recorded");
});

test("renderVocabularyPanel groups entries by group and shows the real badge beside its definition", () => {
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM, fresh: FRESH_TERM } };
  renderVocabularyPanel();
  const root = document.getElementById("vocabularyGroups") as HTMLElement;
  const groupTitles = Array.from(root.querySelectorAll(".vocab-group-title")).map((el) => el.textContent);
  expect(groupTitles).toEqual(["claim-kind", "freshness"]);
  const entries = root.querySelectorAll(".vocab-entry");
  expect(entries.length).toBe(2);
  const recordedEntry = entries[0] as HTMLElement;
  expect(recordedEntry.querySelector(".badge")?.textContent).toBe("recorded");
  expect(recordedEntry.querySelector(".gloss")?.textContent).toBe(RECORDED_TERM.gloss);
  expect(recordedEntry.querySelector(".vocab-definition")?.textContent).toBe(RECORDED_TERM.definition);
  expect(recordedEntry.querySelector(".vocab-siblings")?.textContent).toBe("siblings: derived");
  const freshEntry = entries[1] as HTMLElement;
  expect(freshEntry.querySelector(".freshness")?.textContent).toBe("fresh");
});

test("renderVocabularyPanel does nothing when the panel root is not on the page", () => {
  document.getElementById("vocabularyGroups")?.remove();
  (globalThis as any).VOCABULARY = { terms: { recorded: RECORDED_TERM } };
  expect(() => renderVocabularyPanel()).not.toThrow();
});
