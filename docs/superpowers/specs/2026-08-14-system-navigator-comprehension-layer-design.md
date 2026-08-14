# System Navigator Comprehension Layer Design

**Date:** 2026-08-14
**Status:** Approved by the user through brainstorming on 2026-08-14.
**Revision:** 2 — incorporates an independent verification review of revision 1
(2026-08-14). Every change made in response is listed in "Review resolutions".
**Surface:** `/system` only (the System Navigator). No other browser surface changes.

## Purpose

`/system` renders the factory's evidence correctly and explains it to nobody. Every
number, badge, and reference on the page is accurate, and most of them are unreadable
without knowing the codebase that produced them.

Measured against `cool_physical_ai_project` (182 requirements, 44 tasks, 14 bundles)
on 2026-08-14 at 1440×900:

- Opening `bundle:reactive-planner` renders its traversal spine as
  `SR-030, SR-033, SR-038, SR-086, SR-087, SR-088, SR-089, SR-095, SR-096, SR-097,
  SR-100, SR-101, SR-166, SR-167, SR-168` → `T-055, T-066, T-069, T-059, T-068,
  T-058` → **`Not recorded`** → nineteen wrapped file paths. Fifteen identifiers, no
  titles, no way to know what any of them is.
- The landing shows `SR satisfied 102/181` beside `SR validated 1/43`. Nothing
  explains why the denominators differ, or what either verb means.
- All fourteen bundles are `WEAK`, so the readiness axis discriminates nothing; the
  counts beside it do the real work and are unexplained.
- Sidebar rows concatenate label and counts into one wrapping paragraph:
  `Deterministic safety governor 15 SR · 14 bound · 15 covered · 14 current ·
  1 deferred · 0 validated`, over three lines, with no separation between the
  feature's name and its numbers.

Measured against this repository (zero bundles) on the same day:

- Opening `task:T-001` renders `task:T-001` as the 40 px page heading. The task's real
  title — `` `load_skill_block` -- pure hard skill loading (Python) `` — is 14 px body
  text inside the Story panel.
- That page shows a red `degraded:` banner whose sole reason is "task has no recorded
  runs". An absence is rendered as a failure.
- "Traversal is not applicable for this scope.", "No recorded runs for this task." and
  "no requirements recorded" are three dead ends with no next step from any of them.
- The feature directory renders its heading and nothing at all.
- Roughly 900 px of horizontal canvas beside that content is empty.

This design adds the layer that makes the surface self-explanatory: what every word
means, what every reference is, and what to do about every gap.

## Principles preserved

- **Python computes; the browser renders.** Titles, descriptions, definitions and
  remediation are computed in Python. TypeScript renders them and performs no
  interpretation, no ref parsing, no sorting, no synthesis.
- **The browser stays read-only.** It displays commands; it never executes them.
  Write operations remain SP-C's scope.
- **Nothing is synthesized.** Every description shown is verbatim recorded text from a
  single named field. Where no such field exists, the surface says so and offers the
  command that would record it. A model-written summary would be a `synthesized` claim
  under this system's own vocabulary, and placing one inside the affordance meant to
  establish trust would defeat it. **This rules out composing a description from
  several fields and attributing it to one of them.**
- **No new dependency.** Vanilla TypeScript and DOM, inline assembly, no framework, no
  remote font, image, or icon package.

## Vocabulary of this document

"Ref" means a scope reference string as it appears in payloads: `task:T-001`,
`sr:SR-121`, `bundle:reactive-planner`. "Bare id" means an unprefixed identifier as
several payloads emit today: `SR-121`, `T-060`. "Chip" means the rendered inline
representation of a ref. "Card" means the popover attached to a chip or badge.

---

## Component 1 — Label index

### Ref normalization (Python, mandatory)

The repository carries two live spellings for document refs. `trace/model.py:86`
builds `spec:<basename>`; `system/coverage.py:70` builds `spec:<repo-relative-path>`.
`system/bundles.py:203` already documents that both spellings denote one file.

A new `factory.system.labels.normalize_ref(root, raw) -> str | None` is the single
place that resolves a raw ref or bare id to the canonical form. It is the only ref
parser this feature adds, and it lives in Python. **The browser never parses,
prefixes, or normalizes a ref.**

Canonical form is `<kind>:<id>` where `<id>` is:

- for `sr`, `br`, `task`, `adr`, `feat`, `metric`, `goal`, `diag` — the bare
  identifier (`SR-121`, `T-060`);
- for `spec` and `plan` — the repo-relative POSIX path;
- for `file` — the repo-relative POSIX path.

The index is emitted keyed by canonical ref, and additionally carries an `aliases`
map from every non-canonical spelling encountered (basename form, bare id) to its
canonical ref, so a lookup of either spelling resolves. An input that resolves to
nothing returns `None` and is rendered as unknown.

### Contract

New projection `factory.system labels --json`, served at `GET /api/system/labels`.

```
{
  "labels": {
    "<canonical-ref>": {
      "ref": "task:T-060",
      "id": "T-060",
      "kind": "task",
      "title": "Wire the safety governor into the planner loop",
      "description": "…verbatim recorded text…" | null,
      "description_source": "statement" | "decision" | "purpose" | "description" | null,
      "status": "done" | "todo" | "proposed" | … | null,
      "relations": {"satisfies": ["sr:SR-121"], "source_plan": ["plan:docs/…md"]},
      "path": "tasks/T-060-….md",
      "scope_href": "/system?scope=task%3AT-060" | null
    }
  },
  "aliases": {"spec:2026-07-16-foo.md": "spec:docs/superpowers/specs/2026-07-16-foo.md"},
  "degraded": []
}
```

### Openable scopes

`scope_href` is non-null only for kinds in `queries.py:74`'s `_SCOPE_KINDS` that also
have a tab configuration in `system-bootstrap.ts:351`'s `TABS_BY_KIND`. That
intersection is exactly **`bundle`, `sr`, `task`, `file`**.

`spec` and `plan` are *not* openable — the sidebar's `spec:…` rows are dead links
today and this design does not make them live. `adr`, `diag`, `feat`, `metric` and
`goal` parse as scopes but fall through to the bundle tab set and would render an
error page, so they are also `null` here. Making them openable is out of scope and
recorded as a known limitation.

### Sources

The projection composes existing loaders. It forks no parser and persists no index.

| Kind | Title | Description | Source field |
|---|---|---|---|
| `sr` | `Requirement.title` | `Requirement.statement` | `statement` — required (`requirements/register.py:12`), so an SR always has one |
| `adr` | `AdrDocument.title` | first paragraph of the section whose heading matches `^Decision$` case-insensitively, taking the first such section | `decision` |
| `spec`, `plan` | `Node.title` (`trace/model.py:31`) | first paragraph of the first matching **named section** — `Purpose`, `Goal`, `Problem`, `Overview`, `Summary`, matched case-insensitively in that order — or, for a plan, its `**Goal:**` label line | the heading or label actually matched, lowercased: `purpose`, `goal`, `problem`, … |
| `bundle` | `BundleDeclaration.label` | new optional `description` field (Component 5) | `description` |
| `task` | ledger `title` | **none** — see below | `null` |
| `br`, `feat`, `metric`, `goal`, `diag` | `Node.title` | none | `null` |
| `file` | the repo-relative path | none | `null` |

`run` is not listed: `trace/model.py:102` creates no `run` nodes, so no run ref exists.
A run id rendered by `renderStoryRun` and `renderReversePath` is displayed as a plain
monospace identifier, not a chip.

**Tasks have no recorded description, and none is invented.** `dod` is acceptance
criteria, not description: every task in `tasks/` ends its `dod` with the identical
`"All steps in this task complete; tests/gates pass; committed"`, and
`T-019-required-manual-verification.md` has *only* that entry. Composing a description
from `dod` plus body lines would also violate the verbatim-single-field principle
above, and would be falsely attributed. Instead a task's card carries its **recorded
relations** — `satisfies`, `source_plan`, `status` — which are real, single-sourced,
and answer "what is this for". Adding a first-class `description` field to the task
artifact is a reasonable follow-up and is explicitly out of scope here.

**There is no raw lead-paragraph fallback.** Revision 2 allowed "otherwise the first
non-empty paragraph after the H1". Measured against this repository on 2026-08-14 that
rule produced, for **all 53 plans**, the identical boilerplate
`> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development…`,
and for specs it produced the `Date:` / `Status:` / `Builds on:` metadata block. Both
are worse than nothing: they occupy the affordance meant to explain the artifact with
text that explains nothing and is identical across artifacts.

A lead paragraph is also not a named field, so reporting it as a description
contradicts this document's own verbatim-single-field principle. The fallback is
removed. Measured coverage under the named-section rule: 51 of 53 plans (via
`**Goal:**`), 10 of 43 specs (via `Purpose`/`Goal`/`Problem`). The remaining
documents carry `description: null` and render "no description recorded" with the
Component 3 next step — which is the honest state and an actionable one.

**`trace_deferred` is recorded remediation context.** A deferred requirement records
why in its own frontmatter — `cool_physical_ai_project/requirements/SR-002.md` states
that no candidate task covers energy-cost estimation, return-to-base selection, the
safety margin, and the 5% floor together. The index carries it as a distinct
`deferral_reason` field (never merged into `description`), and Component 3 renders it
above the generic remediation entry. A recorded reason always outranks the table.

### Rendering

One helper, `refChip(ref)`, replaces bare-ref and bare-id emission. The complete site
list, verified against source:

| Site | Today | Note |
|---|---|---|
| `system-renderers.ts:184` `renderMatrixRow` | `row.subject.ref` | already a proper `sr:` ref |
| `system-renderers.ts:237` `renderTimelineEvent` | `event.subject.ref` | proper ref |
| `system-renderers.ts:148` `renderBrief` | `member_of.join(', ')` | **bare bundle ids** |
| `system-renderers.ts:404` `renderStory` | `requirements` list | proper `sr:` refs (`story.py:156`) |
| `system-renderers.ts:430-436` `renderReversePath` | file, run_id, task, requirements | file is a bare path; run_id is not a ref; task is a bare id |
| `system-renderers.ts:340` `renderChangedFiles` | raw paths | `file:` is openable |
| `system-renderers.ts:555` `renderTrace` upstream | bare BR id | |
| `system-renderers.ts:588` `renderTrace` task hop | bare id (`e.src`) | |
| `system-renderers.ts:583,586` `renderTrace` plan/spec | already prefixed | **existing wart:** renders `plan: plan:foo.md`; the chip fixes it |
| `system-bootstrap.ts:270` sidebar Unbundled rows | proper refs | bundle rows at `:219` already render labels — unchanged |
| `system-bootstrap.ts:766` `renderTraversal` | see below | |

`renderBundleList` and `renderFeatureSidebar`'s bundle rows already render labels and
are **not** changed by this component.

### Traversal payload normalization

`queries.py:1565` emits bare ids, and `queries.py:1588` emits
`", ".join(sr_ids)` — one comma-joined string — for a bundle scope. The browser cannot
split that without parsing.

`query_traversal` therefore changes to emit canonical refs as **lists**:

```
{"requirement": ["sr:SR-030", "sr:SR-033", …],
 "tasks": ["task:T-055", …], "design": ["adr:ADR-0003", …],
 "files": ["file:src/drone/planning/reactive.py", …]}
```

`SystemTraversal` in `system-cli.ts:251` changes `requirement: string` to
`requirement: string[]`. The traversal payload is not one of the four frozen response
schemas, so this is permitted; it is a breaking change to one internal contract and is
covered by tests on both sides.

### Bounded ref collections

Attaching a title to each of fifteen comma-joined refs would make the spine worse. So
every site rendering a collection of refs renders a **bounded list**:

- one chip per row, never comma-joined;
- the first five rows shown, the remainder behind a native `<details>` labelled
  `+ N more`, consistent with the evidence disclosure already used by `renderClaim`;
- the total count always visible.

Applies to the traversal spine's four steps, `renderStory`'s requirements,
`renderTrace`'s task hops, `renderChangedFiles`, and `member of bundles`. Ordering
stays exactly as Python emitted it.

### Chip and card

The chip renders `T-060 · Wire the safety governor into the planner loop`, id in the
monospace face, title in the reading face. The chip carries no description — an SR
`statement` runs to sixty words.

The card opens on hover, on keyboard focus, and on tap, and carries: id, kind and
status on one line; title; description clamped to three lines; `from: statement` in
mono naming the recorded field; recorded relations; path in mono; and an `Open` link
only when `scope_href` is non-null. When `description` is `null` the card shows the
Component 3 remediation block for that kind.

A ref that resolves to nothing renders the raw string plus the visible note
`not in the label index`, with the dashed presence rail.

### Sidebar row structure

Rows become two blocks: label on its own line in the reading face, counts beneath in
the mono metadata size. The label is never visually continuous with the counts.

### Why an index rather than titles in each payload

Embedding titles would require a parallel change and a schema revision in each of
`system_response`, `system_claim`, `system_matrix_row`, `system_timeline_event`, and
`system_bundle`. One index is one contract, one fetch, one cache.

---

## Component 2 — Vocabulary

### Delivery: inlined, not fetched

Vocabulary is a static table. It is compiled into the page by `system-shell.ts` at
render time as a JSON literal, exactly as the renderer functions are already inlined.
**No endpoint, no subprocess, no fetch.** `factory.system vocabulary --json` exists as
a CLI subcommand so the table is inspectable and testable from Python, but the browser
never calls it.

The table lives in one Python module, `src/factory/system/vocabulary.py`, and is
mirrored into TypeScript by a generated constant checked by a test that fails if the
two drift.

### Entry shape

```
{
  "term": "recorded",
  "group": "claim-kind",
  "gloss": "straight from a file, not inferred",
  "definition": "Copied verbatim out of an artifact file. Nothing was computed or written by a model.",
  "siblings": ["derived", "synthesized", "missing"],
  "computed_by": ["src/factory/system/queries.py", "src/factory/system/story.py"]
}
```

`gloss` is at most eight words and renders inline. `definition` is one to three
sentences. `computed_by` is a **list** of module paths — a single string would be
false for most terms (`ClaimClass.RECORDED` is set in nine places in `queries.py`
alone, `DERIVED` and `SYNTHESIZED` in `guide.py`).

### Coverage registry

An explicit registry lists every enumerated value the browser can display, and the
completeness test asserts the vocabulary covers exactly that registry. The registry is
the test's source of truth because several rendered values are typed `string` and are
not mechanically enumerable.

- Claim kinds (`system-cli.ts:53`) — `recorded`, `derived`, `synthesized`, `missing`
- Freshness (`:39`) — `fresh`, `stale`, `degraded`, `n/a`
- Matrix statuses (`:90`) — `passed`, `failed`, `error`, `blocked`, `never-run`,
  `unknown`
- Validation states (`trace/validation_status.py:10`) — `passed`, `failed`, `error`,
  `never_validated`, **plus** the mapping to `MatrixStatus`'s hyphenated `never-run`
- Timeline actors (`:110`) — 7 values
- Timeline actions (`:119`) — 7 values
- Citation kinds (`:16`) — 9 values
- Scope kinds (`:9`) — `bundle`, `sr`; and `TimelineSubjectRef.kind` (`:106`) —
  `task`, `sr`, `run`, `manifest`
- Story run source (`:299`) — `manifest`, `session`
- Readiness (`health.py:130`) — `weak`, `medium`, `strong`
- Readiness counts (`health.py:49`, predicates at `health.py:67`) — `sr_total`
  (`len(flags)`, `health.py:140`, no predicate), `bound`, `covered`, `current`,
  `deferred`, `validated`
- Health class names (`trace/health.py:20`) — the five, each stating **its
  denominator rule in words**
- Health counters (`system-cli.ts:222`) — `dangling`, `deferred`, `proposed`
- Trace dispositions (`trace/gaps.py:23`) — `pending`, `exempt`, `deferred` only
- `stops_at` (`:352`) — `task`, `satisfies`, `null`
- Run outcomes — not a union; an allowlist of observed values plus a documented
  fallback that renders an unknown outcome plainly with no gloss
- Structural nouns — `bundle`, `scope`, `SR`, `BR`, `ADR`, `evidence run`, `evidence
  manifest`, `session record`, `claim`, `span`, `citation`

### Rendering

Badges keep their exact contract word, so the browser and the CLI stay one language.
Each gains an inline `gloss` line and an `ⓘ` button opening the definition card.

Health class labels gain a readable primary label — `task->plan` renders as
`Tasks linked to a plan`, with `task->plan` demoted to the mono metadata line. The
readable label lives in the vocabulary table, so Python still owns the wording.

A `Vocabulary` control in the header opens the full table as a workspace view.

---

## Component 3 — Remediation

### Delivery

Static, like vocabulary: `src/factory/system/remediation.py`, inlined into the page by
`system-shell.ts`, with a `factory.system remediation --json` CLI subcommand for
inspection. No endpoint, no fetch.

### Entry shape

```
{
  "state": "sr_unsatisfied",
  "headline": "No task satisfies this requirement",
  "what_it_means": "…",
  "why_it_matters": "…",
  "command": "/trace-fix {id}",
  "command_kind": "slash" | "shell",
  "severity": "absence" | "failure"
}
```

`{id}` (bare identifier) and `{ref}` (canonical ref) are the only substitutions. The
browser performs them literally. **Templates use `{id}` wherever the target command
takes a bare identifier**, which is every current case — `/trace-fix SR-121`, not
`/trace-fix sr:SR-121`.

### Keys

The eleven `GapKind` values (`trace/gaps.py:9`, verified complete): `task_no_sr`,
`task_no_plan`, `task_plan_missing`, `plan_no_spec`, `dangling_upstream`,
`sr_unsatisfied`, `sr_proposed`, `sr_unvalidatable`, `sr_unvalidated`, `sr_stale`,
`dangling_reference`.

Plus the browser-decided absence states, each corresponding to an existing branch the
browser takes on its own:

`no_claims`, `no_matrix_rows`, `no_timeline_events`, `no_guide_sections`,
`no_runs`, `no_requirements`, `no_changed_files`, `no_commit_range`, `no_trace`,
`no_traversal_step`, `no_bundles`, `no_description`, `traversal_not_applicable`,
`matrix_never_run`, `unbundled_artifact`, `unresolved_ref`.

### Severity, narrowed

Revision 1 said the five `degraded:` banners split by severity. They cannot: their
`degraded_reasons` are free-text sentences with interpolated counts
(`story.py:174`, `:177`; `reverse.py:170`; `queries.py:821`, `:1377`), so the browser
could only substring-match — which is interpretation — and making them machine-readable
would change frozen response schemas.

**Severity therefore applies only to states the browser decides itself**: the empty
states listed above, each of which is an explicit `if (!x.length)` branch with a known
key. Those render the neutral absence treatment plus a Next step. The red `degraded:`
banner is left exactly as it is in this increment. Making degraded reasons
machine-readable is recorded as a follow-up.

To avoid the duplication this creates — `no_runs` appears both as a banner reason
(`story.py:174`) and as the empty state at `system-renderers.ts:390` — **a panel
renders at most one Next step block**, at the panel level, after any banner.

### Command inventory

Verified to exist on 2026-08-14. Slash commands: `/factory-init`, `/factory-doctor`,
`/factory`, `/factory-run`, `/factory-tasks`, `/factory-stop`, `/factory-watch`,
`/factory-context`, `/plan`, `/polish`, `/trace-fix`, `/review-plans`, `/system`,
`/goal`, `/visual-explain`, `/remember`.

Module invocations: `uv run python -m factory.requirements {new,bind,defer}`,
`… factory.trace {link,exempt,defer}`, `… factory.doctor {mint,promote}`,
`… factory.system {bundle,coverage}`.

**`factory.system check` does not exist.** The only `check` is
`factory.system bundle check --draft <path>` (`system/cli.py:452`), which requires
`--draft`. Any remediation entry needing it must use that exact form.

A test asserts every `command` names either a registered slash command or an existing
`factory.*` subparser path, so the table cannot drift from the CLI.

### Rendering

Every browser-decided empty state, every `missing` claim, every `not recorded` value,
and every `never-run` matrix row contributes a **Next step** block: headline, one
sentence of `what_it_means`, one sentence of `why_it_matters`, the command in mono
with a copy button. Copy writes to the clipboard and confirms in place. There is no
execution path.

---

## Component 4 — Layout and first run

### Scope heading inversion

`setScopeHeading` (`system-bootstrap.ts:160`) uses `bundle?.label || scopeRef`, which
yields `task:T-001` for every non-bundle scope. It becomes: the label index title as
the heading, the ref as the mono metadata line beneath, kind eyebrow unchanged, and
the description as the lead paragraph when recorded.

### Evidence grid and context rail

Above 1200 px the workspace becomes two columns: panel content left, a sticky context
rail right carrying scope summary, readiness beside its counts, membership, and the
current Next step. Below 1200 px the rail collapses above the content. Below 760 px
the existing mobile layout is unchanged.

### First run

The zero-bundle feature directory (`system-bootstrap.ts:780` iterates an empty list)
gains a card explaining what a bundle is and the command that creates one.

The landing gains a dismissible orientation strip, dismissal held in `localStorage`
under one key. `2026-08-13-system-navigator-visual-identity-design.md:137` lists "user
preference storage" as a non-goal; **that spec is amended by this one**, narrowly, for
this single key. The amendment is recorded in both documents rather than left as a
silent override.

---

## Component 5 — Bundle description field

`system_bundle.schema.json` gains an optional `description` string with
`maxLength: 280`. `BundleDeclaration` gains `description: str | None`, parsed in
`bundles.py` and surfaced through `health`'s bundle rows and the label index.
`additionalProperties: false` (`system_bundle.schema.json:6`) means the schema edit is
genuinely required, not merely permissive.

### Recorded override

`models.py:215` states a bundle carries "a label and exact member refs only — no
status, no claims, no rationale", and
`2026-08-10-system-control-center-program-decomposition.md:72,111` rules that bundle
files stay **membership-only** with reasoning in an ADR.

This design **overrides the membership-only half of that ruling**, on the user's
explicit instruction of 2026-08-14, after the conflict was raised with them. It is
recorded as an override rather than reconciled, because the two cannot be reconciled
honestly: a character cap enforces length, not category, and a 280-character rationale
fits comfortably. Nothing mechanical distinguishes "what the feature is" from "why it
was cut that way".

What holds the line is convention, stated in the schema's own `description`
annotation and in the field's docstring: this field expands the label, and rationale
belongs in an ADR. The rationale-lives-in-an-ADR half of the ruling stands
unchanged.

Revision 1 cited `docs/adr/0003-feature-bundle-map.md` as the current home of that
rationale. That file does not exist; `docs/adr/` does not exist in this repository,
and the decomposition places that document in `cool_physical_ai_project` as an
unshipped SP-A deliverable. The citation is withdrawn.

Existing bundle files remain valid. A bundle without a description renders
`no description recorded` plus its Next step.

---

## Client-side architecture

`system-shell.ts` **must change**, and revision 1 failed to name it.

- `clientSource()` (`system-shell.ts:35`) stringifies an explicit array of renderer
  functions. `refChip` and the card component must be added to that array or they will
  not exist in the page.
- `refChip(ref)` takes one argument, so the label index must be a free variable at
  IIFE scope. `systemBootstrap()`'s state is declared inside the function and is
  invisible to sibling renderers. A mutable binding is emitted in the preamble
  (`system-shell.ts:31`) beside `clear`, with `declare let` shims in both TS files —
  the pattern `system-bootstrap.ts:22` already uses, and which exists precisely because
  a real import injects esbuild's `__name`.
- The vocabulary and remediation tables are emitted into the same preamble as frozen
  JSON literals.
- **This amends `system-renderers.ts:4`'s contract** ("none of them reads fetch/state")
  to: none of them *fetches*, sorts, filters, or decides ordering; all of them may read
  the frozen label/vocabulary/remediation lookups. The comment is updated in place.

### Fetch ordering

`renderFeatureSidebar` is called from `loadHealth()` (`system-bootstrap.ts:829`). The
labels fetch is issued **before** health and awaited by both, so the sidebar never
renders bare and then reflows. Labels use the async runner
(`loadSystemLabelsAsync`), never `spawnSync` — `cli-runner.ts:44`'s `runJsonCli` would
block the docs server's event loop.

### Cost

Only **one** new endpoint is added. Vocabulary and remediation are inlined, so they
cost zero subprocesses. The labels projection reads the full body of every spec and
plan for the `Purpose` paragraph — 124 documents in this repository — so it carries
the same 15 s timeout and "taking longer than expected" treatment as health
(`system-bootstrap.ts:73`), and its extraction stops at the first matching section
rather than parsing whole documents.

---

## Error handling

- **Labels unavailable** — chips render bare refs with the visible note
  `label index unavailable`. Everything else is unaffected. A retry control appears,
  consistent with the existing health-load treatment.
- **Vocabulary or remediation malformed** — impossible at runtime; they are frozen
  literals validated by a build-time test. A missing key renders the badge with no
  gloss and no `ⓘ`, and no Next step, rather than throwing.

No failure blanks the page, and none blocks another.

---

## Verification

### Python

- Unit tests per projection over `tests/unit/system/_fixtures.py`: label extraction
  per kind, `description_source` correctness, `null` handling, alias resolution for
  both `spec:` spellings, and `scope_href` null for `spec`/`plan`/`adr`.
- `normalize_ref` tests covering bare id, basename spelling, path spelling, and
  unresolvable input.
- **Completeness test** asserting the vocabulary covers exactly the coverage registry,
  and every remediation key is a `GapKind` or a declared absence state.
- **Command-existence test** asserting every `command` names a registered slash command
  or an existing `factory.*` subparser path.
- **Drift test** asserting the TypeScript mirror of both tables equals the Python
  source.

### TypeScript (jsdom)

`refChip` output structure and the unknown-ref path; bounded list with `+ N more`;
card open on hover, focus and tap; `Escape` closes and returns focus; copy button; one
Next step per panel; scope heading inversion; sidebar two-block rows; two-column grid
above 1200 px and absent below; first-run card at zero bundles; labels-unavailable
degradation; `renderTraversal` against the new list-shaped payload.

### Browser

**Extend `test/system-browser-validation.test.ts`; do not build a second harness.** It
already boots the real docs server and drives Chromium at 1440×900, 1024×768 and
390×844 behind `BROWSER_GATE=1`, defaulting to `C:\coding\cool_physical_ai_project` —
the correct target, holding 182 requirements, 44 tasks and 14 bundles. This
repository's zero-bundle state is the second target via `BROWSER_GATE_TARGET`.

Added assertions: no console errors; no horizontal page overflow; cards reachable by
keyboard and tap; `Escape` returns focus; **gloss text contrast measured, not
eyeballed**; `prefers-reduced-motion` respected; the spine bounded to five rows with
its disclosure; every visible `Not recorded` carrying a Next step.

**Harness note.** Serving the extension through `tsx` injects esbuild's `keepNames`
`__name` helper into the stringified function bodies, producing
`ReferenceError: __name is not defined` in the browser. This is an artifact of the
harness, not the shipped page. Any browser check must define `window.__name = (fn) =>
fn` before navigation or it reports a false failure.

---

## Review resolutions

| Finding | Resolution |
|---|---|
| B1 traversal emits bare ids and a joined string | `query_traversal` normalized in Python to lists of canonical refs; `SystemTraversal.requirement` becomes `string[]` |
| B2 two `spec:`/`plan:` spellings | `normalize_ref` in Python; index carries an `aliases` map |
| B3 severity has no mechanism | Narrowed to browser-decided empty states; `degraded:` banners unchanged; one Next step per panel |
| B4 `factory.system check` absent | Inventory corrected to `factory.system bundle check --draft` |
| B5 ADR citation invalid | Citation withdrawn |
| B6 membership-only conflict; cap is not enforcement | Rewritten as an explicit recorded override on the user's instruction; false enforcement claim removed |
| B7 `system-shell.ts` and stateless contract | New "Client-side architecture" section; renderer contract amended in place; fetch ordering specified |
| S1 `dod` unusable | Tasks carry no description; card shows recorded relations instead |
| S2 ADR heading rule unspecified | Case-insensitive `^Decision$`, first match, null fallback |
| S3 `computed_by` single string is false | Now a list |
| S4 gloss fails contrast | `--gloss` retargeted to `--text-muted`; contrast measured in the gate |
| S5 emission list wrong | Corrected and completed as a table |
| S6 enum coverage gaps and mislabels | Explicit coverage registry; dispositions corrected; validation-state mapping added |
| S7 three sync spawns | Vocabulary and remediation inlined; one async endpoint remains |
| S8 `spec`/`plan` not openable | Openable set enumerated explicitly |
| Nits | `health.py` citations corrected; `{id}` vs `{ref}` unified on `{id}`; `run` removed from sources; `plan: plan:` wart noted; visual-identity non-goal amended explicitly; schema `additionalProperties: false` noted |

---

## Non-goals

- Write actions of any kind. SP-C owns remediation execution.
- Changes to `system_response`, `system_claim`, `system_matrix_row`, or
  `system_timeline_event` schemas.
- Making `spec`, `plan`, `adr`, `diag`, `feat`, `metric` or `goal` openable scopes.
- Machine-readable `degraded_reasons`.
- A `description` field on the task artifact.
- Model-written summaries, scores, or judgments anywhere.
- Changes to `/review-plans`, the docs browser, or mission control.
- A framework, build step, remote font, image, or icon package.
- Description extraction for `br`, `feat`, `metric`, `goal`, `diag`.
