# System Navigator — Legibility, Increment 2

**Date:** 2026-08-16
**Status:** Design for review.
**Builds on:** `2026-08-14-system-navigator-comprehension-layer-design.md` (merged at `51c4da7`)
**Surface:** `/system` only.

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

## Verification

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
