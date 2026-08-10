# Review browser: task context and focusable panes

The browser code-review surface shows a diff and a stub of a task. It does not
show what the task was supposed to accomplish, and its layout cannot be
reshaped to read either side properly. This design makes the review page a
consumer of the system-navigator loaders that already answer both halves of
that question, and replaces the fixed three-column grid with collapsible,
zoomable panes.

## Problem

`review-html.ts` renders a task panel from `readTaskContext`, which reads
`tasks/T-*.md` and renders the whole file. A real task file body is a pointer,
not a task:

```
- Create: `src/factory/orchestrator/skills.py`
- Test: `tests/unit/orchestrator/test_skills.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 1.
```

The steps the implementer actually worked from live in `### Task 1` of the
source plan. The browser never opens it — `parseTaskFrontmatter`
(`task-header.ts:22`) does not even parse `source_plan` or `source_task`. The
reviewer approves a diff against a filename reference.

The layout compounds it. `body` is a hardcoded
`grid-template-columns: 240px 1fr 320px` with the task as a full-width band
capped at `max-height: 35vh` (`review-html.ts:8,24`). The only control is a
single `<details>` toggle, and even open the task cannot exceed 35vh. There is
no way to give the task the window, hide the file tree, or widen the diff.

Nothing persists across reviews: pane sizes, the reviewed-file checkboxes, and
comments are all in-memory.

## What already exists

The repo already answers "what was this for" twice, and the review page calls
neither.

| Need | Existing answer |
|---|---|
| Task's chain to its requirement | `loadSystemStory(cwd, "task:T-001")` — `system-cli.ts:292` |
| Why a changed file exists | `loadSystemReverse(cwd, "file:src/x.py")` — `system-cli.ts:297` |
| Node + edges + neighbours + freshness + evidence | `system_context` tool — `system-context-tools.ts:69` |
| Scope refs `task:`, `file:`, `sr:`, `bundle:` | `parse_scope_ref` — `queries.py:89` |

`query_story`'s docstring is "open a task, see how it was implemented";
`query_reverse`'s is "open a file, see where it came from" — the two halves of
the V-cycle. The review browser is the one surface that needs both.

Building a new `factory.trace context` subcommand was considered and rejected:
it would be a third implementation of a walk the navigator already owns.

## Architecture

```
buildReviewPageData(cwd, startCommit, files, {taskId})
  |- loadSystemStory(cwd, "task:" + taskId)      EXISTING binding
  |     `- query_story -> task, requirements[], runs[], + NEW plan_section
  |- buildSystemContext(cwd, taskId)             EXTRACTED from system_context
  |     `- loadTraceGraph -> nodes + edges       EXISTING, one subprocess
  `- walkIntentChain(graph, taskId)              NEW, pure, no I/O

GET /api/why?file=<path>                         lazy, on file click
  `- loadSystemReverse(cwd, "file:" + path)      EXISTING binding
```

`loadSystemReverse` is called lazily per file rather than eagerly for all
files: a thirty-file review would otherwise spawn thirty `uv run` subprocesses
before the page renders.

### Components

**`plan_to_tasks.py` (modified).** `ParsedPlanTask` gains `body: str`, the raw
section text between one `### Task N:` header and the next. `parse_plan_tasks`
gains fenced-code-block stripping, which closes the open task
`T-020`. This is not optional polish: the parser currently finds 19 sections in
`2026-07-20-factory-plan-and-run.md` for 16 real tasks, numbered
`[1,2,3,4,5,6,7,1,2,1,8,...]`, because a markdown fixture inside a fence
contains its own `### Task 1:` headers. `source_task: 1` therefore does not
uniquely address a section.

**`story.py` (modified).** `query_story`'s returned dict gains
`plan_section: {plan_path, heading, body} | null`, resolved through
`parse_plan_tasks` so the `### Task N:` grammar keeps exactly one owner. The
section is matched **by task title first, `source_task` number as fallback** —
correct both before and after the fence fix. `null` when the task declares no
`source_plan`, the plan file is missing, or no section matches.

**`system-context.ts` (new).** `buildSystemContext(cwd, id, deps)` lifted
verbatim out of `system_context`'s `execute`
(`system-context-tools.ts:86-119`). The tool becomes a thin caller; the review
server becomes a second one. Neither composes graph, freshness, and evidence on
its own.

**`review-intent.ts` (new, pure).** `walkIntentChain(graph, taskId)` walks the
already-loaded graph — no additional subprocess and no I/O, so it is unit
testable without `uv`. It follows only the edges `extract_edges` writes
(`model.py:133-150`):

```
task --satisfies--> SR --upstream--> BR
task --source_plan--> plan --spec_ref--> spec
```

It returns the resolved hops and a `stopsAt` naming the first hop that did not
resolve, copying `reverse.py`'s stated discipline: never guess past an
unresolved hop, stop and say where.

**`review-layout.ts` (new, pure).** A reducer over pane state —
`toggle(pane)`, `zoom(pane)`, `restore()` — returning a grid column template.
Pure, so the focus model is tested without a browser.

**`review-server.ts` (modified).** Composes the above into `ReviewPageData` and
serves two new endpoints: `GET /api/why?file=` and `POST /api/layout`.

**`review-surface.ts` (modified).** Gains `readLayoutPref`/`writeLayoutPref`
beside `readSurfacePref` (`review-surface.ts:22`), same best-effort,
never-throw contract, same `sessions/.factory-review-surface.json` file.

**`review-html.ts` (modified).** The layout rewrite.

### Data model

```ts
export interface ReviewChainNode {
  id: string;          // "T-001", "plan:2026-07-20-....md", "spec:....md", "SR-014"
  kind: TraceNodeKind; // br | sr | spec | plan | task
  title: string;
  path: string;
}

export interface ReviewIntent {
  chain: ReviewChainNode[];        // BR -> SR -> spec -> plan -> task, resolved hops only
  stopsAt: string | null;          // first unresolved hop, e.g. "satisfies"
  planSection: { planPath: string; heading: string; html: string } | null;
  dod: string[];
  status: string;
  requirements: string[];          // straight from query_story
}
```

`ReviewPageData` gains `intent: ReviewIntent | null`. `status` and `dod` are
duplicated with the existing `ReviewTaskContext` deliberately: the intent
copies come from `query_story` through the ledger, and the task-context copies
come from reading `tasks/T-*.md` directly. The pane prefers the intent copy and
falls back to the file copy, which is what keeps the panel useful when the
navigator is unavailable. They are not merged, because a divergence between
them is itself worth seeing.

`planSection.html` comes from `renderMarkdown`, the same trusted renderer the
existing task panel and `/review-plans` use; it escapes source before emitting
markup. No server data reaches the page through `innerHTML` by any other route.

## Intent pane

Top to bottom: the chain, then status and the DoD checklist, then the resolved
plan section. Only resolved hops render; an unresolved one renders as a single
`stops at: <hop> (<reason>)` line rather than empty scaffolding.

In this repo today, `requirements/` does not exist and no task carries
`satisfies:`, so the walk stops at `satisfies` and the chain renders
`spec -> plan -> task`. This is the designed behaviour, not a degraded mode:
the BR and SR rows appear when requirements exist, and say plainly that they do
not until then.

## Layout and focus

Four panes — `context`, `tree`, `diff`, `comments` — in one grid driven by
`review-layout.ts`, replacing the hardcoded `240px 1fr 320px` and the 35vh
band. Context becomes a real column rather than a band, so zooming it gives the
plan prose the whole window.

- Each pane header carries a collapse chevron; collapsing shrinks it to a thin
  labelled rail and the others reflow to fill.
- `1`-`4` zoom one pane to the full window; `Esc` restores; `?` shows the key
  map.

**Persistence must be server-side.** `localStorage` cannot work here:
`server.listen(0)` (`review-server.ts:153`) binds a random port, so every
review is a new origin and the layout would silently reset each time. The page
`POST`s pane state to `/api/layout`, which persists it through
`writeLayoutPref`.

## Degradation

Every added source is optional and fails independently. The review must stay
approvable when the whole navigator is unavailable — a diff that cannot be
signed off is worse than a diff without context.

| Failure | Result |
|---|---|
| `loadSystemStory` fails | Chain and plan section drop; the task panel still renders from disk as today |
| `loadTraceGraph` fails | Chain drops; plan section survives via story |
| `plan_section` is null | Chain and DoD render; a line states no plan section resolved |
| `/api/why` fails | Inline "no recorded evidence for this file"; the diff pane is unaffected |
| `/api/layout` write fails | Layout works for the session, is not remembered |

Errors surface the reason rather than an empty pane, following
`system-context-tools.ts:60`: missing evidence is unknown, never inferred.

## Testing

- `walkIntentChain`: pure unit tests over graph fixtures — both branches, each
  partial chain, every `stopsAt` case.
- `review-layout.ts`: pure unit tests for toggle, zoom, restore, and
  collapse-all.
- `parse_plan_tasks`: fence-stripping cases including the real
  `2026-07-20-factory-plan-and-run.md` shape that currently yields duplicate
  task numbers, plus `body` extraction.
- `query_story`: `plan_section` resolves by title, falls back to number, and is
  `null` for a task with no `source_plan`; survives the `--json` round trip.
- `buildReviewPageData`: injected fake loaders covering each degraded path.

## Out of scope

- Persisting comments and reviewed-file checkboxes across reviews. Real gap,
  separate change.
- Populating `requirements/`. This design renders the rows when they exist.
- The terminal review overlay (`review-overlay.ts`). It keeps its current
  behaviour; only the browser surface changes here.
