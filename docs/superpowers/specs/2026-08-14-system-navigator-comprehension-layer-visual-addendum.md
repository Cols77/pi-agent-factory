# Comprehension Layer — Visual Addendum

**Date:** 2026-08-14
**Companion to:** `2026-08-14-system-navigator-comprehension-layer-design.md`
**Status:** Design direction for the new components. Binding on implementation.

The visual identity is already settled by
`2026-08-13-system-navigator-visual-identity-design.md` — the midnight evidence
console. Nothing here changes it. This addendum specifies only the components the
comprehension layer adds, so that four subagents building four pieces produce one
surface rather than four.

## Tokens

Every value below already exists in `system-shell.ts:78`. No new hue is introduced.

| Role | Token | Value |
|---|---|---|
| Card ground | `--surface-raised` | `#12242c` |
| Inset ground (command line, rail) | `--surface-soft` | `#102028` |
| Hairline | `--line` / `--line-strong` | `#26404a` / `#3a606c` |
| Signal, affordances | `--signal` | `#65d9ff` |
| Absence attention | `--stale` | `#ffc857` |
| Failure | `--degraded` | `#ff6b6b` |
| Gloss text | `--text-muted` | `#91a8b0` |
| Ids, paths, commands | `--font-mono` | Cascadia Code |
| Reading text | `--font-body` | Aptos |

Two derived tokens are added for intent, both aliases of the above so the palette
does not grow: `--absence: var(--stale)` and `--gloss: var(--text-muted)`.

**Contrast, measured not assumed.** Revision 1 set `--gloss` to `--text-dim`
(`#698089`). At 12 px that is 4.26:1 on `--surface` and 3.83:1 on `--surface-raised` —
both below the 4.5:1 AA floor, and cards sit on exactly those grounds. `--text-muted`
(`#91a8b0`) clears it. The browser gate measures this rather than eyeballing it.

## The organising idea

This surface exists to answer one question: *is this recorded, or did something make
it up?* Provenance is the subject. The visual grammar should encode provenance and
nothing else should compete with it.

### Signature — the presence rail

Claim cards already carry a 3 px left rail. It becomes systematic and page-wide, with
exactly two states:

- **Solid rail** — something is recorded here. Applies to `recorded`, `derived`, and
  `synthesized` claims, populated panels, and resolved refs.
- **Dashed rail** — nothing is recorded here. Applies to `missing` claims, every
  empty state, unresolved hops, and absent descriptions.

Two states, not four. A dotted-versus-dashed distinction at 3 px is not reliably
readable and would read as inconsistency rather than as system. The four-way claim
kind stays carried by the badge word and its gloss, which is where a four-way
distinction belongs.

Colour on the rail follows severity, never kind: `--line-strong` normally,
`--absence` for an absence, `--degraded` for a genuine failure. Text always names the
state; the rail never carries meaning alone.

**Scope of the absence treatment.** It applies only to the empty states the browser
decides itself — the explicit `if (!x.length)` branches. The existing red `degraded:`
banner is unchanged in this increment, because its reasons are free-text sentences the
browser cannot classify without interpreting them. See the design's "Severity,
narrowed".

### Signature moment — the command line

The remedy for every gap in this system is a command typed into a coding agent. The
Next step block should therefore look like the terminal it is destined for, not like a
generic alert box:

```
NEXT STEP
No task satisfies this requirement. Nothing implements it yet,
so it cannot be validated.

  ▌ /trace-fix SR-121                                    [ Copy ]
```

- `NEXT STEP` uses the existing `.eyebrow` treatment (mono, uppercase, `.14em`
  tracking, `--signal`).
- The explanation is two sentences maximum, in `--font-body` at the reading size,
  measure capped at 64ch.
- The command sits on a `--surface-soft` inset with a `--signal` block-cursor glyph
  `▌` as the prompt. It is a text character, so no icon dependency is added.
- `Copy` reuses the existing `.secondary-action` button. On success it becomes
  `Copied` for two seconds, then reverts. It never becomes a second verb.

This is the one place boldness is spent. Everything around it stays quiet.

## Components

### Ref chip

```
T-060 · Wire the safety governor into the planner loop
└mono┘ └dim┘ └────────────── body face ──────────────┘
```

Id in `--font-mono` on a `--signal-soft` ground with 2 px horizontal padding. Title in
`--font-body` at the reading size. Separator `·` in `--text-dim`. On hover and focus,
a 1 px `--signal` underline appears under the **id only**, signalling that the id is
the handle. Title truncates with `text-overflow: ellipsis` at the container width; the
full title is in the card.

An unresolved ref renders the raw ref in mono followed by `not in the label index` in
`--text-dim`, with the dashed rail. Never blank, never guessed.

### Cards (ref card and definition card)

One component, two payloads. `--surface-raised`, 1 px `--line-strong`,
`--radius-md`, `--shadow-raised`, `max-width: 34ch`, padding 12px 14px.

No CSS triangle pointer — it is decoration that costs positioning complexity and adds
nothing. The card offsets 6 px from its trigger and flips to stay in the viewport.

Behaviour: opens after a 120 ms hover delay, immediately on keyboard focus, and on tap
as a toggle. `Escape` closes and returns focus to the trigger. Only one card is open at
a time. Under `prefers-reduced-motion` the fade is removed and the card appears
immediately.

Ref card contents, in order: id and kind and status on one line; title; description
clamped to three lines; `from: statement` in `--text-dim` mono naming the recorded
field; path in mono; `Open` link when the ref is an openable scope.

Definition card contents: the term as it actually renders as a badge, the definition,
`siblings:` as a list, and `computed by:` with the module path in mono.

### Badge with gloss

```
▌ RECORDED  ⓘ   · fresh  ⓘ
  straight from a file, not inferred
```

The badge keeps its exact contract word. `ⓘ` is a text glyph in `--signal` at 11 px,
a real `<button>` so it is keyboard reachable, with an accessible name of
`What does <term> mean?`. The gloss line sits beneath at 12 px in `--gloss`.

### Context rail

Above 1200 px only. `--surface-soft` ground, 1 px `--line` on its left edge, sticky at
the workspace top, 300 px wide. Sections separated by hairlines, never by nested
boxes: scope summary, readiness beside its counts, membership, current Next step.
Below 1200 px it collapses above the panel content in the existing single-column flow.

### Vocabulary panel

A full workspace view, not a modal — it is reference material, and a modal cannot be
read beside the thing that prompted the question. Grouped by `group`, two columns above
1200 px. Each entry renders **the badge exactly as it appears in the interface**,
then gloss, definition, siblings, and `computed_by`. Seeing the real badge beside its
definition is what makes this a legend rather than a word list.

### Empty states and first run

Every empty state gets the dashed rail, a sentence naming what is absent, and a Next
step block. Copy is sentence case, active voice, no apology, no exclamation.

The zero-bundle feature directory renders:

> **No features defined yet.**
> A feature bundle groups the requirements, tasks, and decisions you read together to
> understand one part of the system. Bundles are how this project is browsed, so
> until one exists the directory stays empty.

followed by its Next step block.

The landing orientation strip:

> This page is the evidence behind what the system claims. Start with a weak or
> unbundled feature, open it, and follow its spine: requirement, tasks, decisions,
> files. Every term here is defined — select the ⓘ beside any badge.

Dismiss control reads `Hide this`, not `×`.

## Quality floor

Not announced in the UI, but required: responsive to 390 px with no horizontal page
overflow, visible keyboard focus on every new interactive element using the existing
cyan focus outline, `prefers-reduced-motion` respected by every card and copy
transition, and contrast of `--gloss` on `--surface` verified at 12 px during the
browser pass.

## What was deliberately cut

A four-way dotted/dashed/solid/none rail grammar encoding claim kind. It was not
reliably distinguishable at 3 px and competed with the badge that already carries that
information. Reduced to the two-state presence rail above.
