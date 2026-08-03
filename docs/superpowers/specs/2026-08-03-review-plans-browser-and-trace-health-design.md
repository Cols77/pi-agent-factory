# Design: Browser Surface for `/review-plans` + Traceability Health

**Date:** 2026-08-03
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

`/review-plans` today (`pi-ext/factory-watch/src/index.ts:492`) lists specs, plans
and tasks in a flat `ctx.ui.select` picker and opens the chosen one in a
`ScrollableMarkdown` TUI overlay. It reads one document at a time, with no way to
move to a related document without closing and reopening, and no view of how any
document relates to any other.

That is a poor fit for the artifacts this repo actually produces. Measured across
all 47 specs/plans and 45 tasks — **36,949 lines**:

| feature | count | consequence |
|---|---|---|
| fenced code blocks | 960 (python/bash/typescript) | dominant element; must render literally |
| bullets | 3,315 | |
| task checkboxes `- [ ]` / `- [x]` | 1,099 | plans are executable checklists — **plan % complete is derivable** |
| ATX headings | 890 (~19/doc) | **an auto-TOC per document falls out of the same parse** |
| bold | 2,550 | |
| hrules / table rows / ordered items / blockquotes | 370 / 210 / 170 / 63 | all required |

The largest plan is **102 KB** (`docs/superpowers/plans/2026-07-20-factory-plan-and-run.md`).
That document is not realistically readable through a terminal line-scroller.

Meanwhile the relationships between artifacts are recorded on disk but rendered
nowhere: `tasks/T-*.md` carry `source_plan:` and `satisfies:`, `requirements/SR-*.md`
carry `upstream:` and a `binding:`, and `validation/validation-report.json` carries
the pass/fail truth of every requirement that has been run.

### 1.1 Goals

- A **browser surface** for `/review-plans`, alongside — not replacing — the
  existing TUI surface: rendered markdown, per-document TOC, plan progress, and a
  sidebar of every artifact.
- A **traceability view**: each document shows its declared neighbours as
  navigable links, and a landing map shows the whole artifact graph.
- **Validation traced into the graph**: every SR node carries its real state, and
  opening one shows the evidence behind it.
- A **traceability health measure** and a **workflow for improving it** —
  detecting gaps is only useful if there is a path to closing them.

### 1.2 Non-Goals

- **The viewer is not an editor.** It is a strictly read-only presenter. All writes
  go through the `factory trace` CLI (§6).
- **No inferred edges.** See §4 — the invariant is absolute.
- **No changes to orchestrator pipeline behaviour.** This design adds a new
  `factory trace` CLI package, but touches no existing node, role, or gate.
  Preventing *new* gaps (gating `factory-run`, teaching `writing-plans` to emit a
  spec key) is deliberately excluded and belongs in its own spec. See §9.
- **No result history.** `validation-report.json` is overwritten each run
  (`src/factory/validation/report.py:63-70`), so history does not exist on disk and
  manufacturing it would require changing the factory.
- **No syntax highlighting** of the 960 code blocks. They render literally.

---

## 2. Ownership: Python owns the model, TypeScript presents it

The extension already shells out to Python and consumes structured output —
`pi-ext/factory-watch/src/process-control.ts:13` runs
`uv run python -m factory.orchestrator run`, and `:36` consumes `list --json`.
This design follows that established idiom rather than introducing a second one.

Consequently:

- **Python** owns the artifact graph, the gap rules, the health score, and every
  write. One source of truth. Writes reuse `python-frontmatter` exactly as
  `src/factory/polish/routing.py:41-46` already does, so there is never a second
  YAML frontmatter serializer.
- **TypeScript** owns presentation only: markdown rendering, TOC, graph layout,
  the HTTP server, and the page. It holds no traceability rules.

The alternative — TypeScript computing gaps for the viewer while Python computes
them for the CLI — would place the same rules in two languages and let them drift.

---

## 3. Architecture

```
/review-plans [--browser|--terminal|--stop]
    |
    +-- terminal surface: existing ScrollableMarkdown path, unchanged
    |
    +-- browser surface:
          ensure singleton docs server (127.0.0.1, ephemeral port)
          openInBrowser(url); ctx.ui.notify(url)
          RETURN IMMEDIATELY  <- session is never blocked
                |
                v
        GET /               -> shell page (inline CSS+JS, zero runtime deps)
        GET /api/graph      -> spawnSync `uv run python -m factory.trace graph --json`
        GET /api/doc?path=  -> read file (path-validated), render markdown -> {html, toc, progress}

        every request rebuilds from disk; no cache
```

`/api/graph` spawns the Python CLI **once per request**, so a refresh always shows
current truth — a task flipping to `done` mid-run appears immediately, with no
cache to invalidate. The cost is one subprocess (~hundreds of ms) per graph load,
which is acceptable for a human-paced reading tool and keeps the server stateless.
Document reads do not spawn anything.

```
factory trace status [--json]      -> health score + gap inventory
factory trace graph --json         -> nodes + edges + gaps + validation state
factory trace link <id> --satisfies SR-### | --spec <path>   -> deterministic write

/trace-fix  -> seeds a pi session with the trace-fix skill:
               propose a link from evidence -> human confirms -> `factory trace link` writes
```

---

## 4. The traceability model (`src/factory/trace/`)

Mirrors the structure of the existing `src/factory/requirements/` and
`src/factory/validation/` packages (`__main__.py` + `cli.py` + logic modules).

### 4.1 Nodes

`br` | `sr` | `spec` | `plan` | `task`, sourced from `requirements/SR-*.md`,
`requirements/BR-*.md`, `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`,
`tasks/T-*.md`.

### 4.2 Edges — declared only

| edge | source | declaration |
|---|---|---|
| task → plan | `source_plan:` frontmatter | exact path |
| task → SR | `satisfies:` frontmatter | exact ids |
| SR → BR/SR | `upstream:` frontmatter | exact ids |
| plan → spec | a literal `docs/superpowers/specs/….md` path written in the plan body | a written path is a declaration, not a guess |

**Invariant: nothing appears in the graph unless it is declared on disk.**

Explicitly rejected: matching `2026-07-30-sim-testbench.md` to
`2026-07-30-sim-testbench-design.md` by filename or date similarity. It fabricates
edges that render as authoritative and breaks silently on rename. The `/trace-fix`
workflow (§6) may *propose* such a link, but it becomes an edge only once a human
approves it and it is written to disk — at which point it is declared, not inferred.

### 4.3 Gaps

Everything undeclared is reported as a gap, never as a guessed edge:

- a task declares no `satisfies:`
- a task's `source_plan:` points at a missing file
- a plan references no spec path
- an `upstream:` id has no corresponding file (today: `SR-001 → BR-002`)
- an SR is absent from the validation report (**never validated** ≠ failed)
- an SR is `stale`

### 4.4 Exemptions

Not every task implements a system requirement; tooling and infrastructure tasks
legitimately satisfy none. Without an escape hatch the score could never honestly
reach 100%, and a metric that cannot be satisfied gets ignored.

A **task or plan** may therefore declare `trace_exempt: true` in its frontmatter.
That removes its expected slots and is counted and displayed separately as
*exempt*. An exemption is itself an explicit declaration on disk, consistent with
§4.2 — it is not a silent skip. SRs are not exemptable: a requirement that no task
satisfies and no run validates is a real gap, not an exception.

### 4.5 Health score

Per-class coverage of satisfied expected slots, plus a plain unweighted overall
ratio. Expected slots:

| artifact | expects |
|---|---|
| task | 1 `source_plan` + ≥1 `satisfies` |
| plan | ≥1 spec reference |
| SR | ≥1 satisfying task + 1 validation result |
| spec, BR | nothing — they are roots |

`upstream:` is **not** a slot: a top-level SR legitimately has no parent, and
penalising that would be wrong. A *dangling* `upstream:` is still a defect and is
reported as such.

Dangling references and exemptions are listed as counts, never folded into the
percentage. There are no tunable weights, deliberately — a weighted score invites
arguing with the number instead of closing the gap.

Current state of this repo, for calibration: task→plan 45/45, task→SR **0/45**,
plan→spec 10/26, 1 dangling reference.

---

## 5. Validation in the graph (`validation-status`)

Joins `validation/validation-report.json` to SR nodes by `id` — deterministic, no
inference. Composes the existing `factory.requirements.register` and
`factory.validation` modules rather than re-reading the formats.

Five states, from `src/factory/validation/report.py:46-59`:

| state | source |
|---|---|
| passed | `passed: true` |
| failed | `passed: false` |
| error | `error` key present (the harness itself raised) |
| never validated | id absent from the report |
| **stale** | `stale: true`, **orthogonal to passed** |

`passed: true, stale: true` means *green, but the requirement's statement or
binding changed since that green was earned* (`report.py:56` ← `is_checksum_current`).
It renders as a warning state, never as plain green. It is the most dangerous
state in the system and currently renders nowhere at all.

Opening an SR shows the evidence: metric value vs `assert`, actual vs
`declared_trials`, report freshness from file mtime, and links to trace artifacts.

---

## 6. Improving traceability health

Detection alone does not improve anything. The fix workflow mirrors `polish`
(`.pi/skills/polish/SKILL.md`, `src/factory/polish/routing.py`) — gather human
input, **confirm**, then route deterministically into the ledger.

### 6.1 A deterministic workflow, not a skill that hopes

A markdown skill is a *suggestion* to a model. "Every gap was discussed" is exactly
the kind of claim a model will assert without having done it, and a skill cannot
enforce its own completion.

An LLM cannot be made deterministic. A *workflow* can, by moving **enumeration,
state, writes, and verification into code** and constraining the model to a single
judgment per step:

| concern | owner |
|---|---|
| which gap comes next | `factory trace next` — deterministic ordering |
| candidate targets + evidence | `factory trace next` — deterministic retrieval and ranking |
| **which candidate is right, and why** | **the LLM — the only judgment in the loop** |
| accept / reject / defer | the human |
| the write | `factory trace link\|exempt\|defer` |
| did we cover everything | `factory trace check` — the gate |

The model never decides when the loop ends, never records its own progress, and
never writes a file.

### 6.2 Dispositions live in frontmatter

Every gap resolves to one of four states, and the first three are **declarations on
disk**, consistent with §4.2 — not entries in a side ledger that can drift from the
files it describes:

| disposition | representation |
|---|---|
| linked | `satisfies:` / spec reference now present — the gap ceases to exist |
| exempt | `trace_exempt: true` (+ reason) |
| **deferred** | `trace_deferred: "<reason>"` — discussed, needs more time |
| pending | nothing written — **the gate fails on these** |

`deferred` is a first-class outcome, not a failure. Some gaps genuinely need
investigation that does not fit in the current session; forcing a wrong link to
clear a counter would be worse than recording an honest deferral. A deferred gap
stays visible and counted in the inventory forever — it is never silently gone —
and the next run resumes it with its reason rather than re-litigating it.

### 6.3 The gate

`factory trace check` exits non-zero when any gap is `pending`, listing them. It is
**stateless**: it re-derives every gap from disk and re-reads every disposition,
rather than trusting a session log. A model cannot satisfy it by claiming to have
done the work — only the files can satisfy it.

It exits zero when everything is linked, exempted, or deferred — "at least
discussed" — and reports the breakdown so *better fixed* stays visible: deferrals
are surfaced as warnings with their reasons, never as a pass to be proud of.

### 6.4 Surfaces

- **`factory trace link <id> --satisfies SR-### | --spec <path>`** — the only
  writer of links. Validates the target exists first, so a confirmed link can never
  create a fresh dangling reference.
- **`.pi/skills/trace-fix/SKILL.md`** — deliberately narrow: reason about *the one
  gap the CLI just handed you* and recommend a candidate with its evidence. It owns
  no iteration and no bookkeeping.
- **`/trace-fix`** — seeds a session with that skill, mirroring `/plan` at
  `index.ts:455-490`, and runs the gate at the end.

The proposal step is the only place inference exists in this design. It is always
surfaced for approval, never persisted without it, and never becomes an edge until
it is written to disk — at which point it is declared, not inferred.

---

## 7. Presentation (`pi-ext/factory-watch/src/`)

New, pure, fully unit-testable:

| module | responsibility |
|---|---|
| `md-render.ts` | `renderMarkdown(src) → {html, toc, progress}` — one parse, three outputs |
| `graph-layout.ts` | layered SVG layout: rank = node type, barycenter pass for within-rank ordering |

New, impure: `docs-server.ts` (routes + singleton lifetime), `docs-html.ts` (inline
shell), `trace-client.ts` (spawn the Python CLI, parse JSON, handle failure).

Changed: `index.ts` (command registration), and `review-surface.ts` gains an
**optional** key parameter — defaulting to today's value so existing review callers
and their tests are untouched — so docs and code review remember their surfaces
independently. Choosing browser for a code review should not silently redirect
where you read documents.

**Markdown renderer.** Hand-rolled in TypeScript, covering exactly the feature set
measured in §1: headings, fenced code (literal), bullets, task checkboxes, ordered
lists, tables, blockquotes, hrules, emphasis, inline code, links. `package.json`
declares **zero runtime dependencies** — everything is `devDependencies` — and
vendoring a markdown library to build a viewer would break that property. Input is
HTML-escaped before any markup is emitted.

**Layout.** The graph is layered *by node type* (BR → SR → task → plan → spec), so
rank assignment is free and only within-rank ordering needs a heuristic. This is a
bounded pure function, not a layout engine.

### 7.1 Screens

- **`/` — landing map.** The full graph as an orientation view, filterable by node
  type and validation state so ~92 nodes stays legible. Clicking a node opens it.
- **`/doc/<id>` — reader.** Sidebar of all artifacts, rendered markdown with TOC
  and (for plans) checkbox-derived progress, and a trace panel carrying the
  document's declared neighbours, its gaps, and a mini-map scoped to its 1-hop
  neighbourhood — the same layout component at a smaller scope.
- **Health panel.** Per-class coverage, overall score, gap inventory, exemption and
  dangling-reference counts.

---

## 8. Error handling

| condition | behaviour |
|---|---|
| port bind fails | notify and fall back to the TUI surface (mirrors `index.ts:153`) |
| `uv`/Python unavailable or CLI non-zero | the graph and health panes show the error; the **document reader still works**, since it reads files directly |
| malformed SR/task frontmatter | that node degrades to a filename label, never a crash (matches `doc-lister.ts:26`) |
| no `validation-report.json` | every SR is *never validated*, not *failed* |
| document deleted between listing and opening | 404 rendered in the pane; the server survives |
| empty repo | the map renders its empty state, not an error |
| `--stop` with no server running | no-op with a notice |

**Path traversal.** `/api/doc?path=` resolves against the repo root and rejects
anything outside it. Loopback binding is not by itself an authorization boundary —
any process on the machine can reach the port.

---

## 9. Cross-plan dependencies and deferred work

Consumes unchanged: `review-surface.ts`, `doc-lister.ts` (extended to list
`requirements/SR-*.md`, which it does not today), `factory.requirements.register`,
`factory.validation`, and the `uv run python -m factory.*` invocation pattern.

**Deferred to its own spec — preventing new gaps.** Nothing here stops fresh gaps
appearing: `factory-run` could warn when a task closes declaring no `satisfies:`,
and `writing-plans` could emit a `spec:` frontmatter key so plan→spec becomes
structured rather than recovered from prose. Both change factory and skill
behaviour rather than adding a viewer, so both are out of scope here.

**Honest expectation for the landing map.** With 0 tasks currently declaring
`satisfies:` and no structured plan→spec edges, the first render draws 45 tasks
above 26 plans and little else. The map becomes valuable as `/trace-fix` closes
gaps; until then the **health panel and gap inventory carry the value**, not the
picture. This is a reason to sequence the map last (§10), not a reason to skip it.

---

## 10. Increments

1. **`factory trace`** — model, edges, gaps, exemptions, health score,
   `status`/`graph --json`. Valuable alone as a CLI health report.
2. **`md-render.ts`** — HTML + TOC + progress.
3. **Server + shell + document reader** — sidebar, TOC, trace panel, health and gap
   panes. Shippable without any graph drawing.
4. **`graph-layout.ts`** — landing map + 1-hop mini-map.
5. **`factory trace next|link|exempt|defer|check` + `trace-fix` skill + `/trace-fix`**
   — close the loop, with the gate.

Increment 1 must precede all others. Increments 2-3 and 5 are independent of 4.

These are separable enough that implementation may reasonably split into more than
one plan — increments 1 and 5 are Python and increments 2-4 are TypeScript — in the
same way the requirement-validation spec produced `inc1a`, `1b` and `1c`. They stay
in one spec because they share a single model, and splitting the model across specs
is what would cause drift.

---

## 11. Testing strategy

- **Python** (`factory.trace`): graph construction, all four edge rules, every gap
  class, exemption handling, and health arithmetic — pure-function tests with
  `tmp_path` fixtures, per the existing convention in `tests/unit/`. `trace link`
  gets round-trip tests asserting frontmatter is written correctly and that
  linking to a non-existent target is refused.
- **Validation states**: all five, explicitly including `passed: true, stale: true`.
- **TypeScript**: markdown/TOC/progress rendering and layout arithmetic as pure
  unit tests (vitest, tmp fixtures, per this extension's existing pattern). Server
  routes tested by binding port 0 and fetching, **including a path-traversal
  rejection case**. `trace-client.ts` tested against a stubbed failing subprocess.
- **Manual verification, not inferred from unit tests**: actual browser rendering,
  the non-blocking property (the pi session stays usable while the tab is open),
  and `/trace-fix`'s interactive confirmation loop.
