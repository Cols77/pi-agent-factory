# System Navigator Comprehension Layer Design

**Date:** 2026-08-14
**Status:** Approved by the user through brainstorming on 2026-08-14.
**Surface:** `/system` only (the System Navigator). No other browser surface changes.

## Purpose

`/system` renders the factory's evidence correctly and explains it to nobody. Every
number, badge, and reference on the page is accurate and most of them are unreadable
without knowing the codebase that produced them.

Measured against this repository on 2026-08-14 at 1440×900:

- The landing shows `task->plan 21/21`, `task->SR 0/21`, `plan->spec 25/51`,
  `SR satisfied 0/0`, `SR validated 0/0`. Nothing on the page says what a class is,
  what "satisfied" means, or whether `0/21` is a problem.
- The sidebar is 60 rows of bare refs: `task:T-001`, `task:T-002`,
  `spec:docs/superpowers/specs/2026-07-16-deterministic-agent-dev-factory-design.md`.
  A 320 px rail carries no title for any of them.
- Opening `task:T-001` renders `task:T-001` as the 40 px page heading. The task's
  actual title — `` `load_skill_block` -- pure hard skill loading (Python) `` — is
  14 px body text inside the Story panel.
- That same page shows a red `degraded:` banner whose sole reason is
  "task has no recorded runs". An absence is rendered as a failure.
- It also shows "Traversal is not applicable for this scope.", "No recorded runs for
  this task.", and "no requirements recorded" — three dead ends, no next step from
  any of them.
- Roughly 900 px of horizontal canvas beside that content is empty.

This design adds the layer that makes the surface self-explanatory: what every word
means, what every reference is, and what to do about every gap.

## Principles preserved

- **Python computes; the browser renders.** Titles, descriptions, definitions and
  remediation are Python projections shipped as JSON. TypeScript renders them and
  performs no interpretation, no sorting, no synthesis.
- **The browser stays read-only.** It displays commands; it never executes them.
  Write operations remain SP-C's scope.
- **Nothing is synthesized.** Every description shown is verbatim recorded text from
  a named field. Where no field is recorded, the surface says so and offers the
  command that would record it. A model-written summary would be a `synthesized`
  claim under this system's own vocabulary, and placing one inside the affordance
  meant to establish trust would defeat it.
- **No new dependency.** Vanilla TypeScript and DOM, inline assembly, no framework,
  no remote font, image, or icon package.

## Vocabulary of this document

"Ref" means a scope reference string as it appears in payloads: `task:T-001`,
`sr:SR-121`, `bundle:reactive-planner`, `spec:docs/…md`. "Chip" means the rendered
inline representation of a ref. "Card" means the popover attached to a chip or badge.

## Component 1 — Label index

### Contract

New Python projection `factory.system labels --json`, served at
`GET /api/system/labels`.

```
{
  "labels": {
    "<ref>": {
      "ref": "task:T-060",
      "id": "T-060",
      "kind": "task",
      "title": "Wire the safety governor into the planner loop",
      "description": "…verbatim recorded text…" | null,
      "description_source": "dod" | "statement" | "decision" | "purpose" | null,
      "status": "done" | "todo" | "proposed" | … | null,
      "path": "tasks/T-060-….md",
      "scope_href": "/system?scope=task%3AT-060" | null
    }
  },
  "degraded": []
}
```

`scope_href` is `null` when the ref's kind is not an openable scope, so the renderer
never fabricates a dead link.

### Sources

The projection composes existing loaders. It forks no parser and persists no index.

| Kind | Title | Description | Description source field |
|---|---|---|---|
| `sr` | `Requirement.title` | `Requirement.statement` | `statement` — a required field (`requirements/register.py:12`), so an SR always has one |
| `task` | ledger/frontmatter `title` | `dod` entries joined, then the body's `Modify:`/`Test:` lines | `dod` |
| `adr` | `AdrDocument.title` | first paragraph of the `Decision` section (`system/adr.py:50` already sections the body) | `decision` |
| `spec`, `plan` | `Node.title` (`trace/model.py:31`) | the `Purpose` section's first paragraph when the document has one; otherwise the first paragraph after the H1 | `purpose` |
| `bundle` | `BundleDeclaration.label` | new optional `description` field (Component 5) | `description` |
| `br`, `feat`, `metric`, `goal`, `run`, `diag` | `Node.title` | none extracted in this increment | `null` |
| `file` | the path itself | none | `null` |

A ref absent from the index is rendered as its raw ref plus the visible note
`not in the label index`. It is never guessed and never silently blanked.

### Rendering

One helper, `refChip(ref)`, replaces every bare-ref emission in
`system-renderers.ts` and `system-bootstrap.ts`:

- `renderMatrixRow` — `row.subject.ref`
- `renderTimelineEvent` — `event.subject.ref`
- `renderStory` — the `requirements` list and the story task heading
- `renderReversePath` — the `file`, `run_id`, `task`, and `requirements` hops
- `renderTrace` — task hops (the SR, plan, and spec hops already carry titles; they
  route through the same helper for consistency)
- `renderTraversal` — the Requirement, Tasks, Design, and Files steps
- `renderFeatureSidebar` — the Unbundled group's rows
- `renderBundleList` — feature directory rows
- `setScopeHeading` — the scope heading (see Component 4)

The chip renders `T-060 · Wire the safety governor into the planner loop`: the id in
the monospace face, the title in the reading face. The chip carries no description —
an SR `statement` is long enough to break a matrix row.

The card, opened on hover, on keyboard focus, and on tap, carries: id, kind, status,
title, the description clamped to three lines, the `description_source` shown as
`from: statement` so the reader can see which recorded field they are reading, the
path in monospace, and an `Open` link when `scope_href` is non-null. When
`description` is `null` the card shows the Component 3 remediation block for that
kind instead of an empty area.

### Why an index rather than titles embedded in each payload

Embedding titles would require a parallel change and a schema revision in each of
`system_response`, `system_claim`, `system_matrix_row`, `system_timeline_event`, and
`system_bundle`. One index is one contract, one fetch, one cache, and leaves every
existing response schema untouched.

## Component 2 — Vocabulary

### Contract

New projection `factory.system vocabulary --json`, served at
`GET /api/system/vocabulary`. A static, versioned table held in one Python module.

```
{
  "version": 1,
  "terms": {
    "<term>": {
      "term": "recorded",
      "group": "claim-kind",
      "gloss": "straight from a file, not inferred",
      "definition": "Copied verbatim out of an artifact file. Nothing was computed or written by a model.",
      "siblings": ["derived", "synthesized", "missing"],
      "computed_by": "src/factory/system/_claims.py"
    }
  }
}
```

`gloss` is at most eight words and renders inline. `definition` is one to three
sentences and renders in the card. `computed_by` names the module that decides the
value, so a reader can go and check.

### Coverage

The table covers every enumerated value the browser can display:

- Claim kinds — `recorded`, `derived`, `synthesized`, `missing`
- Freshness — `fresh`, `stale`, `degraded`, `n/a`
- Readiness — `weak`, `medium`, `strong`
- Readiness counts — `sr_total`, `bound`, `covered`, `current`, `deferred`,
  `validated`. Each has an exact predicate in `system/health.py:67`, and each
  definition states that predicate in words.
- Matrix statuses — `passed`, `failed`, `error`, `blocked`, `never-run`, `unknown`
- Timeline actors — `human`, `dev`, `review`, `validation`, `orchestrator`,
  `unknown`, `not-recorded`
- Timeline actions — `approved`, `rejected`, `validated`, `repaired`, `published`,
  `stopped`, `not-recorded`
- Citation kinds — `manifest`, `task`, `requirement`, `validation`, `review`,
  `decision`, `trace`, `bundle`, `session`
- Health class names — `task->plan`, `task->SR`, `plan->spec`, `SR satisfied`,
  `SR validated`
- Reverse-walk `stops_at` — `task`, `satisfies`, `null`
- Trace dispositions — `pending`, `exempt`, `deferred`, plus `proposed` and
  `dangling`
- Structural nouns — `bundle`, `scope`, `SR`, `BR`, `ADR`, `evidence run`,
  `evidence manifest`, `session record`, `claim`, `span`, `citation`

### Rendering

Badges keep their exact contract word. The browser and the CLI stay one language;
`system-cli.ts:53` and the badge text remain the same string.

Each badge gains:

- an inline `gloss` line beneath it, in the muted metadata size;
- an `ⓘ` control opening the definition card.

Health class labels gain a readable primary label — `task->plan` renders as
`Tasks linked to a plan` with `task->plan` demoted to the monospace metadata line.
The readable label lives in the vocabulary table under the class name, so Python
still owns the wording.

A `Vocabulary` control in the page header opens the full table as a panel, grouped
by `group`, reachable without a scope selected.

## Component 3 — Remediation

### Contract

New projection `factory.system remediation --json`, served at
`GET /api/system/remediation`. A static, versioned table keyed by state.

```
{
  "version": 1,
  "states": {
    "<state>": {
      "state": "sr_unsatisfied",
      "headline": "No task satisfies this requirement",
      "what_it_means": "…",
      "why_it_matters": "…",
      "command": "/trace-fix {ref}",
      "command_kind": "slash" | "shell",
      "severity": "absence" | "failure"
    }
  }
}
```

`{ref}` and `{id}` are the only substitutions; the browser performs them literally
with no other templating.

### Keys

The eleven `GapKind` values in `trace/gaps.py:9` — `task_no_sr`, `task_no_plan`,
`task_plan_missing`, `plan_no_spec`, `dangling_upstream`, `sr_unsatisfied`,
`sr_proposed`, `sr_unvalidatable`, `sr_unvalidated`, `sr_stale`,
`dangling_reference` — plus the browser-only absence states:

`no_runs`, `no_requirements`, `no_changed_files`, `no_commit_range`, `no_trace`,
`no_claims`, `no_matrix_rows`, `no_timeline_events`, `no_guide_sections`,
`no_bundles`, `no_description`, `traversal_not_applicable`,
`matrix_never_run`, `unbundled_artifact`.

### Command selection

A pi slash command where one covers the act; the explicit module invocation
otherwise. The available surface, verified on 2026-08-14:

- Slash commands: `/factory-init`, `/factory-doctor`, `/factory`, `/factory-run`,
  `/factory-tasks`, `/factory-stop`, `/factory-watch`, `/factory-context`, `/plan`,
  `/polish`, `/trace-fix`, `/review-plans`, `/system`, `/goal`, `/visual-explain`,
  `/remember`
- Module invocations: `uv run python -m factory.requirements {new,bind,defer}`,
  `uv run python -m factory.trace {link,exempt,defer}`,
  `uv run python -m factory.doctor {mint,promote}`,
  `uv run python -m factory.system {bundle,coverage,check}`

`command_kind` distinguishes the two so the renderer can label the block
`Run in the coding agent` or `Run in a terminal` accurately.

### Rendering

Every empty state, every `missing` claim, every `not recorded` value, and every
`never-run` matrix row renders a **Next step** block: the headline, one sentence of
`what_it_means`, one sentence of `why_it_matters`, then the command in the monospace
face with a copy button. Copy writes to the clipboard and confirms in place; there is
no execution path.

## Component 4 — Layout, severity, and first run

### Scope heading inversion

`setScopeHeading` currently sets the heading to `bundle?.label || scopeRef`, which
yields `task:T-001` for every non-bundle scope. It becomes: the label index title as
the heading, the ref as the monospace metadata line beneath it, the kind eyebrow
unchanged, and the description rendered as the lead paragraph when recorded.

### Sidebar

Unbundled rows render `refChip` output on two lines — id and status on the first,
title on the second, clamped to two lines. The rail's 320 px is then carrying
information proportional to its width.

### Evidence grid

Above 1200 px the workspace becomes two columns: panel content on the left, and a
persistent context rail on the right carrying the scope summary, readiness beside its
counts, membership, and the current Next step. Below 1200 px the rail collapses above
the content in the existing single-column flow. Below 760 px the existing mobile
layout is unchanged.

### Severity

`renderDegradedBanner`, `renderBrief`, `renderTimeline`, `renderStory`, and
`renderReverse` currently render one red `degraded:` banner for both real failures and
mere absences. They split by the `severity` field of the matching remediation entry:

- `failure` — a load error, a parse failure, a broken reference. Red, unchanged.
- `absence` — nothing recorded yet. Neutral surface with the amber attention rail,
  the state named in text, and its Next step block.

Text always names the state; colour never carries meaning alone.

### First run

With zero bundles, the feature directory currently renders its `FEATURE DIRECTORY /
Browse by readiness` heading followed by nothing at all. It gains a first-run card
explaining what a bundle is, why the directory is the primary axis, and the command
that creates one.

The landing gains a dismissible three-sentence orientation strip stating what the
navigator is for and linking to the vocabulary panel. Dismissal is held in
`localStorage` under one key. This is the single exception to the "no user preference
storage" non-goal of the visual identity design, and it is recorded here as such: an
orientation strip that cannot be dismissed becomes noise on the second visit.

## Component 5 — Bundle description field

`system_bundle.schema.json` gains an optional `description` string with
`maxLength: 280`. `BundleDeclaration` gains `description: str | None`, parsed in
`bundles.py` and surfaced through `health`'s bundle rows and the label index.

**Boundary, recorded deliberately.** `models.py:215` states a bundle carries "a label
and exact member refs only — no status, no claims, no rationale", and the program
decomposition ruled that bundle rationale lives in an ADR. That ruling stands. The
`description` field states *what the feature is*; it does not state *why the cut was
made that way*. The 280-character cap is the mechanism that keeps the distinction
enforceable rather than advisory, and the schema's own `description` annotation says
so. Rationale continues to live in `docs/adr/0003-feature-bundle-map.md`.

Existing bundle files remain valid. A bundle without a description renders
`no description recorded` plus its Next step.

## Error handling

Each of the three new projections degrades independently and non-fatally:

- **Labels unavailable** — chips render bare refs with the visible note
  `label index unavailable`. Every other part of the page is unaffected.
- **Vocabulary unavailable** — badges render their contract word with no gloss and no
  `ⓘ`. No layout shift beyond the missing line.
- **Remediation unavailable** — empty states render their existing text without a Next
  step block.

No projection failure blanks the page, and none blocks another. Each renders a single
retry control consistent with the existing health-load treatment.

## Verification

### Python

- Unit tests per projection over a fixture repository: label extraction per kind,
  `description_source` correctness, `null` handling, and ref-absent behaviour.
- **Completeness tests.** One test asserts every value of every enum in
  `system-cli.ts`'s type unions and `trace/gaps.py`'s `GapKind` has a vocabulary
  entry; a second asserts every gap kind and every browser-only absence state has a
  remediation entry. A new state cannot ship undefined.
- A test asserting every `command` in the remediation table names either a registered
  slash command or an existing `factory.*` subcommand, so the table cannot drift from
  the CLI.

### TypeScript (jsdom)

`refChip` output structure; card open on hover, focus, and tap; `Escape` closes and
returns focus to the trigger; copy button behaviour; each empty state rendering its
Next step; severity split between `failure` and `absence`; scope heading inversion;
two-column grid present above 1200 px and absent below; first-run card with zero
bundles; degradation paths for each of the three projections.

### Browser

A Playwright pass at 1440×900, 1024×768, and 390×844 against a populated fixture
repository and against this repository's zero-bundle state, checking: no console
errors, no horizontal page overflow, cards reachable by keyboard and by tap, contrast
of the new muted gloss text, and `prefers-reduced-motion` respected by the card
transition.

**Harness note.** Serving the extension through `tsx` injects esbuild's `keepNames`
`__name` helper into the function bodies that `system-shell.ts` stringifies into the
inline page script, producing `ReferenceError: __name is not defined` in the browser.
This is an artifact of the verification harness, not of the shipped page. The harness
defines `window.__name = (fn) => fn` before navigation. Any future browser check must
carry the same shim or it will report a false failure.

## Non-goals

- Write actions of any kind. SP-C owns remediation execution; this surface displays
  commands only.
- Changes to `system_response`, `system_claim`, `system_matrix_row`, or
  `system_timeline_event` schemas.
- Model-written summaries, scores, or judgments anywhere on the surface.
- Changes to `/review-plans`, the docs browser, or mission control.
- A frontend framework, build step, remote font, image, or icon package.
- A theme chooser. The one `localStorage` key is the orientation strip's dismissal,
  recorded in Component 4.
- Description extraction for `br`, `feat`, `metric`, `goal`, `run`, and `diag` kinds.
