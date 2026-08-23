# System-Traceability Course Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `system-traceability` classroom true against the factory's live surface as of 2026-08-23, cover every untaught workflow, and give a newcomer a 0→100% path — in three gated increments, each reviewed before delivery.

**Architecture:** Three increments in strict order. Increment 1 repairs and re-grounds the three existing lessons, the command card, the glossary and a quiz-key contract bug. Increment 2 authors eight new lessons (seven previously-untaught workflows + a progressive-assurance roadmap lesson). Increment 3 adds a lesson 000 spine, a roadmap perspective, a course-map diagram, and a full-course review gate. Every increment ends in the §"Review gate" checklist; a step that fails it blocks the increment. Content lives in the classroom dir (`C:/Users/33630/.pi/agent/classrooms/system-traceability/`, outside the git repo); the design doc and this plan live in the factory repo.

**Tech Stack:** pi-teach classroom runtime (static HTML lessons, `scaffold_lesson` tool, quiz markup contract in `~/.pi/agent/npm/node_modules/pi-teach/assets/templates/quiz.html`); the factory repo at `C:/coding/pi-agent-factory` (branch `docs/coherence-progressive-assurance-design`, HEAD `330aa1f`) as live ground truth; inline SVG for simple diagrams, committed `tff-generate_visual` HTML in `assets/` for layout-heavy maps.

---

## Ground-truth snapshot (re-verify at each gate; never trust this table to age)

Captured 2026-08-23 against `docs/coherence-progressive-assurance-design` HEAD `330aa1f`:

- **`coherence` console entry, seven groups** (`src/coherence/cli.py` GROUPS): `trace`, `register`, `doctor`, `navigate`, `presentation`, `goals`, `simulation`. `factory.{trace,requirements,doctor,system,goals,simulation,presentation}` are `DeprecationWarning` shims into `coherence.*`.
- **`coherence.trace`**: status, graph, link, **unlink**, next, check, exempt, defer. 11 gap kinds (`src/coherence/trace/gaps.py`): task_no_sr, task_no_plan, task_plan_missing, plan_no_spec, dangling_upstream, sr_unsatisfied, sr_proposed, sr_unvalidatable, sr_unvalidated, sr_stale, dangling_reference. Dispositions pending/exempt/deferred; exempt refused for `sr`/`br`.
- **`coherence.register`**: new, index, status (`--stale`), show, bind, defer, check, next. Closure states MEASURED_PASSING/MEASURED_FAILING/PLANNED/UNMEASURABLE/DECLINED/PENDING (`src/coherence/register/closure.py`); stale binding checksum → PENDING blocking.
- **`coherence.doctor`**: context, mint, promote, task.
- **`coherence.navigate`** (was `factory.system`): brief, dossier, worker, matrix, timeline, story, reverse, guide, traversal, vcycle, validation, catchup, diagram, sim (run/latest/failure/metric/goal-evidence), goal (show/list/evaluate), present, scope, health, freshness, labels, vocabulary, remediation, panels, memberships, **bundle check**, **new**, coverage, **membership**. Reads only except `guide --export` and `goal evaluate`/goal-write lifecycle (verify at gate).
- **`coherence.goals`**: list, show, create, set-state, evaluate, history. **`coherence.simulation`**: runs, sensitivity. **`coherence.presentation`**: present.
- **`factory.coverage`** (not migrated): list-features, run, audit, verdict, consolidate, gate (0/1/2), report, failure. Eight per-SR states; fail = unlinked/not_implemented/dishonest; warn = suspect/unmeasured.
- **`factory.evidence`**: run, task, record, list, reconcile. **`factory.orchestrator`**: run, list, run-state (current/inspect/resume/restart/abandon/preserve-external-edits/doctor). **`factory.validation`**: run.
- **Slash commands**: /system, /trace-fix, /coverage-review, /factory-doctor, /review-plans, /goal, /factory, /factory-run, /factory-tasks, /factory-stop, /factory-watch, /plan, /polish, /catchup, /task, /factory-init, /visual-explain, /clear.
- **Live trace state** at gate time: 65 pending, 1 deferred, 2 exempt (re-verify; counts move).
- **Roadmap (do NOT teach as live commands)**: `coherence.{audit,measurement,status,focus,gate,inbox,explain}` (increments 4–6); progressive-assurance layer (spec `2026-08-22-coherence-progressive-assurance-design.md`, increments 2B/2C/3B/6B — `substrate.policy`, `coherence.policy` compiler, typed `justification:`, `docs/nonconformances/NC-*.md`, seven-dimension profile, eleven-dimension health vector, suspect-edge `proposed|valid|suspect|invalid|waived` STRICT no-auto-`valid`, CI-as-compiled-obligation-consumer, thin vertical slice T-031→NC-0001); one-gate protocol; `/using-coherence`; `/factory-selfcheck`; envelope-wrapping of all producers (agentic I/O §9).

## Conventions (apply to every task)

- **Classroom root**: `CR = C:/Users/33630/.pi/agent/classrooms/system-traceability`.
- **Quiz key schema** (001/002 form; the only valid one): `{"check-1": {"q1": {"answer": "...", "why": "..."}, ...}}`. Option labels are `value="a"|"b"|"c"|"d"`, never the answer text. Every option the same length in words. Never put the answer in the lesson HTML; keys go in `<lesson>/quiz/key.json`.
- **Citations**: every load-bearing claim cites the governing spec (`docs/superpowers/specs/*.md`) or source file (`src/coherence/*/cli.py`, `src/factory/*/cli.py`) by path. Roadmap claims carry "as of 2026-08-22/23".
- **Diagrams**: structural ones are inline SVG in the lesson (copy the `<svg>` styling pattern from lesson 003's figures); layout-heavy maps are committed `tff-generate_visual` HTML into `CR/assets/` and linked `<a href="/c/system-traceability/assets/xxx.html">`.
- **Scaffolding new lessons**: call `scaffold_lesson(classroom="system-traceability", name=..., title=..., summary=...)`; it auto-numbers `max existing + 1`. Lesson 000 is handled explicitly (see Increment 3).
- **Git discipline**: the lesson assets are outside the repo (no git). On the factory repo, stage only the specific design/plan/spec files you touch — **never `git add -A`** (parallel-session uncommitted files exist: increment 4–8 plans, the progressive-assurance spec, and session files).
- **Verification**: every "Run:" includes the exact command and the expected observable. Every task ends with a checkpoint tied to the §"Review gate" items where applicable.

---
# Increment 1 — Repair and re-ground the existing surface

Goal: the three lessons + command card + glossary are true against the ground-truth
snapshot, the quiz-key contract is fixed, two structural diagrams are added, and Gate I
passes.

## Task 1.1 — Fix lesson 001 (routing-the-question)

**Files:**
- Modify: `CR/001-routing-the-question/lesson.html`
- Verify: `CR/001-routing-the-question/quiz/key.json` (unchanged schema)

- [ ] **Step 1: Read the current lesson and the ground-truth snapshot**

Read `CR/001-routing-the-question/lesson.html`. The following fixes are required.

- [ ] **Step 2: Replace the stale gap count**

Find "Run this in the factory repo today and it fails — 47 gaps, every one of them a
`task_no_sr` or `plan_no_spec`". Replace with a count-neutral phrasing plus the live
shape, e.g.:

```html
<p>
  Run this in the factory repo today and it fails — the count moves, but the shape
  doesn't: pending `task_no_sr`, `plan_no_spec`, `sr_unsatisfied` and
  `dangling_reference` gaps, with a handful deferred or exempt. Deferred and exempt
  pass the gate; pending fails it.
</p>
```

Do not hard-code "65" — the number changes under the course; if you want a live figure,
re-run `coherence trace check` and state it as "as of <date>".

- [ ] **Step 3: Retarget the primary invocation from `factory.*` to `coherence`**

The lesson says "There is no `factory` console script — everything is
`uv run python -m factory.<pkg>`". Replace with:

```html
<p>
  The primary invocation is the <code>coherence</code> console entry
  (<code>python -m coherence.&lt;group&gt;</code>) with seven groups — trace, register,
  doctor, navigate, presentation, goals, simulation. The old
  <code>factory.&lt;pkg&gt;</code> paths still work as deprecation shims
  (<code>factory.trace</code>, <code>factory.requirements</code>,
  <code>factory.doctor</code>, <code>factory.system</code>, <code>factory.goals</code>,
  <code>factory.simulation</code>, <code>factory.presentation</code>) — each prints a
  warning pointing at its <code>coherence</code> replacement. Nothing in this course
  teaches a <code>factory.*</code> command as the target.
</p>
```

Then audit the whole lesson for `factory.` invocations and change them to the
`coherence` form (e.g. `factory.trace status` → `coherence trace status`;
`factory.doctor mint` → `coherence doctor mint`). Keep the worked example's
`/trace-fix` slash command — it is unchanged.

- [ ] **Step 4: Fix Trap 1 (the non-verb `factory.evidence.coverage`)**

In "The three traps", the first trap says "`factory.evidence.coverage` is whether
declared deliverables were gathered". That is a module, not a CLI verb. Replace with
what the evidence CLI actually offers:

```html
<li>
  <strong>"Coverage" never means lines of code.</strong> <code>factory.coverage</code>
  is requirement coverage; <code>coherence.navigate coverage</code> (aliased
  <code>membership</code>) is bundle membership; <code>factory.evidence</code>
  (verbs <code>run task record list reconcile</code>) is about run manifests — whether
  declared deliverables were gathered. Three different questions, three different
  commands.
</li>
```

- [ ] **Step 5: Fix the "preflight refuses → run-state" row**

The symptom table row "Nothing will start; preflight refuses." →
`factory.orchestrator run-state` lands on the wrong verb. Change the cell to point at
the preflight gate on `run` and reserve `run-state` for recovery:

```html
<tr>
  <td>"Nothing will start; preflight refuses."</td>
  <td><code>factory.orchestrator run</code> (the preflight gate is part of run;
  exit code distinguishes refused vs failed). <code>factory.orchestrator run-state</code>
  is the checkpoint-recovery surface (<code>current|inspect|resume|restart|abandon|
  preserve-external-edits|doctor</code>).</td>
</tr>
```

- [ ] **Step 6: Verify**

Run: `python -c "import re; s=open(r'CR/001-routing-the-question/lesson.html',encoding='utf-8').read(); print('47' in s, 'factory.evidence.coverage' in s, 'coherence trace status' in s)"` — expect `False False True`. Also confirm no `factory.` verb remains as a *target* (shims may be mentioned as deprecated, not taught). Checkpoint: no stale count, no non-verb, correct routing.

## Task 1.2 — Fix lesson 002 (four-verdicts)

**Files:**
- Modify: `CR/002-four-verdicts/lesson.html`

- [ ] **Step 1: Read the current lesson**

Read `CR/002-four-verdicts/lesson.html`.

- [ ] **Step 2: Replace the wrong `kb-0006` citation**

The lesson says the FEAT-NAV-017 audit blindness "was written up as `kb-0006`". On disk,
`kb/kb-0006-unseeded-random-flaky-sim-test-assertions.md` is about sim-test flakiness —
unrelated. The real root cause (per the coverage-review design doc and lesson 003's own
correction): `T-058`/`T-067` were marked done with no manifest at all → empty
changed-files → blind overlap. Replace the sentence:

```html
<p>
  In that run the manifests were missing for two tasks marked done —
  <code>T-058</code>/<code>T-067</code> — so there was nothing to intersect. Overlap
  came back empty, and empty overlap is indistinguishable from a test that genuinely
  touches nothing. The verdict was honest about its own blindness; the coverage-review
  design records it (<code>docs/superpowers/specs/2026-08-17-requirement-coverage-review-design.md</code>),
  and it is why "missing &ne; empty" evidence handling sits first in the improvement list.
</p>
```

- [ ] **Step 3: Name the validation write-side as a verb**

In the "One SR, four answers" table, row "validation report — Did the measurement
*run*?" add the command that writes it: `factory.validation run` writes
`validation/validation-report.json`; `trace` (`sr_unvalidated`/`sr_stale`) and register
closure consume it. Change the row's first cell to:

```html
<td><code>factory.validation run</code> (writes <code>validation/validation-report.json</code>)</td>
```

- [ ] **Step 4: Reconcile 002 vs 003 on the FEAT-NAV-017 root cause**

Ensure lesson 002 now states the same root cause lesson 003 states (missing manifests for
T-058/T-067), and that no other sentence in 002 references `kb-0006` for this event.
Grep the file for `kb-0006` — the only remaining mention should be none.

- [ ] **Step 5: Verify**

Run: `grep -n "kb-0006" CR/002-four-verdicts/lesson.html` — expect no match.
Checkpoint: one consistent root-cause story, validation named as a verb, no false citation.

## Task 1.3 — Fix lesson 003 (coherence-programme): second-wave rewrite

**Files:**
- Modify: `CR/003-coherence-programme/lesson.html`

- [ ] **Step 1: Read the current lesson**

Read `CR/003-coherence-programme/lesson.html`. The "today" section currently claims the
programme is docs-only with no `src/coherence/`, no `src/substrate/`, no console entry,
no register. All four are now false.

- [ ] **Step 2: Rewrite the "One paragraph answer" and "today" sections**

Replace the paragraphs that claim "Today the whole programme is documents…" with the
live split, using the ground-truth snapshot. Required content, in order:

```html
<p>
  <strong>Today, most of the carve has landed.</strong> On branch
  <code>docs/coherence-progressive-assurance-design</code> (as of 2026-08-23):
  <code>src/substrate/</code> is a populated shared package
  (<code>freshness/{recipes,guard,fingerprint}</code>, <code>codemap/imports</code> =
  TN-13, <code>kb</code>, <code>artifacts</code>, <code>observations</code>,
  <code>projections</code>); the <code>coherence</code> console entry exists and
  dispatches seven groups — trace, register, doctor, navigate, presentation, goals,
  simulation; the old <code>factory.*</code> paths are deprecation shims.
</p>
<p>
  <strong>What is still roadmap.</strong> <code>coherence.{audit,measurement,status,
  focus,gate,inbox,explain}</code> (increments 4–6) do not exist. The
  progressive-assurance layer — obligations, profiles, typed <code>justification:</code>,
  <code>NC-*</code> nonconformance records, the health vector, suspect edges — is
  designed (<code>2026-08-22-coherence-progressive-assurance-design.md</code>)
  with implementation plans (2B/2C/3B/6B) but zero code. One-gate protocol,
  <code>/using-coherence</code>, <code>/factory-selfcheck</code> and the agentic-I/O
  producer migration are all still roadmap.
</p>
```

Remove any sentence that asserts the absence of substrate/coherence/register, and any
claim that <code>unlink</code> (TN-03) is future — it is shipped (<code>coherence trace unlink</code>).

- [ ] **Step 3: Update the increment table's disposition column**

The table currently lists increments 0–8 with "must follow" only. Add a "status" column
(or a paragraph under it) marking: 0/1/1B/1C/2/3 shipped; 2B/2C/3B/6B new (designed,
plans exist); 4/5/6 not built (amend in place); 7/8 not built. Update the dependency
spine diagram text to include the 2B→2C→3B→4→5→6→6B/7-8 fork from the amendment's
scheduling block, and note 6B/7/8 are mutually cuttable.

- [ ] **Step 4: Add the coverage→membership rename note**

Where the design's rename is discussed, state: the rename landed as a parallel verb —
<code>coherence.navigate</code> exposes both <code>coverage</code> and <code>membership</code> today (transition state).

- [ ] **Step 5: Verify**

Run: <code>grep -n "zero implementation\|no src/substrate\|no coherence\|docs only" CR/003-coherence-programme/lesson.html</code> — expect no match (or only the explicitly-flagged roadmap wording). Checkpoint: lesson 003's "today" is true, roadmap is labelled and dated.

## Task 1.4 — Rewrite the command card to the live surface

**Files:**
- Rewrite: <code>CR/reference/command-card.html</code>

- [ ] **Step 1: Read the current card**

Read <code>CR/reference/command-card.html</code>.

- [ ] **Step 2: Rewrite it entirely (write tool)**

Rewrite the card as a single dense reference with the ground-truth snapshot. Required
sections, in order:

1. **Slash commands** — keep the existing table (all verified accurate), add the missing
   commands: <code>/factory</code>, <code>/factory-run</code>, <code>/factory-tasks</code>, <code>/factory-stop</code>,
   <code>/factory-watch</code>, <code>/plan</code>, <code>/polish</code>, <code>/catchup</code>, <code>/task</code>, <code>/factory-init</code>,
   <code>/visual-explain</code>, <code>/clear</code> with one-line meanings (source: <code>pi-ext/factory-watch/src/index.ts</code>).
2. **<code>coherence</code> console** — the entry: <code>coherence &lt;trace|register|doctor|navigate|presentation|goals|simulation&gt;</code>; note <code>python -m coherence.&lt;group&gt;</code> works for scripts; <code>factory.*</code> = deprecation shims.
3. **<code>coherence.trace</code>** — status, graph, link, **unlink** (TN-03), next, check, exempt, defer; the 11 gap kinds; dispositions; exempt refused for SR/BR.
4. **<code>coherence.register</code>** — new, index (exit 1 on stale), status (<code>--stale</code>), show, bind, defer, check, next; closure states + the stale-checksum→PENDING rule.
5. **<code>coherence.doctor</code>** — context, mint, promote, task.
6. **<code>coherence.navigate</code>** — the full verb list from the snapshot incl. <code>membership</code>/<code>coverage</code>, <code>catchup</code>, <code>freshness</code>, <code>diagram</code>, <code>sim</code> subtree, <code>goal</code>; scope refs (<code>bundle: sr: task: file: adr: diag: feat: metric: goal:</code>); "reads only except guide --export and goal evaluate".
7. **<code>coherence.goals</code> / <code>coherence.simulation</code> / <code>coherence.presentation</code>** — the three verb lists.
8. **<code>factory.coverage</code>** — list-features, run, audit, verdict, consolidate, gate (0/1/2), report, failure; the eight states; fail/warn sets; <code>coverage-reviews/</code> location.
9. **<code>factory.evidence</code> / <code>factory.orchestrator</code> / <code>factory.validation</code>** — the verb lists, with run-state's checkpoint verbs.
10. **Roadmap block** — a short, clearly-labelled "designed, not shipped (as of 2026-08-23)" list: coherence.{audit,measurement,status,focus,gate,inbox,explain}; progressive-assurance vocabulary; one-gate protocol; /using-coherence; /factory-selfcheck; envelope migration.
11. **Related lessons** — fix the dead link: point at <code>../001-routing-the-question/lesson.html</code> ("Routing the question") plus 002/003 and the glossary.

Every verb listed must exist in the snapshot (argparse-verified). Keep the <code>&lt;main class="cl-lesson-shell" data-cl-content&gt;</code> shell and <code>&lt;title&gt;</code>.

- [ ] **Step 3: Verify**

Run a small python check that greps the card for each snapshot verb and reports any missing, and
Run: <code>grep -rn "001-the-traceability-surface" CR/</code> — expect no matches. Checkpoint: card is
complete, current, and link-clean.

## Task 1.5 — Glossary + quiz-key contract fixes

**Files:**
- Modify: <code>CR/GLOSSARY.md</code>
- Modify: <code>CR/003-coherence-programme/quiz/key.json</code>

- [ ] **Step 1: Glossary additions**

Append to the relevant sections of <code>CR/GLOSSARY.md</code>:
- **unlink** — <code>coherence trace unlink NODE (--satisfies SR | --upstream BR)</code>: removes a declared edge; the reverse of link (TN-03).
- **deprecation shim** — a <code>factory.*</code> module that re-exports its <code>coherence.*</code> replacement and emits a DeprecationWarning; the transition layer during the carve, not the target.
- **roadmap-vs-live** — the dated discipline: any item not in code carries "as of <date>"; live items are what lessons teach as current.
- Under **Coherence programme (assurance half)** add, tagged "(roadmap, as of 2026-08-23)": **Obligation** <code>{id, scope_ref, kind, requiredness, reason, source_policy, state, resolve_cmd}</code>; **profile** (seven-dimension vocabulary); **justification** (typed task edge kinds satisfies/corrects/mitigates/implements/maintains/explores); **NC-* record** (nonconformance, mirror of FR-*); **health vector** (eleven dimensions); **suspect edge** (<code>proposed|valid|suspect|invalid|waived</code>, STRICT no-auto-valid).

Align the closure-state and gap-kind lists with the snapshot if they drifted.

- [ ] **Step 2: Fix lesson 003's quiz key schema**

Read <code>CR/003-coherence-programme/quiz/key.json</code> — it currently uses a flat
<code>{"q1": "a", ...}</code> shape (wrong). Rewrite it to the 001/002 schema:

```json
{
  "coherence-1": {
    "q1": {"answer": "a", "why": "All twelve increments are docs only was true at writing; today most of the carve has landed, but the amendment's new increments 2B/2C/3B/6B and 4-8 remain unbuilt — the split is the point."},
    "q2": {"answer": "a", "why": "New modules get re-export shims for one release; old paths are not removed on migration."},
    "q3": {"answer": "a", "why": "RTK is a shim over shell output to compact it — a precedent for Coherence's projection boundary, not a dependency."},
    "q4": {"answer": ["a", "b", "c", "d"], "why": "The four freshness resolution classes; event_bus_sweep does not exist."},
    "q5": {"answer": "open", "why": "Looking for: RTK's compaction is lossy text with invisible/final truncation, so nothing else can consume it; Coherence's projections are deterministic pure functions over validated inputs carrying truncated/redacted flags and linking back to content-hashed raw artifacts, so the compact view can be the agent's interface while the machine envelope and domain artifacts stay the evidence."},
    "q6": {"answer": "substrate", "why": "The layer that depends on nothing and is shared by both halves."}
  }
}
```

Match the quiz's actual <code>data-quiz-id</code> (currently <code>coherence-1</code>) and question ids; do
not renumber.

- [ ] **Step 3: Verify**

Run: <code>python -c "import json; k=json.load(open(r'CR/003-coherence-programme/quiz/key.json')); print(list(k))"</code> — expect <code>['coherence-1']</code> and every q1..q6 present. Checkpoint: glossary current, key schema uniform.

## Task 1.6 — Add two structural diagrams (inline SVG)

**Files:**
- Modify: <code>CR/001-routing-the-question/lesson.html</code> (add loop diagram near the top)
- Modify: <code>CR/002-four-verdicts/lesson.html</code> (add closure-state diagram in "One SR, four answers")

- [ ] **Step 1: Loop/six-tools diagram in lesson 001**

Copy the <code>&lt;svg&gt;</code> styling pattern from lesson 003's figures (<code>.t</code>, <code>.box</code>, <code>.t-l</code>, <code>.led</code>,
<code>.shim</code>, <code>.dep</code> classes + the arrow <code>&lt;marker&gt;</code> def). Build a horizontal diagram of the
one loop: doctor → trace → orchestrator → coverage → system → check, with a labelled
seam "model: exactly one judgement per step" between trace and orchestrator (and between
coverage and its subagents). Keep <code>role="img"</code> + <code>aria-label</code>. Insert it directly under
the "The loop, in one line" section.

- [ ] **Step 2: Closure-state diagram in lesson 002**

A small vertical decision chain: binding checksum stale? → PENDING (blocking) →
else validation passing? → MEASURED_PASSING → failing? → MEASURED_FAILING (healthy) →
no harness? → UNMEASURABLE (warning) → deferred? → DECLINED → open task? → PLANNED →
else PENDING. Insert it in the "One SR, four answers" section under the layer table.

- [ ] **Step 3: Verify**

pip tag-check or browser render both lessons in the classroom server and hard-refresh. Checkpoint: diagrams render, styling matches lesson 003.

## Task 1.7 — Gate I (review before delivery)

Run the full "Review gate" checklist against the Increment 1 outputs.

- [ ] **Step 1: Mechanical half (subagent)**

Dispatch one subagent with a bounded task: read the four edited files
(001/002/003 lessons, command card) plus <code>GLOSSARY.md</code> and the three quiz key files;
verify against <code>src/coherence/*/cli.py</code> and <code>src/factory/*/cli.py</code> that every verb/flag
cited exists; confirm no <code>factory.evidence.coverage</code>-style non-verb; confirm no stale
counts ("47") and no <code>kb-0006</code>-for-NAV-017 citation; confirm lesson 003's "today" is
true; report a pass/fail list with citations. (Reuse the earlier audit's method, scope
narrowed to Increment 1 files.)

- [ ] **Step 2: Pedagogical half (teacher)**

Read each edited lesson for: one-tight-win focus, retrieval-first quiz (no answer in
HTML), consistent vocabulary with the glossary, and that the Q&A-thread topics are at
least not contradicted.

- [ ] **Step 3: Render check**

Open <code>/c/system-traceability</code> in the classroom server; hard-refresh; verify 001/002/003
and the command card render (headings, tables, quiz submit, no broken links). If the
server is not running, <code>cd C:/coding/pi-agent-factory &amp;&amp; pif</code> and run <code>/classroom</code>.

- [ ] **Step 4: Record the gate**

Write <code>CR/learning-records/0001-increment-1-repair-gate.md</code> (follow
<code>LEARNING-RECORD-FORMAT.md</code>): what passed, what failed (if anything), the live-state
figures captured at gate time. Commit nothing in the repo unless a spec/plan file was
touched (stage only those).

---

# Increment 2 — The eight workflow lessons (seven untaught + progressive-assurance roadmap)

Goal: eight new lessons, each teaching one workflow end to end with exact live verbs (or,
for the roadmap lesson, the designed vocabulary), one worked example grounded in the
repo, one diagram where it earns its place, a retrieval-first quiz with key, and a
citation to the governing spec/source. Auto-numbering via <code>scaffold_lesson</code> gives
004-011 in creation order; create them in the order below so numbering matches the design
(004 progressive-assurance … 011 agent mechanics).

## Task 2.1 — Lesson 004: Progressive assurance (roadmap)

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="progressive-assurance-roadmap", title="Progressive assurance: obligations, profiles, nonconformances (roadmap)", summary="The designed, not-yet-shipped layer — obligations, profiles, typed justification, NC-* records, health vector.")</code>
- Modify: <code>CR/004-progressive-assurance-roadmap/lesson.html</code>
- Create: <code>CR/004-progressive-assurance-roadmap/quiz/key.json</code>

- [ ] **Step 1: Scaffold** (as above); then edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson** (dense, operator level). Sections:

1. **Why this lesson exists**: the roadmap is moving under the course; a newcomer must
   recognise the vocabulary and know it is designed, not shipped — teach "as of 2026-08-23"
   labelling from the start.
2. **The problem (seven gaps)**: summarise §1 of <code>2026-08-22-coherence-progressive-assurance-design.md</code>
   — validation error treated as warning on own SR; no task→defect link (T-031/issue #1);
   context manifest can pass with zero proof; nothing dogfooded end-to-end; health is one
   scalar; no CI; staleness doesn't distinguish never-reviewed from now-suspect.
3. **Progressive assurance model**: the minimal invariant kernel (seven rules, always
   active; rule 1: an execution error/missing executable/invalid result cannot become
   pass); the seven-dimension profile (<code>maturity, consequence, reversibility, volatility,
   verification_cost, exposure, collaboration</code>); scope precedence (artifact > feature >
   path > project; conflicts rejected not ordered); the compiled <code>Obligation</code>
   <code>{id, scope_ref, kind, requiredness, reason, source_policy, state, resolve_cmd}</code> with
   <code>requiredness ∈ {not_applicable, advisory, required, blocking}</code>.
4. **Typed relationships**: <code>justification:</code> kinds (satisfies/corrects/mitigates/implements/
   maintains/explores), legacy <code>satisfies:</code> as shorthand; typed lifecycle edges
   (intent/design/assurance/change); suspect edges <code>proposed|valid|suspect|invalid|waived</code>
   with the STRICT rule — no automatic path to <code>valid</code> at any requiredness; deferred/
   exempt gaps classify <code>waived</code>; only the gate protocol's DecisionFile <code>accept</code> restores
   <code>valid</code>.
5. **NC-* records**: <code>docs/nonconformances/NC-*.md</code>, mirror of <code>FR-*</code> (own dir/loader/schema,
   id-keyed, degrade-not-crash); frontmatter <code>id, title, external_ref (gh-issue:&lt;n&gt;),
   detected_by, status, corrected_by</code>; the T-031 → NC-0001 → issue #1 thread; external_ref
   is a citation, never a live sync.
6. **Health vector**: eleven dimensions; <code>coherence status</code> one-liner names the worst
   dimension, not an average; which dimensions are obligation-backed (4/5/11) vs direct
   queries (1/2/9/10) vs reclassified findings (3/7/8) — the corrected reading from §13.
7. **CI as obligation consumer**: D18 — CI reads the compiled obligation set (never a
   hand list); day-one commands = what <code>/factory-run</code> already gates + <code>coherence trace
   check</code>/<code>register check</code>; the §13 third divergence (day-one <code>blocking</code>).
8. **The increment map**: D15 (never reopen a shipped increment; 2B/2C/3B/6B new); the
   scheduling fork 2B→2C→3B→4→5→6→6B/7-8; 6B and 7/8 mutually cuttable.
9. **Live vs roadmap box**: explicit "NONE of this is in <code>src/</code> today" with the
   verified-absent list (no <code>src/substrate/policy/</code>, no <code>docs/nonconformances/</code>).

Citation: <code>docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md</code>
(+ the four 2026-08-22 increment plans for 2B/2C/3B/6B). Diagram: the increment-map fork
as inline SVG.

- [ ] **Step 3: Quiz + key** (retrieval; live-vs-roadmap discrimination). Key schema:

```json
{
  "pa-1": {
    "q1": {"answer": "c", "why": "requiredness is the four-value enum; the other options mix kinds, states or scopes."},
    "q2": {"answer": "b", "why": "A deferred/exempt gap classifies waived, and restoring valid always needs the gate protocol's DecisionFile accept — the STRICT rule."},
    "q3": {"answer": "a", "why": "Legacy satisfies: is shorthand for justification: [{satisfies: ...}]; no task file migration is required."},
    "q4": {"answer": "open", "why": "Looking for: designed-not-shipped; substrate.policy, coherence.policy, NC-* and the health vector do not exist in src/ as of 2026-08-23; the increment plans (2B/2C/3B/6B) are documents."}
  }
}
```

Questions mirror the lesson: q1 = what is <code>requiredness</code>? (options: a/b/c/d equal
length); q2 = how does a suspect edge return to <code>valid</code>?; q3 = is any task file
migration needed for typed justification?; q4 (short) = is this layer live or roadmap, and
what is your evidence?

- [ ] **Step 4: Verify**

Render in the classroom server; confirm every roadmap claim carries "as of 2026-08-23"
and nothing reads as a live command. Checkpoint: learner can name live-vs-roadmap and the
strict rule.

## Task 2.2 — Lesson 005: Staleness and checksums

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="staleness-and-checksums", title="Staleness and checksums", summary="When a measurement answers a question that has since changed — register index, sr_stale, freshness fingerprints, resolution classes.")</code>
- Modify: <code>CR/005-staleness-and-checksums/lesson.html</code>
- Create: <code>CR/005-staleness-and-checksums/quiz/key.json</code>

- [ ] **Step 1: Scaffold** (as above); edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **The story**: a binding's content hash no longer matches the SR's statement/binding —
   the measurement answers a question that has since changed. Distinguish from gap/suspect
   (roadmap) semantics.
2. **Where staleness lives**: <code>coherence register index</code> (exit 1 on any stale) and
   <code>coherence register status --stale</code>; <code>is_checksum_current</code>/<code>content_checksum</code>
   (<code>src/coherence/register/register.py</code>); the trace gap <code>sr_stale</code>
   (<code>src/coherence/trace/gaps.py</code>, "result predates a change to statement or binding");
   closure <code>PENDING</code> on stale checksum (<code>src/coherence/register/closure.py</code>).
3. **The freshness machinery**: <code>substrate.freshness</code> — <code>fingerprint_file</code>,
   <code>fingerprint_value</code>, <code>fingerprint_tool</code>, <code>fingerprint_git_tree</code>, <code>sha256_bytes</code>;
   <code>derived_auto | repeatable_policy | authoritative_gate | provenance_blocked</code>
   resolution classes; a stale snapshot stays addressable but is never rendered as current.
4. **Navigator freshness**: <code>coherence navigate freshness</code> and <code>catchup</code>; the
   <code>(freshness.state)</code> markers on every projection; codeindex fingerprint snapshot as the
   shipped <code>derived_auto</code> path (<code>src/factory/codeindex/</code>).
5. **Worked micro-example**: run <code>coherence register index</code> and <code>coherence register status
   --stale</code> in the repo; edit an SR statement and watch the checksum go stale;
   <code>coherence trace check</code> picks up <code>sr_stale</code>; then <code>coherence register bind ...
   --reaffirm REASON</code> refreshes. (Edit a scratch SR or revert after; keep the repo state
   clean.)
6. **Mention, don't teach**: suspect-edge <code>proposed|valid|suspect|invalid|waived</code> and the
   never-reviewed-vs-now-suspect distinction are roadmap (progressive-assurance lesson
   004).

Citation: <code>src/coherence/register/{cli,register,closure}.py</code>,
<code>src/coherence/trace/gaps.py</code>, <code>src/substrate/freshness/*</code>.
Diagram: the stale-checksum → PENDING → re-bind loop as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "stale-1": {
    "q1": {"answer": "b", "why": "Stale checksum → PENDING (blocking); a failing measurement is still healthy closure."},
    "q2": {"answer": "a", "why": "index exits 1 on any stale; status --stale lists only stale entries."},
    "q3": {"answer": "d", "why": "authoritative_gate routes to the owning writer; provenance_blocked reports a blocker; derived_auto rebuilds disposable indexes; repeatable_policy reruns within limits."},
    "q4": {"answer": "open", "why": "Looking for: the measurement is answering a question that has since changed; a stale snapshot stays addressable but is never rendered as current."}
  }
}
```

- [ ] **Step 4: Verify**

Run every cited command; confirm the repo is left clean (scratch edits reverted).
Checkpoint: learner can make a checksum stale and restore closure.

## Task 2.3 — Lesson 006: The doctor loop

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="doctor-loop", title="The doctor loop: from prose to measurable requirement", summary="context, mint, promote, task — and why an auditor proposes but never writes.")</code>
- Modify: <code>CR/006-doctor-loop/lesson.html</code>
- Create: <code>CR/006-doctor-loop/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **The claim pipeline**: prose → falsifiable SR (proposed, no binding) → measurable
   (bound) → task that satisfies it. <code>coherence doctor context|mint|promote|task</code>
   (<code>src/coherence/doctor/cli.py</code>).
2. **mint**: <code>coherence doctor mint --source SPEC --title T --statement S [--domain behavioral]</code>
   — creates a proposed SR (no binding). What makes a statement falsifiable (one
   measurable claim, no weasel words).
3. **promote**: <code>coherence doctor promote ID --harness H --experiment E --metric M --assert EXPR [--trials N]</code>
   — attaches the binding that makes it measurable. Closure states after promote
   (<code>MEASURED_*</code> once validation runs; <code>PENDING</code> while binding checksum fresh but
   unvalidated).
4. **task**: <code>coherence doctor task --satisfies SR-NNN --title T --dod D [--dod D ...]</code> —
   creates the work unit with definition-of-done.
5. **The write-discipline**: the doctor writes; an auditor (coverage) never authors the
   artifact it audits. Accepting an audit-proposed requirement routes through the doctor:
   context, mint, human confirm, promote. Rejecting/deferring writes a reason so the
   proposal doesn't return anonymously.
6. **Worked micro-example**: mint a scratch SR from a real spec paragraph, promote it
   with a tiny harness/assert, create a task; then delete the scratch artifacts to keep
   the repo clean.

Citation: <code>src/coherence/doctor/cli.py</code>, the doctor skill
<code>C:/coding/pi-agent-factory/.pi/skills/doctor/SKILL.md</code>.
Diagram: proposed→promoted→tasked chain as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "doctor-1": {
    "q1": {"answer": "c", "why": "mint creates a proposed SR with no binding; promote attaches the binding."},
    "q2": {"answer": "a", "why": "promote is the only verb that attaches harness/experiment/metric/assert."},
    "q3": {"answer": "d", "why": "An auditor may propose; only the doctor (context, mint, human confirm, promote) writes the SR."},
    "q4": {"answer": "open", "why": "Looking for: proposed has no binding; promoted has a binding and becomes measurable; the binding is what makes an SR measurable."}
  }
}
```

- [ ] **Step 4: Verify**

Run mint/promote/task on a scratch SR then clean up; confirm no scratch artifact remains.
Checkpoint: learner can take prose to a bound requirement to a task.

## Task 2.4 — Lesson 007: Evidence lifecycle and orchestrator recovery

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="evidence-lifecycle-recovery", title="Evidence lifecycle and orchestrator recovery", summary="Run manifests, run-state checkpoints, reconcile — and missing ≠ empty (TN-01).")</code>
- Modify: <code>CR/007-evidence-lifecycle-recovery/lesson.html</code>
- Create: <code>CR/007-evidence-lifecycle-recovery/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **The four data layers**: canonical artifacts (<code>requirements/</code>, specs, plans, tasks);
   derived index; immutable <code>evidence/runs/*.json</code> manifests; ignored
   <code>sessions/.factory-runs/</code> (source: <code>2026-08-07-factory-evidence-lifecycle-and-recovery-design.md</code>).
2. **factory.evidence verbs**: <code>run task record list reconcile</code>
   (<code>src/factory/evidence/cli.py</code>); what a manifest records (experiment, feature, SRs,
   goals, commit, result).
3. **Orchestrator run-state**: <code>factory.orchestrator run|list</code> and
   <code>factory.orchestrator run-state current|inspect|resume|restart|abandon|
   preserve-external-edits|doctor</code> (<code>src/factory/orchestrator/</code>); preflight gate is part
   of <code>run</code>, exit codes distinguish refused vs failed.
4. **Missing ≠ empty (TN-01)**: a task with no manifest audits differently from a task that
   ran and touched nothing — the FEAT-NAV-017 story (T-058/T-067 marked done with no
   manifest). This is why <code>evidence record</code> exists (recover missing evidence).
5. **Reconcile + recovery**: <code>factory.evidence reconcile</code>; the kb-0004 recovery story
   (run recovery: <code>run-state resume/restart/abandon</code>, <code>preserve-external-edits</code>).
6. **Worked micro-example**: <code>factory.orchestrator run-state current</code> in the repo; read a
   real manifest under <code>evidence/runs/</code>; show a task that lacks one.

Citation: <code>2026-08-07-factory-evidence-lifecycle-and-recovery-design.md</code>,
<code>src/factory/evidence/*</code>, <code>src/factory/orchestrator/run_cli.py</code>, <code>kb/kb-0004*</code>.
Diagram: the four-layer stack + run-state recovery arrows as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "ev-1": {
    "q1": {"answer": "a", "why": "reconcile is the cross-manifest read-side check; record recovers missing evidence."},
    "q2": {"answer": "c", "why": "run-state is the checkpoint-recovery surface; the preflight gate lives on run."},
    "q3": {"answer": "b", "why": "Missing ≠ empty (TN-01): no manifest audits differently from an empty run."},
    "q4": {"answer": "open", "why": "Looking for: a run manifest joining experiment, feature, SRs, goals, commit and result; immutable under evidence/runs/."}
  }
}
```

- [ ] **Step 4: Verify**

Run <code>factory.orchestrator run-state current</code> and <code>factory.evidence list</code>; cite real
output. Checkpoint: learner can locate manifests and drive recovery.

## Task 2.5 — Lesson 008: Navigator read-backs

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="navigator-readbacks", title="Navigator read-backs", summary="coherence.navigate — scope, brief, matrix, timeline, story, reverse, guide, and the comprehension-only rule.")</code>
- Modify: <code>CR/008-navigator-readbacks/lesson.html</code>
- Create: <code>CR/008-navigator-readbacks/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **The package**: <code>coherence.navigate</code> (was <code>factory.system</code>, now a shim) —
   comprehension-only. Exactly two writes: <code>guide --export</code> and <code>goal evaluate</code>
   (re-verify at gate).
2. **Scope refs**: <code>bundle: sr: task: file: adr: diag: feat: metric: goal:</code>;
   <code>coherence navigate scope</code> lists them.
3. **The projections**: <code>brief</code>, <code>matrix</code> (validation matrix, one row per SR),
   <code>timeline</code> (decision timeline), <code>vcycle</code> (definition+verification sides, goals,
   metrics), <code>story</code> (task → runs → requirements), <code>reverse</code> (file → run → task →
   requirements), <code>guide</code> (grounded prose or recorded bullets), <code>dossier</code>,
   <code>traversal</code>, <code>validation</code> (per-SR validation status), <code>health</code>, <code>labels</code>,
   <code>vocabulary</code>, <code>remediation</code>, <code>panels</code>, <code>freshness</code>, <code>catchup</code>, <code>diagram</code>,
   <code>memberships</code> (bundle membership; alias <code>membership</code>/<code>coverage</code>), <code>bundle check</code>.
4. **Reading order**: lower layer first — declared link → closure → ran → true (echoes
   lesson 002's four layers).
5. **What it cannot do**: never infers an edge, never writes except the two verbs, never
   repairs — <code>/system</code> shows the remediation command and copies it; running it is your job.
6. **Worked micro-example**: <code>coherence navigate scope</code>, <code>brief --scope bundle:&lt;x&gt;</code>,
   <code>story --scope task:T-031</code>, <code>reverse --scope file:&lt;path&gt;</code> in the repo.

Citation: <code>src/coherence/navigate/cli.py</code>, the navigator specs
(<code>2026-08-08</code>, <code>2026-08-14</code>, <code>2026-08-16</code>).
Diagram: the story vs reverse walk as a tiny inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "nav-1": {
    "q1": {"answer": "d", "why": "reverse walks file → run → task → requirements; story walks task → runs → requirements."},
    "q2": {"answer": "b", "why": "guide --export and goal evaluate are the only two writers."},
    "q3": {"answer": "c", "why": "The navigator never repairs; it shows/copies the remediation command."},
    "q4": {"answer": "open", "why": "Looking for: scope ref kinds (bundle: sr: task: file: adr: diag: feat: metric: goal:) and that everything is computed on demand, no cache."}
  }
}
```

- [ ] **Step 4: Verify**

Run the four worked commands; confirm output matches the lesson. Checkpoint: learner can
answer "what is this feature made of / which code backs this SR" from the CLI.

## Task 2.6 — Lesson 009: Coverage run flow

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="coverage-run-flow", title="Coverage run flow", summary="list-features → run → audit/verdict → consolidate → gate → report; the audit's two booleans and the degraded rule.")</code>
- Modify: <code>CR/009-coverage-run-flow/lesson.html</code>
- Create: <code>CR/009-coverage-run-flow/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **Why it exists**: requirement coverage, never line coverage; the design doc
   (<code>2026-08-17-requirement-coverage-review-design.md</code>).
2. **The verbs**: <code>factory.coverage list-features</code> → <code>run FEAT</code> → <code>audit FEAT
   --run-id</code> / <code>verdict</code> (per-SR subagent results) → <code>consolidate FEAT RUN_ID</code> →
   <code>gate FEAT RUN_ID</code> (0/1/2) → <code>report FEAT RUN_ID</code>; <code>failure</code> records
   tool failures (<code>src/factory/coverage/cli.py</code>).
3. **The two booleans**: <code>implemented</code> and <code>honest</code> per SR; the mechanical
   import-graph overlap underneath (codemap import edges, transitive closure ∩ changed
   files) — necessary, never sufficient, not code coverage.
4. **States + gate**: pass/suspect/unmeasured/unlinked/unverified/not_implemented/
   dishonest/declined; fail = unlinked/not_implemented/dishonest; warn =
   suspect/unmeasured; <code>degraded</code> is never a pass (subagent dispatch failure →
   <code>workflow_issues</code>).
5. **Auditor never writes**: proposals route through the doctor (echo 006); the audit
   artifact (<code>coverage-reviews/&lt;FEAT&gt;-&lt;run-id&gt;/</code>) is regenerable.
6. **Worked micro-example**: <code>factory.coverage list-features</code>; if a small feature exists,
   run the audit on it (or use the design doc's FEAT-NAV-017 story as the example).

Citation: <code>src/factory/coverage/{cli,audit,gate,scope}.py</code>,
<code>2026-08-17-requirement-coverage-review-design.md</code>.
Diagram: the run→audit→gate pipeline as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "cov-1": {
    "q1": {"answer": "a", "why": "Empty import-graph overlap yields suspect even when the measurement passes."},
    "q2": {"answer": "b", "why": "degraded is never a pass; a subagent dispatch failure is recorded in workflow_issues."},
    "q3": {"answer": "c", "why": "audit/verdict captures the per-SR subagent judgements; gate is the exit-code decision."},
    "q4": {"answer": "open", "why": "Looking for: implemented and honest; honest requires implemented; the mechanical overlap underneath is necessary-not-sufficient."}
  }
}
```

- [ ] **Step 4: Verify**

Run <code>factory.coverage list-features</code>; confirm the states table matches
<code>src/factory/coverage/audit.py</code>. Checkpoint: learner can drive a feature audit and read
its gate exit.

## Task 2.7 — Lesson 010: Goals and simulation

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="goals-and-simulation", title="Goals and simulation", summary="coherence.goals and coherence.simulation — goal lifecycle, metrics, and the evaluate edge rules.")</code>
- Modify: <code>CR/010-goals-and-simulation/lesson.html</code>
- Create: <code>CR/010-goals-and-simulation/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. Sections:

1. **The goal layer**: <code>coherence.goals list|show|create|set-state|evaluate|history</code>
   (<code>src/coherence/goals/</code>); a goal binds a contract to feature/requirement refs and a
   target; metric history via <code>coherence navigate sim metric</code>.
2. **Simulation**: <code>coherence.simulation runs|sensitivity</code>
   (<code>src/coherence/simulation/</code>); run manifests list <code>goal_id</code>; evidence for a goal =
   its simulation runs (ascending by run id).
3. **The evaluate lifecycle**: <code>coherence.goals evaluate GOAL</code> runs the auto-eval against
   the latest simulation run and records a transition only when the lifecycle (spec §13)
   permits; an illegal edge or no measurable run reports without writing. This is the one
   goal-write path (besides create/set-state) and it is the only eng_* action tool.
4. **Navigator goal surface**: <code>coherence navigate goal show|list|evaluate</code>, <code>sim
   run|latest|failure|metric|goal-evidence</code> — read-only projections over the same data.
5. **Worked micro-example**: <code>coherence.goals list</code>, <code>show &lt;id&gt;</code>, and
   <code>coherence navigate sim metric &lt;metric_id&gt;</code> on a real goal.

Citation: <code>src/coherence/{goals,simulation}/*</code>, the goals spec (goal lifecycle §13).
Diagram: goal → latest run → evaluate → transition as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "gol-1": {
    "q1": {"answer": "b", "why": "evaluate is the auto-eval action that writes goal state only on a permitted lifecycle edge."},
    "q2": {"answer": "a", "why": "goal evidence is its simulation runs, ascending by run id, from the manifests."},
    "q3": {"answer": "d", "why": "an illegal lifecycle edge or a run with no measurable goal reports without writing."},
    "q4": {"answer": "open", "why": "Looking for: runs|sensitivity verbs and that sensitivity explores parameter changes across runs."}
  }
}
```

- [ ] **Step 4: Verify**

Run list/show/sim metric on a real goal; do not call evaluate (it writes). Checkpoint:
learner can read goal state and evidence without writing.

## Task 2.8 — Lesson 011: Agent mechanics of the trace tools

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="agent-mechanics-trace", title="Agent mechanics of the trace tools", summary="How the model-judge loop really works: trace_next hands every candidate, the trace tools are the only writers, check re-derives from disk.")</code>
- Modify: <code>CR/011-agent-mechanics-trace/lesson.html</code>
- Create: <code>CR/011-agent-mechanics-trace/quiz/key.json</code>

- [ ] **Step 1: Scaffold**; edit the returned <code>lesson.html</code>.

- [ ] **Step 2: Write the lesson**. This is the lesson your Q&A threads asked for; teach the
   implementation, not just the surface. Sections:

1. **The deterministic split in practice**: code enumerates, holds state, writes, verifies;
   the model makes exactly one judgement per step. Where each trace tool sits.
2. **trace_next**: returns the pending gap + EVERY candidate requirement with its full
   statement, ranked by word-overlap as a lexical hint only, with the instruction to judge
   by meaning. It never filters; never truncates the list.
3. **The writers**: <code>trace_link</code> (satisfies/spec/source_plan), <code>trace_exempt</code> (tasks/
   plans only, never an SR), <code>trace_defer</code> (reason required). Each validates its target
   exists and refuses a dangling write. The model's text never touches the files; only the
   tool writes.
4. **Why no inference**: a link is a semantic judgement, not a string match; a wrong link
   poisons every downstream projection (echo lesson 001's refusal, now with the mechanism).
5. **trace_check**: stateless, re-derives every gap and disposition from disk on every run;
   a model's account of its own progress carries no weight; deferred/exempt pass, pending
   fails.
6. **The skill layer**: the trace-fix skill (<code>C:/coding/pi-agent-factory/.pi/skills/trace-fix/SKILL.md</code>)
   is the procedure /trace-fix routes into; the tool surface is declared in AGENTS.md so
   every session shares the same contract; the reasoning is written before the write so a
   human can watch.
7. **Worked micro-example**: walk one real gap: <code>coherence trace next</code>, read the
   candidates, propose the link with reasoning, then the write — and show what
   <code>coherence trace check</code> does before and after.

Citation: <code>src/coherence/trace/*</code>, the trace-fix skill, AGENTS.md factory tools block.
Diagram: see → propose → write → re-check loop as inline SVG.

- [ ] **Step 3: Quiz + key**:

```json
{
  "mech-1": {
    "q1": {"answer": "c", "why": "trace_next returns every candidate with full statements; the word-overlap order is a hint, never a filter."},
    "q2": {"answer": "a", "why": "only the trace tools write; the model proposes and the tool validates the target before writing."},
    "q3": {"answer": "d", "why": "check re-reads the files every time; a claim of done carries no weight."},
    "q4": {"answer": "open", "why": "Looking for: the reason-ahead-of-write so a human can audit, and that an undeclared edge does not exist for the graph."}
  }
}
```

- [ ] **Step 4: Verify**

Run <code>coherence trace next</code> and <code>coherence trace check</code>; confirm the lesson's claims
match live output. Checkpoint: learner can explain the model-judge loop and watch it run.

## Task 2.9 — Gate II (review before delivery)

- [ ] **Step 1: Mechanical half (subagent)**

Dispatch one subagent: read the eight new lessons; verify every cited verb/flag exists in
live argparse (<code>src/coherence/*/cli.py</code>, <code>src/factory/*/cli.py</code>); confirm no lesson
teaches a roadmap command as live (progressive-assurance lesson must carry the
"as of 2026-08-23, not shipped" label throughout); confirm quiz keys match the 001/002
schema and no answer key is in any HTML; report pass/fail with citations.

- [ ] **Step 2: Pedagogical half (teacher)**

Read each lesson for: one tight win, worked example grounded in the repo, retrieval-first
quiz (equal-length options), consistent glossary vocabulary, and that each covers its
Q&A-thread topic if one exists (esp. 011 covers the mechanics threads).

- [ ] **Step 3: Render + links**

Open <code>/c/system-traceability</code>, hard-refresh, verify all eight lessons render, quizzes
submit, keys load (grading path), and cross-links to 001-003 and the command card resolve.

- [ ] **Step 4: Record the gate**

Write <code>CR/learning-records/0002-increment-2-workflows-gate.md</code>. Commit nothing in the
repo unless a spec/plan file was touched (stage only those).

---

# Increment 3 — The 0→100% spine and the roadmap

Goal: make the course a single arc a newcomer can follow from zero, add the roadmap
perspective, ship the course-map diagram, and pass the full-course gate.

## Task 3.1 — Lesson 000: From zero to operator (the spine)

**Files:**
- Create via <code>scaffold_lesson(classroom="system-traceability", name="from-zero-to-operator", title="From zero to operator", summary="The sequenced tour: what the framework does, the one loop, the tools, agent mechanics, workflows, and the roadmap.")</code>
- Rename the created dir to <code>CR/000-from-zero-to-operator/</code> (the scaffolder would number it 012; the spine must lead)
- Modify: <code>CR/000-from-zero-to-operator/lesson.html</code> and <code>lesson.json</code>
- Create: <code>CR/000-from-zero-to-operator/quiz/key.json</code>

- [ ] **Step 1: Scaffold, then rename**

Call <code>scaffold_lesson</code> with the params above (creates <code>012-from-zero-to-operator</code>),
then move the directory: <code>mv CR/012-from-zero-to-operator CR/000-from-zero-to-operator</code>.
The server reads ordering from the directory prefix (<code>orderPrefix</code> parses a leading
number), so 000 sorts first. No <code>lesson.json</code> edit is needed for ordering (it carries no
name field), but update nothing that references the old dir.

- [ ] **Step 2: Write the lesson** — the entry point. Sections:

1. **What the framework does** (one paragraph + the loop diagram from lesson 001): prose
   becomes claims, claims link to work, work produces evidence, evidence is judged, all
   read back — behind gates that re-derive from disk.
2. **The deterministic split** as the load-bearing idea: code enumerates/holds state/
   writes/verifies; the model makes exactly one judgement per step.
3. **The course map** (link the diagram from Task 3.3): 000 spine → 001 routing → 002
   verdicts → 003 programme → 004 progressive-assurance (roadmap) → 005 staleness → 006
   doctor → 007 evidence/recovery → 008 navigator → 009 coverage flow → 010 goals/sim →
   011 agent mechanics; note 004 is roadmap, the rest live.
4. **Your first loop** (the one thing a newcomer can do immediately):
   <code>coherence trace check</code> (see the gate fail), <code>coherence trace next</code> (see the
   candidates), <code>coherence trace defer</code> (make one honest disposition), re-check —
   without linking anything yet.
5. **Where to look next**: the command card (<code>/r/system-traceability/command-card.html</code>),
   glossary, and lesson links.

- [ ] **Step 3: Quiz + key** (orientation, retrieval):

```json
{
  "spine-1": {
    "q1": {"answer": "d", "why": "check re-derives every gap from disk each run; nothing else can make it green."},
    "q2": {"answer": "b", "why": "004 is the progressive-assurance roadmap lesson; the rest of the spine is live."},
    "q3": {"answer": "a", "why": "the deterministic split: code enumerates/holds state/writes/verifies; the model makes exactly one judgement per step."},
    "q4": {"answer": "open", "why": "Looking for: an honest first disposition (defer with a reason) without inventing a link."}
  }
}
```

- [ ] **Step 4: Verify**

Open <code>/c/system-traceability</code> — 000 must sort first; the map links resolve.
Checkpoint: a newcomer can start and finish their first loop in one sitting.

## Task 3.2 — Roadmap perspective (current vs planned)

**Files:**
- Modify: <code>CR/003-coherence-programme/lesson.html</code> (cross-link)
- Content lands inside lesson 000 (section 6) as designed in Task 3.1, plus a cross-link from 003

- [ ] **Step 1: Add the roadmap-perspective section to lesson 000**

After "Your first loop", add a section "Today vs roadmap (as of 2026-08-23)" that distils
the audit's split for a newcomer: LIVE = coherence.{trace,register,doctor,navigate,
presentation,goals,simulation}, substrate, factory.{coverage,evidence,orchestrator,
validation}; ROADMAP = coherence.{audit,measurement,status,focus,gate,inbox,explain},
progressive-assurance layer (004), one-gate protocol, /using-coherence,
/factory-selfcheck, envelope migration. State plainly what will NOT survive the carve:
residual <code>factory.*</code> renames, <code>coverage</code>→<code>membership</code> (already parallel today),
<code>/factory-doctor</code>→<code>/factory-selfcheck</code>.

- [ ] **Step 2: Cross-link 003**

In <code>CR/003-coherence-programme/lesson.html</code> "Go deeper" add:

```html
<p>For the newcomer-facing current-vs-roadmap split, start at
<a href="../000-from-zero-to-operator/lesson.html">From zero to operator</a>.</p>
```

- [ ] **Step 3: Verify**

Render 000 and 003; the cross-link resolves. Checkpoint: live-vs-roadmap is one page away
from anywhere in the course.

## Task 3.3 — Course map diagram (committed HTML in assets/)

**Files:**
- Create: <code>CR/assets/course-map.html</code> (via <code>tff-generate_visual</code>, type <code>flowchart</code> or <code>plan</code>, aesthetic matching the classroom)

- [ ] **Step 1: Generate**

Use <code>tff-generate_visual</code> with type <code>flowchart</code> and the mermaid content of the lesson
flow: 000 → 001 → 002 → 003 → {004 (roadmap), 005, 006, 007, 008, 009, 010, 011}, with
prerequisite edges (003 ← 002 ← 001 ← 000; workflow lessons depend on 001/002; 011
reuses 001's loop; 004 references 003). Title: "System Traceability — Course Map".
Filename: <code>course-map.html</code>. If the tool writes elsewhere, move it to
<code>CR/assets/course-map.html</code>.

- [ ] **Step 2: Link it from lesson 000**

In lesson 000's course-map section:

```html
<p>Full interactive map:
<a href="/c/system-traceability/assets/course-map.html">Course map</a>.</p>
```

- [ ] **Step 3: Verify**

Open the asset URL in the classroom server; the map renders and the link works.
Checkpoint: the course has one visual map a newcomer can navigate.

## Task 3.4 — Gate III (full-course review before delivery)

- [ ] **Step 1: Full mechanical audit (subagent)**

Dispatch one subagent: read ALL lessons (000-011) + command card + glossary + every quiz
key; verify every cited verb/flag against live argparse; confirm no roadmap command is
taught as live; confirm the FEAT-NAV-017 root cause is one story across 002/003; confirm
quiz keys uniform and no answers in HTML; scan for dead internal links (grep
<code>../.../lesson.html</code> hrefs against existing dirs). Report pass/fail with citations.

- [ ] **Step 2: Full pedagogical read (teacher)**

Read the whole course top to bottom as a newcomer would (000 first): check the arc holds,
each lesson's win is delivered, prerequisites are respected, and every Q&A-thread topic
is covered or explicitly deferred.

- [ ] **Step 3: Render sweep**

Open <code>/c/system-traceability</code>, hard-refresh, walk every lesson + card + asset in the
browser; submit one quiz to verify the grading round-trip; verify lesson ordering
(000 first, then 001-011).

- [ ] **Step 4: Live-state snapshot + record**

Capture <code>coherence trace check</code> output and the lesson list into
<code>CR/learning-records/0003-increment-3-spine-gate.md</code> with the full-course verdict.

- [ ] **Step 5: Ship note**

Tell the learner the course is live at <code>/c/system-traceability</code>, which increments
shipped, what the gate found, and that the next review is due whenever the surface
changes again (the plan's Ground-truth snapshot is dated and must be re-verified).

---

# Self-review (run before execution handoff)

- **Spec coverage:** every § of the design doc maps to tasks: Inc1 = §5 Inc1 (1.1-1.7), Inc2
  = §5 Inc2 incl. the progressive-assurance lesson (2.1-2.9), Inc3 = §5 Inc3 (3.1-3.4); review
  gate §7 is Gate I/II/III (1.7, 2.9, 3.4); acceptance §8 = gate records + spine check.
- **Placeholder scan:** no TBD/TODO; every step has an exact command or exact content spec;
  the only "if available" choices are explicitly flagged (live counts, feature availability).
- **Type consistency:** lesson ids/numbering are consistent (000 + 004-011; scaffold order =
  design order); key schema is uniform (`{"check-1"|... : {q1: {...}}}`); verbs cited match
  the Ground-truth snapshot; `CR` is defined once in Conventions.

# Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-23-system-traceability-course-overhaul.md`.**
Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between
   tasks (the Gate tasks already specify the subagent review half).
2. **Inline Execution** — I execute tasks in this session with checkpoints at each gate.

Which approach?
