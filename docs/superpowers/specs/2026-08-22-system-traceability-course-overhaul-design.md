# System-Traceability Course Overhaul — Design (amended)

> Status: design (not yet approved). Applies to the pi-teach classroom
> `system-traceability` at `~/.pi/agent/classrooms/system-traceability/`, whose content
> is the deliverable this design governs. Ground truth is the factory repo at
> `C:/coding/pi-agent-factory`, re-verified against `docs/coherence-progressive-assurance-design`
> HEAD `c9e94ab` (2026-08-22).
>
> **Supersession note:** a first version of this design was committed as `3250f7e` on
> `fix/kb-0004-run-recovery`. The working tree moved to `docs/coherence-progressive-assurance-design`
> (parallel session); this amended version supersedes it on that branch. Both remain in git
> history; this document is the operative one for the course update.

## 1. Context and problem

The classroom teaches an operator how to use the pi-agent-factory traceability and
coherence tool surface (mission: at any moment be able to say what the system is, which
requirement each artifact serves, and where the story broke; the ultimate consumer
project is `cool_physical_ai_project`). The learner is the factory's author: operator
level, dense, exact syntax, everything grounded in the live local surface.

On 2026-08-22 the tool surface outran the course twice in one day. Two read-only audits
(one subagent per half: specs-vs-code, lessons-vs-live-CLI) found, with file citations:

- The course teaches `factory.<pkg>` as the primary invocation, but the primary surface
  is now `coherence <group>` / `python -m coherence.<group>`; `factory.*` survives only
  as `DeprecationWarning` shims (`src/factory/trace/__init__.py`,
  `src/factory/requirements/__init__.py`, `src/factory/doctor/__init__.py`).
- The Coherence programme has partially landed: `src/coherence/` exists (`trace`,
  `register`, `doctor`), a `coherence` console entry exists
  (`pyproject.toml`, `src/coherence/__main__.py`), `substrate/` is a populated shared
  package (`freshness/{recipes,guard,fingerprint}`, `codemap/imports` = TN-13, `kb`,
  `artifacts`, `observations`, `projections`), and `coherence.trace unlink` (TN-03) exists.
- Lesson 003's "today, the whole programme is documents" section is therefore false (four
  specific claims, all now contradicted by code). Lesson 001 quotes a stale gap count (47;
  live today: 65 pending, 1 deferred, 2 exempt). Lesson 002 cites `kb-0006` for the
  FEAT-NAV-017 audit blindness, but `kb/kb-0006-*.md` is about sim-test flakiness — and
  002 and 003 give opposite root causes for the same event.
- Command card omits ~15 live `factory.system` verbs (`dossier`, `worker`, `traversal`,
  `validation`, `catchup`, `diagram`, `present`, `freshness`, the `sim` subtree), whole
  package sections (`evidence`, `orchestrator`, `validation`, `goals`, `simulation`,
  `presentation`), the new `unlink` verb, and carries one broken link
  (`../001-the-traceability-surface/` does not exist).
- The learner's own Q&A threads (annotations.json: "why won't it invent a link from a
  filename / exempt a requirement", "how do you use a model to create the link — how was
  this implemented in the coding agent") probe the agent-mechanics of the trace tools —
  a topic no lesson covers.

### 1.1 Second-wave drift (evening 2026-08-22, after the audits)

Before this design could be approved, the roadmap moved again, per
`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`
(which amends the toolset design's §11/§3 and the execution map) and four new
implementation plans (`2026-08-22-coherence-increment-{2b,2c,3b,6b}-*.md`):

- **Increment 3 shipped**: `src/coherence/{navigate,presentation,goals,simulation}` now
  exist; the `coherence` console entry dispatches seven groups (trace, register, doctor,
  navigate, presentation, goals, simulation — `src/coherence/cli.py`); `factory.system`
  is now a shim to `coherence.navigate` ("factory.system is deprecated; use
  coherence.navigate" — `src/factory/system/__main__.py`), and `factory.goals`,
  `factory.simulation`, `factory.presentation` are shims likewise.
- **`coherence.navigate` gains the coverage→membership rename as a parallel verb**: the
  verb list now carries both `coverage` (old) and `membership`/`memberships` (new) — the
  toolset design's "rename, not absorb" landing as a transition state.
- **The progressive-assurance spec adds a whole roadmap layer that has NOT shipped**:
  `substrate.policy` (profile vocabulary + `Obligation` contract), `coherence.policy`
  (compiler), typed task `justification:` (satisfies/corrects/mitigates/implements/
  maintains/explores), `docs/nonconformances/NC-*.md` records, the seven-dimension
  profile vocabulary, the eleven-dimension health vector, suspect-edge
  `proposed|valid|suspect|invalid|waived` states, CI as a compiled obligation consumer,
  and the thin vertical slice. Verified absent today: no `src/substrate/policy/`, no
  `docs/nonconformances/` (checked directly). Increments 4 (`audit/measurement`), 5
  (`status/focus`), 6 (`gate/inbox`) remain unbuilt.
- Ground truth below reflects this second wave. Where a lesson must choose, THE COURSE
  TEACHES WHAT EXISTS (coherence.* incl. increment 3) AS CURRENT and the progressive-
  assurance vocabulary AS ROADMAP (nothing shipped).

## 2. Verdict on representativeness (the question asked)

"Review the specs, put them in perspective with what you're teaching: is it
representative, and is the drift expected?"

| Spec family | Status in code | Today's course | Verdict |
|---|---|---|---|
| Coverage review (`2026-08-17-requirement-coverage-review-design.md`) | CURRENT (`factory.coverage` full suite; per-SR subagent; codemap overlap; `--gate` re-derives) | Lesson 002, accurate | Representative |
| Evidence lifecycle (`2026-08-07-factory-evidence-lifecycle-and-recovery-design.md`) | CURRENT (`factory.evidence`, orchestrator `run-state` recovery surface, kb-0004) | absent | Gap (not representative) |
| Toolset design + increment 3 (`2026-08-18-…`, `2026-08-20-coherence-programme-execution-map.md`) | MIXED, more shipped: coherence.{trace,register,doctor,navigate,presentation,goals,simulation} + substrate live; status/focus/gate/inbox/using-coherence/selfcheck absent | Lesson 003 teaches 0-3 as "docs only" (now false in both waves) | Drift — **expected** (code landed under the course) but must be re-taught current-vs-roadmap |
| Agentic I/O (`2026-08-20-coherence-agentic-io-design.md`) | MIXED: contracts real (`substrate/observations.py`, `projections.py`, freshness resolver classes); no producer wraps output in an envelope yet | absent | Gap; teach "contract now, producer migration = roadmap" |
| Comprehension layer, briefing/validation guide, feature spine, context packet, curation, legibility (`2026-08-08/10/11/14/16`) | CURRENT — now under `coherence.navigate` (increment 3 migrated them) | absent (verb list only, and under wrong package name) | Gap (not representative; package rename compounds it) |
| Progressive assurance (`2026-08-22-coherence-progressive-assurance-design.md`) | ROADMAP — plan files + spec only; `substrate.policy`, `NC-*`, typed justification, health vector not in code | absent | Gap in coverage; but teach as roadmap, not current |

Overall: partial representation. The large drift is **expected** — the roadmap shipped
(often twice in one day) while the course stood still. A few defects are **unexpected**
and must be repaired (wrong citation, contradictory lessons, a taught non-verb
`factory.evidence.coverage`, stale package names).

## 3. Goal and non-goals

**Goal:** a course that (a) is true against the live surface as of 2026-08-22 (second
wave) and re-verifies at each delivery, (b) covers every untaught workflow with a
dedicated lesson, (c) lets a newcomer go 0→100%: what the framework does → the one loop →
the tools → agent mechanics → each workflow → the roadmap, (d) carries a small number of
earned diagrams, and (e) passes a defined review gate before any increment ships to the
learner.

**Non-goals:** no factory internals changes; no instrumented code coverage; no
re-teaching "what is a requirement" (operator level); no classroom-runtime changes; no
new factory features; the course speaks about the roadmap (including the progressive-
assurance layer), it does not implement it.

## 4. Ground truth frozen at 2026-08-22 (second wave) — what lessons must teach

Live verb surface (source of truth for every lesson; verified by argparse scan of
`src/coherence/*/cli.py` and `src/factory/*/cli.py` at `c9e94ab`):

- **`coherence` console entry, seven groups**: trace, register, doctor, navigate,
  presentation, goals, simulation (`src/coherence/cli.py` GROUPS). Everything else
  (`evidence`, `orchestrator`, `validation`, `coverage`, `preflight`, `polish`,
  `codeindex`) remains under `factory.*` today — mix is expected and taught as such.
- `coherence.trace`: status, graph, link, unlink (TN-03), next, check, exempt, defer.
  11 gap kinds (as in `src/coherence/trace/gaps.py`); dispositions pending/exempt/deferred;
  exempt refused for `sr`/`br`.
- `coherence.register` (was `factory.requirements`): new, index, status (`--stale`), show,
  bind, defer, check, next. Closure states
  `MEASURED_PASSING/MEASURED_FAILING/PLANNED/UNMEASURABLE/DECLINED/PENDING`; stale binding
  checksum → `PENDING` blocking (`src/coherence/register/closure.py`).
- `coherence.doctor` (was `factory.doctor`): context, mint, promote, task.
- `coherence.navigate` (was `factory.system`): brief, dossier, worker, matrix, timeline,
  story, reverse, guide, traversal, vcycle, validation, catchup, diagram, sim
  (run/latest/failure/metric/goal-evidence), goal (show/list/evaluate), present, scope,
  health, freshness, labels, vocabulary, remediation, panels, memberships, bundle check,
  **new**, coverage, membership. Reads only except `guide --export` and `goal evaluate`
  (and any goal-write lifecycle once increment on goals lands — verify at gate).
  Note the `coverage`→`membership` rename: both verbs exist today (transition state).
- `coherence.goals`: list, show, create, set-state, evaluate, history.
  `coherence.simulation`: runs, sensitivity. `coherence.presentation`: present.
- `factory.coverage`: list-features, run, audit, verdict, consolidate, gate (0/1/2),
  report, failure. Eight per-SR states; fail = unlinked/not_implemented/dishonest; warn =
  suspect/unmeasured.
- `factory.evidence`: run, task, record, list, reconcile. `factory.orchestrator`: run,
  list, run-state (current/inspect/resume/restart/abandon/preserve-external-edits/doctor).
  `factory.validation`: run.
- Slash commands inside pif (from `pi-ext/factory-watch/src/index.ts` and command files):
  /system, /trace-fix, /coverage-review, /factory-doctor, /review-plans, /goal, /factory,
  /factory-run, /factory-tasks, /factory-stop, /factory-watch, /plan, /polish, /catchup,
  /task, /factory-init, /visual-explain, /clear.
- Roadmap (NOT implementable today; teach as such, label "as of 2026-08-22"):
  - `coherence.{audit, measurement, status, focus, gate, inbox, explain}` (increments 4-6).
  - Progressive-assurance layer (spec 2026-08-22, increments 2B/2C/3B/6B — plans exist,
    zero code): `substrate.policy` profile vocabulary + `Obligation` contract;
    `coherence.policy` compiler; typed `justification:` replacing bare `satisfies`;
    `docs/nonconformances/NC-*.md` records; seven-dimension profile; eleven-dimension
    health vector; suspect-edge `proposed|valid|suspect|invalid|waived` + STRICT
    no-auto-`valid` rule; CI as compiled obligation consumer; thin vertical slice dogfood
    (T-031 → NC-0001 → issue #1). The course names these so a newcomer recognises them,
    and states they are designed, not shipped.
  - One-gate protocol decision file; `/using-coherence` router + skill;
    `/factory-selfcheck` rename; envelope-wrapping of every producer (agentic I/O §9).

## 5. Architecture: three increments, strict order, each gated

The bombshell scope (repair + seven new workflows + 0→100% spine + visuals + review +
second-wave regeneration) cannot be one pass. Deliver in strict order 1 → 2 → 3
(learner-approved), each ending in the review gate (§7); the next increment does not start
until the gate passes.

### Increment 1 — Repair and re-ground the existing surface (second wave)

- **001-routing-the-question**: drop/refresh the "47 gaps" figure (state: counts move;
  prefer "the gate is red — live: 65 pending, deferred and exempt pass"); retarget the
  primary invocation to `coherence <group>` / `python -m coherence.*` (state that
  `factory.*` shims still work with a warning, and that the shim surface now covers
  system/goals/simulation/presentation too); fix Trap 1 (replace the non-verb
  `factory.evidence.coverage` with what the evidence CLI actually offers: run/task/record/
  list/reconcile); fix the "preflight refuses → run-state" row (preflight refusal comes
  from `factory.orchestrator run`'s preflight gate; `run-state` is the checkpoint
  recovery surface).
- **002-four-verdicts**: replace the `kb-0006` citation with the real source (the
  coverage-review design doc's root cause: `T-058`/`T-067` marked done with no manifest →
  empty changed-files → blind overlap; reconcile 002 and 003 on this); name the write side
  `factory.validation run` (which writes `validation/validation-report.json`) so the
  "layers" table teaches a verb, not a noun.
- **003-coherence-programme**: rewrite the "today" section to the LIVE second-wave state:
  shipped = substrate + coherence.{trace,register,doctor,navigate,presentation,goals,
  simulation} + unlink + coverage→membership rename (parallel verb); roadmap = increments
  4-8 (status/focus/gate/inbox/explain, audit/measurement) AND the 2B/2C/3B/6B
  progressive-assurance layer (obligations, profiles, justification, NC-*, health vector,
  CI consumer). Label every roadmap claim "as of 2026-08-22". Do NOT teach the
  progressive-assurance vocabulary as live commands.
- **Command card** (`reference/command-card.html`): rewrite to the live surface — primary
  `coherence` entry + the 7-group console; add the ~15 missing navigate verbs and the sim
  subtree; add evidence/orchestrator/validation/simulation/presentation/goals sections;
  add `unlink`, `membership`; fix the broken "related lessons" link (point at
  001-routing-the-question).
- **GLOSSARY.md**: add `unlink`, `deprecation shim`, `roadmap-vs-live` markers, and the
  progressive-assurance terms (profile, obligation, justification, NC-*) tagged as
  roadmap; align closure-state and gap-kind lists with the frozen surface.
- **Quiz-key contract**: fix `003/quiz/key.json` to the `{"check-1": {...}}` schema used
  by 001/002 (003 currently uses a flat `{"q1": "a"}` shape).
- **Diagrams (2, inline SVG like lesson 003's existing figures)**: (a) the one-loop/six-
  tools diagram (doctor→trace→orchestrate→coverage→system→check) with the model-judge
  seam marked; (b) the trace-graph + closure decision diagram (gap kinds → disposition →
  gate exit).
- **Gate I** (see §7).

### Increment 2 — The eight workflow lessons (seven untaught + progressive-assurance roadmap)

One lesson per workflow. Each: exact live verbs (or, for the roadmap lesson, the designed vocabulary), one worked micro-example against the
real repo state, one diagram where it earns its place, a retrieval-first quiz, and a
citation to the governing spec or source file.

0. **Progressive assurance: obligations, profiles, nonconformances (roadmap)** — added at
   the learner's request after the second-wave amendment. Teaches the vocabulary as
   **designed, not shipped**: the seven-dimension profile (`maturity`, `consequence`,
   `reversibility`, `volatility`, `verification_cost`, `exposure`, `collaboration`), the
   compiled `Obligation` contract `{id, scope_ref, kind, requiredness, reason,
   source_policy, state, resolve_cmd}` with `requiredness`
   `not_applicable|advisory|required|blocking`, typed task `justification:`
   (satisfies/corrects/mitigates/implements/maintains/explores), `docs/nonconformances/
   NC-*.md` records (mirror of `FR-*`, `external_ref: gh-issue:<n>`, `corrected_by:
   T-031`), the eleven-dimension health vector, suspect-edge
   `proposed|valid|suspect|invalid|waived` with the STRICT no-auto-`valid` rule, CI as a
   compiled obligation consumer (D18), and the increment map 2B→2C→3B→4→5→6→6B/7-8 with
   D15 (never reopen a shipped increment). Grounded in
   `2026-08-22-coherence-progressive-assurance-design.md`; every command-level claim
   carries the "as of 2026-08-22, not shipped" label. Quiz asks the learner to
   distinguish live-vs-roadmap and name the strict rule — retrieval, not recognition.
1. **Staleness and checksums** (the named gap):
   `coherence.register index|status --stale`, trace gap `sr_stale`, `is_checksum_current`,
   `content_checksum`, `substrate.freshness` fingerprints, `derived_auto/repeatable_policy/
   authoritative_gate/provenance_blocked`, codeindex fingerprint snapshot, `coherence
   navigate freshness`/`catchup`. Story: "the measurement is answering a question that has
   since changed". Mention suspect-edge states (roadmap) only as "coming, not here yet".
2. **The doctor loop**: `coherence.doctor context|mint|promote|task`; proposed SR ↔
   binding; promote with harness/experiment/metric/assert; auditor proposes, never writes;
   accept routes through the doctor, reject/defer writes a reason.
3. **Evidence lifecycle and orchestrator recovery**: `factory.evidence run|task|record|
   list|reconcile`; immutable run manifests under `evidence/runs/`; `factory.orchestrator
   run-state current|inspect|resume|restart|abandon|preserve-external-edits|doctor`; the
   kb-0004 recovery story; "missing ≠ empty" (TN-01).
4. **Navigator read-backs (coherence.navigate)**: scope/brief/matrix/timeline/vcycle/
   story/reverse/guide/validation/catchup/freshness/health/remediation/memberships/bundle
   check/coverage/membership gates; comprehension-only (two writes only); reading order
   lower-layer-first; teach under the NEW package name.
5. **Coverage run flow**: list-features → run → audit/verdict → consolidate → gate →
   report; one read-only subagent per SR; `degraded` never a pass; the `failure` verb;
   artifacts under `coverage-reviews/<FEAT>-<run-id>/`.
6. **Goals and simulation**: `coherence.goals` list/show/create/set-state/evaluate/
   history; `coherence.simulation` runs|sensitivity; metric history; goal-evidence; the
   evaluate lifecycle edge rules.
7. **Agent mechanics of the trace tools**: how `trace_next` hands every candidate, how
   `trace_link/exempt/defer` are the only writers and validate targets exist, why the
   model's text never touches files, `check` re-derives from disk — the model-judge loop
   your Q&A threads probed, now a first-class lesson with the trace-fix skill as the
   procedure. (Typed `justification` is roadmap; mention but do not teach as live.)

**Gate II.**

### Increment 3 — The 0→100% spine and the roadmap

- **Lesson 000 "From zero to operator"**: a sequenced tour that makes the course a single
  arc: what the framework does (coherence brand, one loop, the deterministic split) →
  where each numbered lesson sits → how to run the first loop on a real project → where
  the course map lives. Serves as the entry point a newcomer opens first. Numbering after
  Increment 2 runs: 004 progressive-assurance (roadmap), 005 staleness, 006 doctor loop,
  007 evidence+recovery, 008 navigator read-backs, 009 coverage run flow, 010
  goals+simulation, 011 agent mechanics.
- **Roadmap perspective**: fold the spec audit's current-vs-planned split into a
  newcomer-readable map (this is live today / this is the roadmap; what will not survive
  the carve: residual `factory.*` renames, coverage→membership, /factory-doctor→
  /factory-selfcheck; the progressive-assurance layer as designed-not-shipped);
  cross-link 003.
- **Course map diagram** (tff-generate_visual HTML into `assets/`, linked): the full
  lesson flow 000→011 with prerequisites.
- **Gate III**: full-course fresh-eyes audit (see §7), browser render check of every
  lesson, quiz-key contract check, broken-link scan.

## 6. Lesson content standards (applies to every edited/new lesson)

- One tight win per lesson; operator level; skip definitions already in GLOSSARY.
- Exact invocation + real output; every cited verb exists in live argparse (verify at
  gate time).
- One worked example grounded in the live repo (numbers re-verified at gate, or avoided).
- Citation to the governing spec/source file for every load-bearing claim.
- Quiz: retrieval over recognition; options equal length; no answer key in HTML; key in
  `quiz/key.json` with the 001/002 schema.
- `lesson.json` populated; summary one line.
- Diagrams: inline SVG (003 precedent) for structural diagrams when simple; committed
  `tff-generate_visual` HTML in `assets/` and linked for layout-heavy maps. Vendoring a
  mermaid runtime is deliberately avoided (no bundler in the classroom server; static
  HTML must render standalone). "Mermaid when it's enough" is served by hand-written
  simple SVG, which renders anywhere and matches the existing figures.

## 7. Review gate (the "review step before delivering the course")

Runs at the end of every increment, before anything ships to the learner. It is a
defined checklist, performed with fresh eyes (a subagent does the mechanical half; the
teacher does the pedagogical read):

1. **Verbs exist**: every verb/flag cited in lessons or the card is found in live
   argparse (grep) or run successfully (second wave: check `coherence.*` imports too).
2. **No non-verb claims**: nothing teaches a command that does not exist (the
   `factory.evidence.coverage` trap must not recur).
3. **Internal consistency**: new/edited lessons contradict neither each other nor the
   command card nor the glossary (001/002/003 cross-check; FEAT-NAV-017 root cause must be
   one story).
4. **Counts/status**: any figure cited ("65 pending", versions, dates) is re-verified at
   gate time or removed; roadmap claims carry "as of <date>".
5. **Render**: every lesson + card renders in the classroom server (headings, tables,
   quiz submit, no broken links; hard-refresh, not stale tab).
6. **Quiz contract**: schema matches 001/002; no answer key in HTML; options equal
   length.
7. **Package vocabulary**: primary invocation is `coherence.*`; `factory.*` is described
   as the shim layer, not the target; progressive-assurance items are labelled roadmap.

Gate failure blocks the increment. The gate itself is recorded in
`learning-records/` (one record per increment, per the classroom's record format).

## 8. Verification and acceptance

- After each increment: the §7 checklist passes; the learner can run every cited command
  from the lesson text; no lesson contradicts another or the card; every annotation-thread
  topic from the Q&A ('filename link', 'exempt a requirement', 'model creates the link',
  'how implemented in the coding agent') is covered by a lesson or explicitly marked
  deferred.
- End of Increment 3: a newcomer with zero factory context can follow lesson 000 → 011
  (the full spine) and end able to run a full understand → audit → close-gaps → re-gate
  loop on `cool_physical_ai_project`, naming the tool for each step and which layer is
  authoritative for which question — and able to say, for any coherence item, whether it
  is live or roadmap ("as of 2026-08-22"), including the progressive-assurance vocabulary
  (obligations, profiles, NC-* records, health vector) recognized as designed-not-shipped.

## 9. Risks and open items

- **Live numbers/surface move during the update** (the branch currently under review is
  itself the day's progressive-assurance amendment; increments 4-8 and 2B/2C/3B/6B are
  unbuilt but may land at any moment). Mitigation: avoid hard counts; label roadmap
  claims; the gate re-verifies at each delivery; treat "current vs roadmap" as a dated
  snapshot, never a promise.
- **Parallel sessions and branches**: the design previously lived on
  `fix/kb-0004-run-recovery` (3250f7e); the working tree is on
  `docs/coherence-progressive-assurance-design`, which holds uncommitted increment-4..8
  plan amendments and the new spec. Do NOT `git add -A` there; stage only this design
  file. The course asset directory (`~/.pi/agent/classrooms/…`) is outside the repo and
  unaffected by branch moves.
- **The 002 "doesn't render" report was not reproduced** (files byte-clean; the 404 was a
  stale tab). Monitor at every gate's render step; treat any recurrence as a runtime
  defect to chase, not a lesson fix.
- **Quiz keys are never served**; the 003 key-schema fix is hygiene, not a render fix —
  do not use "key missing" as evidence of a broken page.

## 10. Decisions already taken (with the learner)

- Sequencing: strict 1 → 2 → 3, each gated (learner: "yess sounds good").
- Increment 2 carries the full set of eight workflow lessons — the seven untaught
  workflows plus a dedicated progressive-assurance (roadmap) lesson, added at the
  learner's request after the second-wave amendment.
- Design doc homes here (repo `docs/superpowers/specs/`), amended for the second-wave
  drift; course content lands in the classroom directory; the implementation plan will
  follow under `docs/superpowers/plans/` per the superpowers flow.
- The subagent audit is expected to be re-run or spot-verified at Increment 1 gate time
  because the surface changed after it (second wave).