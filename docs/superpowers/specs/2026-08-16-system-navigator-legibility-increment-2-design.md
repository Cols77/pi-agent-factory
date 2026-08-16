# System Navigator — Legibility, Increment 2

**Date:** 2026-08-16
**Status:** Design for review.
**Builds on:** `2026-08-14-system-navigator-comprehension-layer-design.md` (merged at `51c4da7`)
**Surface:** `/system` only.

## The design principle: the newcomer test

**Every decision in this document answers to one person.** They have never used this
tool. They have never used a coding agent. They know nothing about the system being
built. They open `/system` and must be able to figure the rest out from the page.

That person cannot be sent to documentation, cannot be assumed to know what a
"bundle", a "requirement", a "claim" or a "trace" is, and will not go and read a
glossary before starting. **Whatever they need to understand must arrive where they
need it, in the order they need it.**

They arrive with two separate ignorances, and the surface must serve both:

1. **They don't know the tool's vocabulary** — `bundle`, `SR`, `recorded`, `fresh`,
   `never-run`, `satisfied`. Increment 1 began this with badge glosses; it is not
   finished until the *framing* is plain too, not only the badges.
2. **They don't know the project being built** — what a "safety governor" is, why
   there are 181 requirements, what any of them say. This is served by titles and
   descriptions, which is why Component 1 (nothing truncated) is a correctness issue
   and not a preference.

**The test, stated so it can be applied:** a reader who knows nothing must be able to
answer, in this order, without leaving the page —

1. *What is this project made of?*
2. *What is this page showing me?*
3. *What does this word mean?*
4. *What does this identifier refer to?*
5. *What should I look at first?*
6. *Something is missing here — what do I do about it?*

Increment 1 answered 3, 4 and 6. This increment must answer 1, 2 and 5, and finish 3
and 4 where they are still truncated or buried.

**What this principle does NOT license.** It does not mean renaming contract words —
the user chose "keep the word, add a plain gloss" in Increment 1 precisely so the
browser and the CLI stay one language, and that ruling stands. It does not mean
inventing explanatory prose about artifacts: descriptions remain verbatim from one
recorded field or absent. Being welcoming must never cost being truthful; a surface
that explains confidently and wrongly is worse for a newcomer than one that says
nothing, because they have no way to detect the error.

## Purpose

Increment 1 made the navigator *answerable*: every ref carries its title, every
contract word a definition, every gap a command. Using it revealed that answerable is
not the same as **legible**. The user's report, verbatim:

> "I don't understand much because it lacks some kind of contextualisation of the
> information available in the browser's UI… what's the Brief about? The matrix? Maybe
> a simple phrase to indicate in the tab what information is it providing, how to read
> that… The pill above with requirement>tasks>Design is just really ugly. eventually
> use more space, move the title in the pills themselves, allow hyper link to navigate
> to the corresponding requirement… we need the informations to be more directly,
> clearly and understandably available."

Plus a correctness complaint: **descriptions are truncated.** A requirement's statement
is the one place the surface explains what a requirement *is about*, and it is clipped.

This increment closes those, and the residuals Increment 1's final review left open.

## Diagnosis, measured

| Problem | Evidence |
|---|---|
| Requirement text is clipped | `.info-card-description` sets `-webkit-line-clamp: 3` (`system-shell.ts:497`). SR statements run to 60+ words; the reader sees a third of one. |
| Bundle descriptions are capped | `system_bundle.schema.json:18` `maxLength: 280`. Increment 1 argued this cap was "convention"; it is an arbitrary limit on the only prose a feature has. |
| Chip titles are clipped | `.chip-title` uses `text-overflow: ellipsis` with `white-space: nowrap`. |
| The spine is cramped | `.traversal-path` is `repeat(4, minmax(0, 1fr))` (`system-shell.ts:402`). Measured at 1440×900: four 170 px columns holding 1, 6, 0 and 19 items. The fat columns truncate while the thin ones sit empty. |
| Chips do not navigate | `scope_href` is used ONLY inside the hover card, as an "Open" link (`system-comprehension.ts:208`). Reaching a requirement takes hover → read → click. |
| Tabs are unexplained | `<button id="tabBrief" … aria-label="Brief">Brief</button>` (`system-shell.ts:704`). Seven tabs, no statement anywhere of what any of them shows. |

## Component 0 — The landing teaches the ontology

*Answers newcomer questions 1, 2 and 5.*

Today the landing says "See the system clearly" and shows `Overall 179/300 satisfied ·
60%` beside five ratios named `task->plan`, `SR satisfied`, `SR validated`. A newcomer
cannot tell what a requirement, a feature or a task is, nor which of those numbers
matters, nor where to click.

### The shape sentence

One sentence, composed in Python from the health projection's own counts, stating what
the project is made of in plain words. For `cool_physical_ai_project` it reads:

> This project is described by **181 requirements**, grouped into **14 features**.
> **43 tasks** implement them, and **1 requirement** has a passing validation.

That single line teaches the entire ontology — requirements exist, features group them,
tasks implement them, validation proves them — while stating this project's actual
shape. It is derived, not synthesised: every number comes from `query_health`, and the
sentence is a template with counts substituted, never a model's prose. It renders with
a `derived` badge and its gloss, so its provenance is visible like any other claim.

Zero-denominator states must read honestly rather than cheerfully: with no bundles it
says "grouped into **no features yet**" and carries the `no_bundles` next step.

### The reading path

Beneath it, a short "New here?" block naming the first move in the user's own terms —
open a feature, read its Brief, follow its spine — with each named thing linking to the
real control. It is dismissible via the existing orientation-strip mechanism and key,
not a second one.

### Numbers explain themselves

Every ratio on the landing gains its denominator rule inline, not only on hover: the
vocabulary entries for the five health classes already state these (Increment 1), and
`SR validated 1/43` beside `SR satisfied 102/181` is the case that most needs it. The
`ⓘ` remains for the full definition; the one-line reason sits on the tile.

## Component 1 — Nothing is truncated

- Remove `-webkit-line-clamp` from `.info-card-description`. The card gains
  `max-height: min(60vh, 520px)` with `overflow-y: auto`, so a long statement scrolls
  inside the card instead of being cut off or overflowing the viewport.
- Remove `maxLength: 280` from `system_bundle.schema.json`. The schema annotation keeps
  the *guidance* ("state what the feature is; rationale belongs in an ADR") and drops
  the false claim that a character count enforces it — a point Increment 1's review
  already made and the spec already conceded.
- `.chip-title` stops clipping in the spine and in any single-column context: it wraps.
  It keeps `ellipsis` only where a chip sits in a genuinely narrow grid cell (matrix
  subject column), where wrapping would break row alignment.

**Rule:** the surface may bound a *list* (five rows plus `+ N more`) but never a
*sentence*. A count is recoverable by expanding; a clipped statement is not.

## Component 2 — The evidence ladder

The spine becomes vertical and full-width.

Four equal columns was the wrong shape because the content is wildly asymmetric — on
`bundle:reactive-planner`: 15 requirements, 6 tasks, 0 design, 19 files. Equal columns
force the heavy steps to truncate while the empty one holds nothing.

```
┌────────────────────────────────────────────────────────────────────┐
│ ① REQUIREMENT ───────────────────────────────────────────────  15  │
│    SR-030  Planner Ground-Truth Isolation                          │
│    SR-033  Interchangeable Planner Implementations                 │
│    SR-038  Deterministic Planner Fallback After LLM Failure        │
│    ▸ + 12 more                                                     │
│                                                                    │
│ ② TASKS ──────────────────────────────────────────────────────  6  │
│    T-055  Add Architecture Records, Verify Contracts, and …        │
│    ▸ + 3 more                                                      │
│                                                                    │
│ ③ DESIGN ─────────────────────────────────────────────────────  0  │
│    Not recorded                                                    │
│    NEXT STEP  ▌ uv run python -m factory.trace link …    [ Copy ]  │
│                                                                    │
│ ④ FILES ──────────────────────────────────────────────────────  19 │
│    src/drone/planning/reactive.py                                  │
│    ▸ + 14 more                                                     │
└────────────────────────────────────────────────────────────────────┘
```

- Each step is a full-width row. A chip gets the workspace width instead of 170 px, so
  titles fit without truncation — which is what "move the title in the pills" asks for.
- The step label sits on a rule with its **count right-aligned**. The count is the
  answer to "how much is here", visible without expanding.
- Sequence is carried by the numbered markers and the left rail. **The decorative
  `::after` chevron is removed** — Increment 1's review already noted it no longer
  bridges columns and reads as an orphan; in a vertical ladder it is redundant.
- The five-row cap and `+ N more` disclosure stay. Bounding the list is right; the
  count on the rule makes the bound honest.
- An empty step renders `Not recorded` **and its Next step inline**, in the step where
  the absence is. That is the exact case the user named.

## Component 3 — Chips navigate

`refChip` returns an `<a href>` when the ref has a `scope_href`, and a `<span>`
otherwise. Clicking navigates to that artifact's page; hover and keyboard focus still
open the info card.

This gives back what a link gives: middle-click, open-in-new-tab, copy-link, the
browser's own focus and visited semantics — none of which a `<span role="button">`
provides.

Accessibility: an anchor is already actionable, so the anchor form drops
`role="button"` and uses `aria-describedby` pointing at the card. The non-openable
span form keeps `role="button"` and `aria-expanded` as today. `scope_href` is non-null
only for `bundle`, `sr`, `task`, `file` — unchanged from Increment 1; `spec`, `plan`,
`adr` remain non-openable and render as spans.

## Component 4 — Every panel says what it is

Each tab gains a one-line orientation, shown as a persistent line beneath the tab strip
for the active panel — not a tooltip, because this is orientation a newcomer needs
continuously, not detail they seek out.

Wording lives in Python, in a new `PANELS` table in `vocabulary.py`, so the browser
keeps rendering rather than authoring. Each entry has `label`, `what_it_shows` (one
sentence), and `how_to_read` (one sentence).

Draft wording, to be checked against what each panel actually renders:

| Panel | What it shows | How to read it |
|---|---|---|
| Brief | Every claim this scope makes, with the evidence behind it. | Each card's badge says whether the claim was copied from a file, computed, or written by an agent. |
| Matrix | Whether each requirement's validation has run, and what it concluded. | `never-run` means no result was ever recorded — not that it failed. |
| Timeline | Decisions recorded against this scope, in the order they happened. | An actor of `not-recorded` means the record does not say who decided. |
| Guide | A prose walkthrough assembled from the same recorded claims. | Quoted spans are verbatim; anything else is assembled from them. |
| Trace | The V-cycle chain: requirement → satisfying tasks → their plans and specs. | A hop reading `unresolved` means the link exists but its target does not. |
| Story | Every recorded run of this task, and what each one changed. | A run sourced from a session has no commit range; only manifests record one. |
| Reverse | Which requirement this file traces back to, and through which run. | `stops_at` names the first hop that did not resolve. |

A completeness test asserts every tab id in `TABS_BY_KIND` has a `PANELS` entry.

## Component 5 — Increment 1's residuals

1. **Unreachable remediation states.** 17 of 27 never render. Wire the ones whose
   trigger the browser can already see: `no_requirements`, `no_changed_files`,
   `no_trace`, `no_commit_range`, `traversal_not_applicable`, `unbundled_artifact`.
   The 11 `GapKind` states need gap data the browser does not receive; **remove the
   spec's promise that they render**, and record them as CLI-only until a gaps
   projection exists. Increment 1's spec over-promised and its text must be corrected
   rather than left aspirational.
2. **Alias collision.** `build_labels`' file loop runs last and does
   `aliases[path] = ref` unconditionally, so a changed-file path exactly equal to a
   bare id would shadow it silently. Guard it: skip and append to `degraded` on
   collision.
3. **`.presence-rail.is-failure` is dead CSS.** Either wire a state that uses it or
   delete it. Decide from the code; do not leave an unreachable style.
4. **`adr` members crash the Brief tab.** `queries.py:1011` raises
   `AssertionError: unexpected member kind: 'adr'`, breaking Brief for 2 of 14 bundles
   in the product repo (`event-log-replay-metrics`,
   `governance-traceability-contract-spine`) and taking the new context rail's
   membership and Next-step sections with it. Pre-existing (commit `4d59510`), now in
   scope. Resolve `adr:` members through `adr_module.load_adrs` as the label index
   already does, with a regression test per affected bundle shape.

## Component 6 — Jargon audit of the framing text

*Answers newcomer question 3, where Increment 1 left it half-done.*

Increment 1 glossed the **badges**. The prose around them was never audited, and it is
where a newcomer meets the vocabulary first. Current examples, all shipped:

- `"Trace what the system claims, what validates it, and where the evidence leads."`
  (the page subtitle) — "claims", "validates", "evidence" all unexplained.
- `"Start with weak or unbundled features, then follow their evidence spine."` — three
  undefined terms in twelve words, and it is the landing's only instruction.
- `"Declared scopes"`, `"Browse by readiness"`, `"BUNDLE SCOPE"` — "scope" and
  "readiness" are tool vocabulary presented as if self-evident.

Deliverable: walk every literal string rendered by `system-shell.ts`,
`system-renderers.ts` and `system-bootstrap.ts`, and for each one decide, recording the
decision:

- **Plain** — rewrite in words a newcomer knows (`"Declared scopes"` →
  `"Features and artifacts"`).
- **Contract word, keep + gloss** — it names a real artifact kind or state and must
  match the CLI; ensure it carries a gloss or an `ⓘ` at that site.
- **Leave** — already plain.

The output is a table in the implementation report, so the choices are reviewable
rather than a diffuse rewrite. Contract words are never renamed; only the sentences
*around* them change.

## Verification

### The newcomer test, as an acceptance gate

Beyond the unit and browser gates below, the increment is accepted only if a reader
with no prior knowledge can answer the six questions from the design principle using
the page alone. Make this checkable rather than aspirational: an independent agent is
given the rendered page against `cool_physical_ai_project`, told nothing about the
tool, the coding agent, or the project, and asked to answer all six in its own words —
plus one it cannot answer from a correct page, as a control against agreeable guessing.
Its answers are recorded and judged against the real data. A confident wrong answer is
a failure, not a pass.


- Python: unit tests per change; a completeness test for `PANELS`; a collision test for
  the alias guard; a regression test that a bundle with an `adr:` member briefs without
  raising.
- TypeScript (jsdom): unclamped description; anchor vs span by `scope_href`; ladder
  structure — one row per step, count on the rule, five-row cap with `+ N more`, empty
  step carrying its Next step inline; panel orientation line switching with the tab.
- Browser gate: extend the existing per-element containment assertions to the ladder;
  assert no chip title is visually truncated at 1440×900; assert the orientation line
  is present for every tab; re-run the three viewports against
  `cool_physical_ai_project`.

## Non-goals

- No change to the label/vocabulary/remediation contracts beyond the additions above.
- No new dependency; no framework, remote font, image, or icon package.
- The browser still never parses a ref, never synthesises a description, and never
  executes a command.
- No gaps projection (the 11 `GapKind` states stay CLI-only this increment).
