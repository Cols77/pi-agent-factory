# System Navigator Visual Identity and Readability Design

**Date:** 2026-08-13
**Status:** Approved through the UI review and the user's readability/visual-identity directives

## Purpose

`/system` is the Pi Agent Factory evidence control center. Its primary user is an engineer
who needs to answer three questions quickly:

1. Where is the system weak, stale, blocked, or unbundled?
2. What requirement, task, decision, validation, and file evidence supports a feature?
3. What should I inspect next?

The redesign keeps the browser surface read-only and keeps Python authoritative for ordering,
freshness, readiness, coverage, and provenance.

## Art direction

The interface is a **midnight evidence console**: graphite and ink surfaces, cool cyan signal
lines, amber/red attention states, and restrained green validation states. It must look like a
purpose-built engineering instrument rather than a white-card SaaS dashboard.

Typography carries the hierarchy. Display text uses a technical variable/display face available
on the host (`Bahnschrift`, `Aptos Display`, then a restrained fallback). Reading text uses
`Aptos`/`Segoe UI Variable Text`; artifact identifiers and evidence paths use `Cascadia Code`.
No external font or asset dependency is introduced.

The memorable interaction is a **trace spine** that renders the active scope as an ordered path:
requirement → tasks → design decisions → changed files. Each step is a distinct, labelled segment,
not a sentence containing arrows.

## Constraints

- Preserve the vanilla TypeScript + DOM architecture and inline client assembly.
- Do not add a frontend framework, build dependency, remote font, image, or icon package.
- Preserve the existing JSON contracts and the rule “Python computes; the browser renders.”
- Preserve direct URLs, browser history, lazy trace loading, Alt+number shortcuts, and read-only
  operation.
- Maintain visible text labels in addition to color for every state.
- Support desktop, tablet, and a 390 px viewport without horizontal page overflow.
- Respect `prefers-reduced-motion`.
- Keep TypeScript and DOM tests deterministic under jsdom.

## Information architecture

### Shell

The header contains a small `PIF / EVIDENCE` eyebrow, the `System Navigator` title, and a concise
description. A subtle grid/noise-like CSS atmosphere provides depth without reducing contrast.

The desktop shell uses a 320 px navigation rail and a fluid content workspace. The navigation
rail includes search, readiness groups, counts, and selected-scope state.

At 760 px and below, the shell becomes one column. In focus mode, the rail contracts to a compact
“Browse scopes” control above the full-width workspace. Opening it reveals the scope list as a
bounded sheet; it never reserves 300 px beside the content.

### Landing mode

The landing is visible immediately, including a status treatment while project health loads.
After health resolves it contains:

- a strong “Project evidence” heading and explanatory lead;
- one prominent overall health metric with an honest `No measurable evidence` state when the
  denominator is zero;
- compact class metrics with labels and ratios;
- a feature directory whose rows expose label, readiness, member count, and the readiness counts
  supplied by Python;
- a recoverable error treatment with Retry when health cannot be loaded.

The sidebar remains a navigation index. The main feature directory is the readable overview, not
a second unlabelled list.

### Focus mode

Selecting a scope hides the landing content. The workspace begins with:

- a scope-kind eyebrow;
- the human bundle label when known, with the raw ref retained as monospace metadata;
- refresh and last-loaded status;
- the trace spine when traversal data exists;
- only tabs relevant to the current scope kind.

Bundle and SR scopes show Brief, Matrix, Timeline, Guide, and Trace. Task scopes show Story. File
scopes show Reverse. Inapplicable panels may remain in the DOM for compatibility but are removed
from navigation and the tab sequence.

## Readability rules

- Body reading size is at least 14 px with 1.6 line height; metadata is at least 12 px.
- Long-form panels use a controlled maximum line length of approximately 90 characters.
- IDs and paths use the monospace face; prose does not.
- Cards have clear type hierarchy: state rail, heading/status row, claim text, then optional detail.
- Citations and quoted spans are placed in a native disclosure labelled with the evidence count,
  reducing vertical noise without hiding the existence of evidence.
- Matrix rows use a compact grid on wide screens and a stacked layout on narrow screens.
- Fresh, stale, degraded, blocked, missing, and n/a remain legible without color.
- Focus outlines use the cyan accent and remain visible on every interactive element.

## Interaction and accessibility

- Readiness group controls are native buttons and support pointer, Enter, and Space automatically.
- Tabs implement Left/Right, Home, and End movement; inactive tabs use `tabindex=-1`.
- Panels use `role=tabpanel` and `aria-labelledby`.
- Loading surfaces use `aria-busy` and a live status message.
- The active scope uses `aria-current=page` and a persistent visual state.
- Search Enter and Go use the same exact-ref navigation path; no invalid `fetch('sr:...')` request
  is made.
- Scope arrow navigation only considers currently visible links.
- Motion is limited to meaningful hover/focus/loading transitions and is disabled when reduced
  motion is requested.

## Error handling

- Health load failure leaves the shell and landing visible, explains that project evidence could
  not be read, and provides Retry.
- Scope failures preserve navigation and return to the browse state; they do not blank the page.
- Guide and trace remain independently degradable as in the existing architecture.

## Verification

Automated DOM tests must cover landing/focus separation, zero-denominator wording, relevant tabs,
native disclosure controls, keyboard tab movement, Retry, selected scope, trace-spine structure,
and mobile CSS structure. Existing extension and Python system suites must remain green.

An independent browser-validation agent must inspect the rendered page at approximately
1440×900, 1024×768, and 390×844, check the landing and a populated bundle scope, exercise keyboard
navigation, and report console errors, overflow, contrast/readability concerns, and reduced-motion
behaviour.

## Non-goals

- Changing Python evidence semantics or JSON schemas.
- Adding write actions, source-file editing, authentication, or remote services.
- Building a graph canvas or replacing the existing trace query.
- Adding a theme chooser or user preference storage.
- Refactoring unrelated docs/review browser surfaces.
