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
  nextStepBlock,
  refCardFields,
  refChip,
  renderVocabularyPanel,
} from "../src/system-comprehension.js";
import {
  badge,
  badgeSpan,
  freshnessBadge,
  renderBrief,
  renderChangedFiles,
  renderMatrix,
  renderReverse,
  renderStory,
  renderTrace,
  renderTraversalNotApplicable,
} from "../src/system-renderers.js";
import { REMEDIATION_DATA } from "../src/system-vocabulary-data.js";

const T060 = {
  ref: "task:T-060", id: "T-060", kind: "task",
  title: "Wire the safety governor into the planner loop",
  description: null, description_source: null, deferral_reason: null,
  status: "done", relations: { satisfies: ["sr:SR-121"] },
  path: "tasks/T-060.md", scope_href: "/system?scope=task%3AT-060",
};

// sr IS an openable kind (_OPENABLE_KINDS = {bundle, sr, task, file} in
// labels.py), so build_labels always emits a non-null scope_href for a real
// sr: ref -- this fixture must carry a truthful one, or tests that use it
// exercise a shape production can never produce.
const SR121 = {
  ref: "sr:SR-121", id: "SR-121", kind: "sr",
  title: "Battery-aware return",
  description: "The rover must return to base before battery falls below 15%.",
  description_source: "statement", deferral_reason: null,
  status: null, relations: {},
  path: "requirements/SR-121.md", scope_href: "/system?scope=sr%3ASR-121",
};

// A spec ref: never openable (spec is NOT in _OPENABLE_KINDS), so its
// scope_href is always null -- the genuine non-openable/span fixture. Tests
// that need to exercise the span path use this, not SR121.
const SPEC_FOO = {
  ref: "spec:docs/superpowers/specs/2026-08-14-foo-design.md",
  id: "2026-08-14-foo-design.md", kind: "spec",
  title: "Foo Design",
  description: "Why foo exists.", description_source: "purpose",
  deferral_reason: null, status: null, relations: {},
  path: "docs/superpowers/specs/2026-08-14-foo-design.md",
  scope_href: null,
};

// A story/reverse run WITH recorded changed files and a recorded commit
// range -- story.py's `_manifest_run` / reverse.py's `_run_entry` shape.
const RUN_WITH_DATA = {
  run_id: "run-001", source: "manifest", outcome: "completed",
  start_commit: "a".repeat(40), result_commit: "b".repeat(40),
  implementation: {
    kind: "recorded", text: "run run-001: 1 changed file(s) recorded",
    freshness: { state: "fresh", reason: null, dependencies: [] },
    citations: [], spans: [], changed_files: ["src/a.py"],
  },
  citation: { kind: "manifest", path: "evidence/runs/run-001.json", sha256: "c".repeat(64), anchor: null },
};

// A session-only run: story.py's `_session_run` / reverse.py's shape for a
// run with no matching evidence manifest -- changed_files is null (never an
// empty array) and both commits are null, per design (a session record never
// captures either).
const RUN_NO_DATA = {
  run_id: "run-002", source: "session", outcome: "completed",
  start_commit: null, result_commit: null,
  implementation: {
    kind: "missing", text: "run run-002: implementation not recorded",
    freshness: { state: "n/a", reason: "session records do not capture changed files or a commit range", dependencies: [] },
    citations: [], spans: [], changed_files: null,
  },
  citation: { kind: "session", path: "sessions/run-002.session.json", sha256: "d".repeat(64), anchor: null },
};

const A_CLAIM = {
  kind: "recorded", text: "Battery-aware return",
  freshness: { state: "fresh", reason: null, dependencies: [] },
  citations: [], spans: [],
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
  const dom = new JSDOM(
    "<!doctype html><body>"
      + "<div id=\"vocabularyGroups\"></div>"
      + "<div id=\"panelBrief\"></div><div id=\"panelMatrix\"></div>"
      + "<div id=\"panelTimeline\"></div><div id=\"panelGuide\"></div>"
      + "<div id=\"panelStory\"></div><div id=\"panelReverse\"></div>"
      + "<div id=\"panelTrace\"></div>"
      + "</body>",
    { pretendToBeVisual: true },
  );
  (globalThis as any).window = dom.window;
  (globalThis as any).document = dom.window.document;
  (globalThis as any).LABELS = {
    "task:T-060": T060, "sr:SR-121": SR121,
    [SPEC_FOO.ref]: SPEC_FOO,
  };
  (globalThis as any).ALIASES = {
    "T-060": "task:T-060", "task:T-060": "task:T-060",
    "SR-121": "sr:SR-121", "sr:SR-121": "sr:SR-121",
    [SPEC_FOO.ref]: SPEC_FOO.ref,
  };
  (globalThis as any).VOCABULARY = { terms: {} };
  (globalThis as any).REMEDIATION = REMEDIATION_DATA;
  // badge()/freshnessBadge() (system-renderers.ts) and renderVocabularyPanel()
  // reference these as free variables, exactly as they do in the assembled
  // page (system-shell.ts's clientSource()) -- wiring them onto globalThis
  // here reproduces that same page-scope resolution for a unit test.
  (globalThis as any).badgeSpan = badgeSpan;
  (globalThis as any).glossFor = glossFor;
  (globalThis as any).definitionTrigger = definitionTrigger;
  (globalThis as any).clear = (el: HTMLElement) => { el.innerHTML = ""; };
  (globalThis as any).refChip = refChip;
  (globalThis as any).boundedList = boundedList;
  (globalThis as any).nextStepBlock = nextStepBlock;
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

// --- Task 2 (legibility inc 2): artifact chips are real links ---

test("an openable ref renders as a link carrying the SPA contract", () => {
  const el = refChip("task:T-060");
  expect(el.tagName).toBe("A");
  expect(el.getAttribute("href")).toBe("/system?scope=task%3AT-060");
  expect(el.getAttribute("data-scope")).toBe("task:T-060");
  expect(el.className).toContain("scope-open");
  expect(el.hasAttribute("role")).toBe(false); // an anchor is already actionable
});

test("a non-openable ref stays a span with button semantics", () => {
  const el = refChip(SPEC_FOO.ref);
  expect(el.tagName).toBe("SPAN");
  expect(el.getAttribute("role")).toBe("button");
  expect(el.getAttribute("aria-expanded")).toBe("false");
});

test("openable kinds render as anchors, non-openable kinds as spans", () => {
  expect(refChip("sr:SR-121").tagName).toBe("A"); // sr IS openable
  expect(refChip("task:T-060").tagName).toBe("A");
  expect(refChip(SPEC_FOO.ref).tagName).toBe("SPAN"); // spec is NOT
});

test("clicking an anchor chip navigates and does not toggle the card", () => {
  const chip = refChip("task:T-060");
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelector(".info-card")).toBeNull();
});

test("hover and keyboard focus still open the card for an ANCHOR chip", () => {
  // The controller matches `.ref-chip[data-ref]`; an anchor missing data-ref
  // would silently never open (the exact regression this task must avoid).
  vi.useFakeTimers();
  try {
    const hoverChip = refChip("task:T-060");
    document.body.appendChild(hoverChip);
    hoverChip.dispatchEvent(new (window as any).MouseEvent("mouseover", { bubbles: true }));
    expect(document.querySelector(".info-card")).toBeNull();
    vi.advanceTimersByTime(120);
    expect(document.querySelector(".info-card")).not.toBeNull();
  } finally {
    vi.useRealTimers();
  }
  closeOpenCard();

  const focusChip = refChip("task:T-060");
  document.body.appendChild(focusChip);
  focusChip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
});

test("refCardFields orders id/kind/status, title, description, from, path, open", () => {
  // SR121 truthfully carries a scope_href (sr IS openable), so the Open
  // field this test's title has always named is now actually exercised.
  const fields = refCardFields(SR121);
  expect(fields.map((f) => f.className)).toEqual([
    "info-card-meta",
    "info-card-title",
    "info-card-description",
    "info-card-from",
    "info-card-path",
    "info-card-open",
  ]);
  expect(fields[0]?.text).toBe("SR-121 · sr");
  expect(fields[3]?.text).toBe("from: statement");
  expect(fields[5]?.href).toBe("/system?scope=sr%3ASR-121");
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

test("refCardFields renders a task's recorded relations (I2)", () => {
  const fields = refCardFields(T060);
  const relations = fields.find((f) => f.className === "info-card-relations");
  expect(relations?.text).toBe("satisfies: sr:SR-121");
});

test("refCardFields adds no relations line when relations is empty", () => {
  const fields = refCardFields(SR121);
  expect(fields.some((f) => f.className === "info-card-relations")).toBe(false);
});

test("infoCard renders each field as a line, with href fields as links", () => {
  // SR121's fields include its truthful Open field (see refCardFields
  // test above), so 6 lines, not 5.
  const card = infoCard(refCardFields(SR121));
  expect(card.className).toBe("info-card");
  expect(card.querySelectorAll(".info-card-line").length).toBe(6);
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

test("an opened card sets aria-controls on its trigger, cleared on close (M6)", () => {
  // SPEC_FOO (non-openable, span form): click both opens and closes it, so
  // it still exercises the aria-controls set/clear round trip via a click.
  // The anchor form's click-does-not-toggle behaviour has its own dedicated
  // test. sr IS openable (SR-121 is now an anchor), so it can't stand in
  // for the span case any more.
  const chip = refChip(SPEC_FOO.ref);
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  const card = document.querySelector(".info-card") as HTMLElement | null;
  expect(card?.id).toBeTruthy();
  expect(chip.getAttribute("aria-controls")).toBe(card?.id);
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(chip.getAttribute("aria-controls")).toBeNull();
});

test("clicking a span chip toggles the card open then closed", () => {
  // T-060 and SR-121 are both openable and render as anchors whose click
  // navigates instead of toggling (see "clicking an anchor chip
  // navigates..." above); SPEC_FOO stays a span, so it still exercises the
  // click-to-toggle contract.
  const chip = refChip(SPEC_FOO.ref);
  document.body.appendChild(chip);
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelector(".info-card")).not.toBeNull();
  chip.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
  expect(document.querySelector(".info-card")).toBeNull();
});

test("only one card is open at a time", () => {
  // Opened via focus rather than click so this exercises the shared
  // exclusivity behaviour regardless of chip form (anchor vs span).
  const a = refChip("T-060");
  const b = refChip("SR-121");
  document.body.appendChild(a);
  document.body.appendChild(b);
  a.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
  expect(document.querySelectorAll(".info-card").length).toBe(1);
  b.dispatchEvent(new (window as any).FocusEvent("focusin", { bubbles: true }));
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
  // SPEC_FOO (span form): only span chips carry an initial aria-expanded
  // attribute (an anchor is already actionable and skips role/aria-expanded
  // entirely -- see "an openable ref renders as a link..." above). SR-121
  // is openable now (a real sr: ref always is), so it can't stand in here.
  ensureCardController();
  const chip = refChip(SPEC_FOO.ref);
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
  // Task 12 (carried from Task 11 review): humanised headings, not raw slugs
  // -- a legend that greets a newcomer with `claim-kind` undercuts itself.
  expect(groupTitles).toEqual(["Claim kinds", "Freshness"]);
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

// --- Task 12: Next steps, absence severity, headings and first run ---

test("a next step names the command and copies it", () => {
  const el = nextStepBlock("sr_unsatisfied", "SR-121");
  expect(el.querySelector(".command")?.textContent).toContain("/trace-fix SR-121");
  expect(el.querySelector("button")?.textContent).toBe("Copy");
});

test("a next step's eyebrow, reason and why sit above the command row", () => {
  const el = nextStepBlock("sr_unsatisfied", "SR-121");
  expect(el.querySelector(".eyebrow")?.textContent).toBe("NEXT STEP");
  // sr_unsatisfied.what_it_means carries a literal {id} token -- substituted
  // with the bare identifier, same as the command (M8).
  expect(el.querySelector(".next-step-reason")?.textContent).toBe(
    REMEDIATION_DATA.states.sr_unsatisfied.what_it_means.replace("{id}", "SR-121"),
  );
  expect(el.querySelector(".next-step-why")?.textContent).toBe(
    REMEDIATION_DATA.states.sr_unsatisfied.why_it_matters,
  );
});

test("{id} is substituted in prose fields too, not just the command (M8)", () => {
  expect(REMEDIATION_DATA.states.sr_unsatisfied.what_it_means).toContain("{id}");
  const reason = nextStepBlock("sr_unsatisfied", "SR-121").querySelector(".next-step-reason")?.textContent;
  expect(reason).not.toContain("{id}");
  expect(reason).toContain("SR-121");

  expect(REMEDIATION_DATA.states.unresolved_ref.why_it_matters).toContain("{id}");
  const why = nextStepBlock("unresolved_ref", "SR-121").querySelector(".next-step-why")?.textContent;
  expect(why).not.toContain("{id}");
  expect(why).toContain("SR-121");
});

test("an unknown state renders an empty shell rather than throwing", () => {
  expect(() => nextStepBlock("not-a-real-state", "X-1")).not.toThrow();
  const el = nextStepBlock("not-a-real-state", "X-1");
  expect(el.className).toBe("next-step");
  expect(el.children.length).toBe(0);
});

test("clicking Copy becomes Copied for two seconds, then reverts", () => {
  vi.useFakeTimers();
  try {
    const el = nextStepBlock("sr_unsatisfied", "SR-121");
    document.body.appendChild(el);
    const button = el.querySelector("button") as HTMLButtonElement;
    button.dispatchEvent(new (window as any).MouseEvent("click", { bubbles: true }));
    expect(button.textContent).toBe("Copied");
    vi.advanceTimersByTime(1999);
    expect(button.textContent).toBe("Copied");
    vi.advanceTimersByTime(1);
    expect(button.textContent).toBe("Copy");
  } finally {
    vi.useRealTimers();
  }
});

// A recorded deferral_reason outranks the generic what_it_means sentence
// (visual addendum: "a recorded reason outranks the table").
test("a recorded deferral_reason outranks the generic what_it_means sentence", () => {
  (globalThis as any).LABELS = {
    ...((globalThis as any).LABELS),
    "sr:SR-121": { ...SR121, deferral_reason: "Deferred pending hardware review." },
  };
  const el = nextStepBlock("sr_unsatisfied", "SR-121");
  expect(el.querySelector(".next-step-reason")?.textContent).toBe("Deferred pending hardware review.");
  expect(el.textContent).not.toContain(REMEDIATION_DATA.states.sr_unsatisfied.what_it_means);
});

test("an empty panel renders one next step per distinct empty condition, all after the degraded banner", () => {
  // Both runs AND requirements are empty here -- two distinct, real gaps
  // (no_runs, no_requirements), each contributing its own next step. This is
  // not the "one Next step per empty child" case renderChangedFiles' comment
  // guards against (many empty items in ONE list); these are two separate
  // sections of one panel, each independently empty.
  renderStory({
    scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "Load skills", status: "done" },
    runs: [], requirements: [], degraded: true,
    degraded_reasons: ["task has no recorded runs"],
  });
  const panel = document.getElementById("panelStory") as HTMLElement;
  expect(panel.querySelectorAll(".next-step").length).toBe(2);
  const children = Array.from(panel.children);
  const bannerIndex = children.findIndex((el) => el.className === "degraded-banner");
  const nextStepIndex = children.findIndex((el) => el.className === "next-step");
  expect(bannerIndex).toBeGreaterThanOrEqual(0);
  // The (first) next step comes after the banner in document order.
  expect(nextStepIndex).toBeGreaterThan(bannerIndex);
});

test("an absence uses the dashed rail, not the failure rail", () => {
  renderStory({
    scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "Load skills", status: "done" },
    runs: [], requirements: [], degraded: false, degraded_reasons: [],
  });
  const empty = document.querySelector("#panelStory .presence-rail")!;
  expect(empty.className).toContain("is-absent");
  expect(empty.className).not.toContain("is-failure");
});

test("renderBrief's empty state gets the dashed rail and no panel-level next step (M10: the rail owns it)", () => {
  (globalThis as any).LABELS = {
    ...((globalThis as any).LABELS),
    "bundle:empty": {
      ref: "bundle:empty", id: "empty", kind: "bundle", title: "Empty bundle",
      description: null, description_source: null, deferral_reason: null,
      status: null, relations: {}, path: "bundles/empty.json", scope_href: null,
    },
  };
  (globalThis as any).ALIASES = { ...((globalThis as any).ALIASES), "bundle:empty": "bundle:empty" };
  renderBrief({
    // A bundle: scope's real query_brief payload carries no `member_of` key
    // at all (queries.py:1049, "Other scope kinds omit the key") -- this
    // fixture must not carry one either, or it would be misread as an sr:
    // scope's empty membership and spuriously add an unbundled_artifact
    // next step, defeating this test's own point.
    scope: { kind: "bundle", ref: "bundle:empty" },
    claims: [], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelBrief") as HTMLElement;
  const empty = panel.querySelector(".empty")!;
  expect(empty.className).toContain("presence-rail is-absent");
  // M10: renderBrief no longer renders its own no_claims Next step --
  // system-bootstrap.ts's renderContextRailNextStep renders the identical
  // block in the persistent context rail instead, so the two never show the
  // same command twice at once. Command substitution itself (the bare id,
  // not the prefixed ref) is covered by nextStepBlock's own tests above.
  expect(panel.querySelectorAll(".next-step").length).toBe(0);
});

test("nextStepBlock substitutes {id} with the bare identifier and {ref} with the canonical ref, independently", () => {
  (globalThis as any).REMEDIATION = {
    ...REMEDIATION_DATA,
    states: {
      ...REMEDIATION_DATA.states,
      __test_both_tokens: {
        state: "__test_both_tokens", headline: "test", what_it_means: "test", why_it_matters: "test",
        command: "/trace-fix {id} --canonical {ref}", command_kind: "slash", severity: "absence",
      },
    },
  };
  const el = nextStepBlock("__test_both_tokens", "sr:SR-121");
  expect(el.querySelector(".command-text")?.textContent).toBe("/trace-fix SR-121 --canonical sr:SR-121");
});

test("an unresolvable subject degrades the command to the raw string for both tokens, not a broken guess", () => {
  (globalThis as any).REMEDIATION = {
    ...REMEDIATION_DATA,
    states: {
      ...REMEDIATION_DATA.states,
      __test_both_tokens: {
        state: "__test_both_tokens", headline: "test", what_it_means: "test", why_it_matters: "test",
        command: "/trace-fix {id} --canonical {ref}", command_kind: "slash", severity: "absence",
      },
    },
  };
  const el = nextStepBlock("__test_both_tokens", "sr:SR-999-unknown");
  expect(el.querySelector(".command-text")?.textContent).toBe(
    "/trace-fix sr:SR-999-unknown --canonical sr:SR-999-unknown",
  );
});

test("renderMatrix's empty state gets the dashed rail and a matching next step", () => {
  renderMatrix({ scope: { kind: "bundle", ref: "bundle:empty" }, rows: [] });
  const panel = document.getElementById("panelMatrix") as HTMLElement;
  expect(panel.querySelector(".empty")?.className).toContain("is-absent");
  expect(panel.querySelectorAll(".next-step").length).toBe(1);
});

// Child-level empty states (one run's changed-files list, one reverse path
// list) get the dashed rail but never their own Next step block -- "one Next
// step per panel, never one per empty child."
test("renderChangedFiles' empty state is styled but carries no next step of its own", () => {
  const el = renderChangedFiles([])!;
  expect(el.querySelector(".empty")?.className).toContain("presence-rail is-absent");
  expect(el.querySelector(".next-step")).toBeNull();
});

test("renderReverse's empty state is styled with no matching remediation next step", () => {
  renderReverse({ scope: { kind: "file", ref: "file:src/a.py" }, paths: [], degraded: false, degraded_reasons: [] });
  const panel = document.getElementById("panelReverse") as HTMLElement;
  expect(panel.querySelector(".empty")?.className).toContain("presence-rail is-absent");
  expect(panel.querySelector(".next-step")).toBeNull();
});

// -- Task 7 residuals: no_requirements, unbundled_artifact, no_changed_files,
// no_commit_range, no_trace, traversal_not_applicable ------------------------

test("renderStory wires no_requirements as a panel-level empty, styled and followed by its next step", () => {
  renderStory({
    scope: { kind: "task", ref: "task:T-060" },
    task: { id: "T-060", title: "Wire the governor", status: "done" },
    runs: [RUN_WITH_DATA], requirements: [], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelStory") as HTMLElement;
  const reqs = panel.querySelector(".requirements") as HTMLElement;
  expect(reqs.querySelector(".empty")?.className).toContain("presence-rail is-absent");
  expect(reqs.textContent).toContain("no requirements recorded");
  expect(reqs.querySelectorAll(".next-step").length).toBe(1);
});

test("renderStory renders no no_requirements next step when requirements are present", () => {
  renderStory({
    scope: { kind: "task", ref: "task:T-060" },
    task: { id: "T-060", title: "Wire the governor", status: "done" },
    runs: [RUN_WITH_DATA], requirements: ["sr:SR-121"], degraded: false, degraded_reasons: [],
  });
  const reqs = document.querySelector("#panelStory .requirements") as HTMLElement;
  expect(reqs.querySelector(".presence-rail")).toBeNull();
  expect(reqs.querySelectorAll(".next-step").length).toBe(0);
});

test("renderBrief wires unbundled_artifact per-artifact, like matrix_never_run, when member_of is empty", () => {
  renderBrief({
    scope: { kind: "sr", ref: "sr:SR-121" },
    member_of: [], claims: [A_CLAIM], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelBrief") as HTMLElement;
  expect(panel.querySelector("#memberOf")).toBeNull();
  expect(panel.querySelectorAll(".next-step").length).toBe(1);
});

test("renderBrief renders no unbundled_artifact next step when member_of has entries", () => {
  // Registered so boundedList's refChip resolves this member cleanly --
  // an unregistered ref would legitimately add its OWN unresolved_ref next
  // step (a different, real gap), which would confound this assertion.
  (globalThis as any).LABELS = {
    ...((globalThis as any).LABELS),
    "bundle:evidence-lifecycle": {
      ref: "bundle:evidence-lifecycle", id: "evidence-lifecycle", kind: "bundle",
      title: "Evidence lifecycle", description: null, description_source: null,
      deferral_reason: null, status: null, relations: {},
      path: "bundles/evidence-lifecycle.json", scope_href: "/system?scope=bundle%3Aevidence-lifecycle",
    },
  };
  (globalThis as any).ALIASES = {
    ...((globalThis as any).ALIASES),
    "bundle:evidence-lifecycle": "bundle:evidence-lifecycle",
  };
  renderBrief({
    scope: { kind: "sr", ref: "sr:SR-121" },
    member_of: ["bundle:evidence-lifecycle"], claims: [A_CLAIM], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelBrief") as HTMLElement;
  expect(panel.querySelector("#memberOf")).not.toBeNull();
  expect(panel.querySelectorAll(".next-step").length).toBe(0);
});

test("renderBrief renders no unbundled_artifact next step for a scope kind with no member_of key at all", () => {
  // A bundle: scope's own query_brief payload carries no `member_of` key
  // (queries.py:1049) -- must not be misread as "empty membership".
  renderBrief({ scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, claims: [A_CLAIM] });
  const panel = document.getElementById("panelBrief") as HTMLElement;
  expect(panel.querySelectorAll(".next-step").length).toBe(0);
});

test("renderStory rolls up no_changed_files and no_commit_range into ONE next step each, never one per run", () => {
  renderStory({
    scope: { kind: "task", ref: "task:T-060" },
    task: { id: "T-060", title: "Wire the governor", status: "done" },
    runs: [RUN_NO_DATA, RUN_NO_DATA], requirements: ["sr:SR-121"], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelStory") as HTMLElement;
  // Panel-level, not nested inside either .run box -- direct children only.
  const panelLevel = Array.from(panel.children).filter((el) => el.className === "next-step");
  expect(panelLevel.length).toBe(2);
});

test("renderStory renders neither rollup next step once at least one run carries the data", () => {
  renderStory({
    scope: { kind: "task", ref: "task:T-060" },
    task: { id: "T-060", title: "Wire the governor", status: "done" },
    runs: [RUN_NO_DATA, RUN_WITH_DATA], requirements: ["sr:SR-121"], degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelStory") as HTMLElement;
  const panelLevel = Array.from(panel.children).filter((el) => el.className === "next-step");
  expect(panelLevel.length).toBe(0);
});

test("renderReverse rolls up no_changed_files and no_commit_range the same way, from paths[].run", () => {
  renderReverse({
    scope: { kind: "file", ref: "file:src/a.py" },
    paths: [
      { file: "src/a.py", run: RUN_NO_DATA, task: null, requirements: [], stops_at: "task" },
    ],
    degraded: false, degraded_reasons: [],
  });
  const panel = document.getElementById("panelReverse") as HTMLElement;
  const panelLevel = Array.from(panel.children).filter((el) => el.className === "next-step");
  expect(panelLevel.length).toBe(2);
});

test("renderTrace's empty branch stays the plain not-applicable path -- no presence rail, no next step", () => {
  renderTrace([]);
  const panel = document.getElementById("panelTrace") as HTMLElement;
  expect(panel.textContent).toContain("No trace recorded for this scope. See the Story or Reverse tabs.");
  expect(panel.querySelector(".presence-rail")).toBeNull();
  expect(panel.querySelectorAll(".next-step").length).toBe(0);
});

test("renderTraversalNotApplicable wires traversal_not_applicable with the dashed rail and a next step", () => {
  const node = document.createElement("div");
  node.id = "traversalPath";
  document.body.appendChild(node);
  renderTraversalNotApplicable(node, "task:T-060");
  expect(node.textContent).toContain("Traversal is not applicable for this scope.");
  expect(node.querySelector(".empty")?.className).toContain("presence-rail is-absent");
  expect(node.querySelectorAll(".next-step").length).toBe(1);
});

test("humaniseGroup falls back to a capitalised slug for an unlisted group, without inventing new terms", () => {
  (globalThis as any).VOCABULARY = {
    terms: { widget: { term: "widget", group: "widget-kind", label: "widget", gloss: "", definition: "d", siblings: [], computed_by: [] } },
  };
  renderVocabularyPanel();
  const title = document.querySelector("#vocabularyGroups .vocab-group-title");
  expect(title?.textContent).toBe("Widget kind");
});
