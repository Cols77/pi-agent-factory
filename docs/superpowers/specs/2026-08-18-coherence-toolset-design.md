# Coherence: a named tool set for continuous system understanding

**Status:** design
**Date:** 2026-08-18
**Supersedes:** nothing. Absorbs the twelve improvement notes recorded in
`.tmp/traceability-task-notes.md` (TN-01…TN-12) and adds three that the layering exposed:
TN-13 (one code map), TN-14 (KB error signatures reach retrieval), TN-15 (KB scope by
symbol).

## 1. Problem

The factory has six tools that answer six different questions about a requirement, and
they work. What is missing is a *set*: a name, one entry point, one vocabulary, and one
place where findings land.

Concretely, today:

- Knowing where a project stands takes four commands (`trace status`,
  `requirements status`, `run-state current`, and finding the newest `coverage-reviews/`
  directory by mtime). Nothing aggregates them.
- Two words mean three things each. `coverage` is requirement coverage
  (`factory.coverage`), bundle membership (`factory.system coverage`) and deliverable
  gathering (`factory.evidence.coverage`). `doctor` is the requirements doctor
  (`factory.doctor`), bootstrap diagnostics (`/factory-doctor`) and run recovery
  (`run-state doctor`). An operator who guesses wrong lands in the wrong subsystem.
- Findings scatter into four places nobody sweeps: audit proposals under
  `coverage-reviews/`, session-review suggestions appended to summaries, `kb/` entries,
  and `trace_deferred` reasons buried in requirement frontmatter.
- Human gates are four different experiences. The coverage gate times out after 300s and
  finalises without the human's decisions; the factory review gate blocks on a file; the
  doctor confirms per item; `/trace-fix` asks per gap.
- Two parsers do one job: `factory.coverage.imports` hand-rolls a Python-only stdlib-`ast`
  import walker, while `factory.codeindex` already parses with tree-sitter and maintains a
  freshness fingerprint.
- Shared knowledge is filed under execution. `factory.kb` holds the failure knowledge base,
  and its retrieval already implements error-signature matching — but the only caller,
  `orchestrator/runner.py`, passes an empty signature list, so entries are selected by file
  glob alone. Nothing on the assurance side reads the KB at all, though audits produce
  exactly the failure records it exists to accumulate.
- Nothing covers specs, courses, or the test→requirement edge. A plan finds its spec by a
  regex over a literal path; course notes carry a `traceability:` block that nothing
  validates; tests reach requirements only through a binding's `experiment` field.

The measured consequence, in the two live repos: `pi-agent-factory` has 47 pending trace
gaps and no requirements register at all; `cool_physical_ai_project` has 181 SRs of which
134 are unbound, 5 have no satisfier, and exactly one feature has ever been audited — a
run that found its own blocker (empty `changed_files` in evidence manifests, `kb-0006`).

## 2. Goals

1. One brand — **Coherence** — covering the assurance half of the factory, with one CLI
   namespace, one skill namespace, and one entry command.
2. One-way layering with no import cycles, so the boundary is real rather than nominal.
3. `/using-coherence`: a single command a user invokes without knowing the tool set,
   which lands them in the right skill, command and UI.
4. Two protocols instead of six lookalikes: one human gate, one findings inbox.
5. All fifteen improvement notes land inside this structure rather than beside it.

### Non-goals

- No change to the orchestrator's pipeline semantics, gate vocabulary
  (`unit`/`sim`/`integration`/`full`), or human-review flow beyond adopting the shared
  gate protocol.
- No LLM narration in the navigator. That non-goal is inherited and stands.
- No instrumented code coverage. "Coverage" continues to mean requirement coverage.
- No auto-authored requirements. An auditor may propose; only the doctor writes.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Brand the assurance tool set **Coherence** | Literal, no metaphor to learn; the tool set exists to keep artifacts coherent. |
| D2 | Move packages rather than alias them | A facade would leave one concept with two vocabularies permanently. |
| D3 | Three layers: `factory` → `coherence` → `substrate` | The only cycle-free shape the current import graph admits (§4). |
| D4 | `/using-coherence` = deterministic probe + one enum-constrained model call | Matches the factory's own rule: code enumerates, holds state and launches; the model makes exactly one judgement. |
| D5 | Gates and findings get shared protocols, not per-tool implementations | Four gate experiences is the largest single source of operator surprise. |
| D6 | The inbox is computed from disk on every read | Same principle as the gates: no state that can drift from the artifacts. |
| D7 | Sequence: two fixes, incremental carve, then the rest | The drone repo's gate config calls into this code and its pipeline is already interrupted; main must never be red for more than a day. |
| D8 | A capability needed by both layers lives in `substrate`, not in whichever layer needed it first | The code map and the knowledge base are both consumed from either point of view — task execution and requirement assurance. Filing them under execution is what produced a duplicate import walker and a KB the audit cannot read. |
| D9 | Gate *execution* stays with the orchestrator; `substrate.config` keeps only the declarations | Running a gate is execution: it shells out, streams, and belongs to a run. Assurance reads the outcome. Moving the runner would drag process management across the seam for no caller's benefit. |
| D10 | Courses are Markdown in `docs/course/`; a classroom is an export target, never a second source | Markdown is cheap to author, diffs cleanly, lives in the repo and is therefore traceable. `[[wikilinks]]` give a knowledge graph over notes, requirements and specs at no cost. Hand-maintained HTML outside any repo cannot be checked by anything. |

## 4. Layering

Dependencies run one way: **`factory` (execution) → `coherence` (assurance) →
`substrate` (shared models)**.

### 4.1 Evidence for the seam

Measured from the current tree:

- The five packages to move need exactly two things from execution: the **task ledger**
  (`Task`, `load_tasks`, `parse_plan_tasks` — used by `requirements/cli.py` and five
  `system` modules) and the **agent-dispatch trio** (`PiAgentBackend`, `AgentRole`,
  `load_skill_block` — used only by `coverage/runner.py`). Neither is execution logic.
- `validation`, `presentation` and `goals` import the movers. All three are assurance-side,
  so moving them in converts those cross-package edges into internal ones.
- What remains pointing from execution into assurance — `evidence/finalize.py`,
  `preflight/checks.py`, `orchestrator/*` — is the legal direction.
- `trace ↔ system` is a genuine cycle today (`trace/graph.py` imports `system.adr`). Both
  move together, so it becomes internal.

### 4.2 Package map

**`substrate/`** — shared, depends on nothing in the other two.

| Module | Contents | Moved from |
|---|---|---|
| `substrate.paths` | repo/skill/extension path resolution | `factory.paths` |
| `substrate.config` | `.factory/factory.yaml` loading, gate declarations | `factory.config` |
| `substrate.schemas` | JSON schemas | `factory.schemas` |
| `substrate.ledger` | task and plan parsing: `Task`, `load_tasks`, `set_status`, `parse_plan_tasks` | `factory.orchestrator.ledger` |
| `substrate.agents` | `PiAgentBackend`, `Scope`, `load_skill_block`; role *catalogues* stay with their owners | `factory.orchestrator.{pi_backend,skills,types}` |
| `substrate.validators` | `schema_validator`, `manifest_validator`, `session_validator`, `kb_validator` | `factory.validation` (document half) |
| `substrate.evidence` | manifest **read** model: `list_run_manifests`, manifest parsing | `factory.evidence.manifests` |
| `substrate.freshness` | severity model, `GATE_FAILING_SEVERITIES` | `factory.freshness` |
| `substrate.codemap` | code index (signatures) **plus a new import-edge layer** | `factory.codeindex` + `factory.coverage.imports` |
| `substrate.kb` | failure knowledge base: entry model, index, retrieval | `factory.kb` |

**`coherence/`** — depends on `substrate` only.

| Module | Was | Notes |
|---|---|---|
| `coherence.trace` | `factory.trace` | gains `unlink` (TN-03) |
| `coherence.register` | `factory.requirements` | the register and its closure model |
| `coherence.doctor` | `factory.doctor` | prose → falsifiable requirements |
| `coherence.audit` | `factory.coverage` | requirement coverage; drops its private import walker |
| `coherence.navigate` | `factory.system` | `coverage` verb renamed `membership` (TN-08) |
| `coherence.measurement` | `factory.validation` (harness half) | `harness`, `sim_harness`, `playwright_harness`, `pipeline`, `report`, `scorer_registry`, `assertions` |
| `coherence.simulation` | `factory.simulation` | read only by `navigate` and `presentation` today |
| `coherence.presentation` | `factory.presentation` | |
| `coherence.goals` | `factory.goals` | |
| `coherence.status` | new | §6 |
| `coherence.focus` | new | §6 |
| `coherence.gate` | new | §7 |
| `coherence.inbox` | new | §8 |

**`factory/`** — execution; may depend on both.

`orchestrator` (minus the ledger and agent substrate), `polish`, `preflight`,
`evidence.finalize` (the write side), `commands`. Simulation harnesses are invoked through
`coherence.measurement`; failure knowledge is read and written through `substrate.kb`. Gate
**execution** stays here (D9): `substrate.config` holds the declarations, the orchestrator
runs them, and `coherence` reads the outcomes.

### 4.3 Compatibility

Every moved module keeps a shim at its old path for one release: a re-export plus a
`DeprecationWarning` naming the new path. `.factory/factory.yaml` in consumer repos —
including `cool_physical_ai_project`, whose `full` gate calls
`python -m factory.system coverage --gate` — keeps working untouched until the consumer
chooses to migrate. Shim removal is a separate, announced change, not part of this design.

## 5. CLI surface

One console entry with subcommand groups. Each group keeps its existing argparse parser;
the entry is a dispatcher, not a rewrite.

```
coherence status                       # §6, the union of every gate
coherence focus <scope-ref>            # §6, session-sticky working set
coherence inbox [triage]               # §8
coherence explain <term|id>            # existing vocabulary data, made reachable

coherence trace     status|graph|next|link|unlink|exempt|defer|check
coherence register  new|index|status|show|bind|defer|check|next
coherence doctor    context|mint|promote|task
coherence audit     list-features|run|audit|verdict|consolidate|gate|report|failure
coherence navigate  scope|brief|matrix|timeline|story|reverse|vcycle|guide|
                    membership|bundle|goal|sim|diagram|present
```

`python -m coherence.<group> <verb>` remains valid for scripting and for gate declarations.

**The `doctor` collision is resolved by renaming, not by absorbing** (TN-08). `coherence
doctor` is the requirements doctor and keeps the word. Bootstrap diagnostics become
`/factory-selfcheck`, and run recovery keeps its own namespace as `run-state doctor`.
`/factory-doctor` aliases `/factory-selfcheck` for one release with a deprecation line. It
does not fold into `coherence status`: it diagnoses the factory's own installation, which is
a different question from whether a project's artifacts cohere.

**Universal scope refs.** The navigator already parses nine kinds (`sr: task: feat: file:
adr: diag: metric: goal: bundle:`). Every command in the set accepts them, every output
prints them, and they are copyable in the TUI and clickable in the browser. This replaces
today's habit of hand-retyping feature ids and run ids across four tools.

## 6. `/using-coherence`, status and focus

### 6.1 The dispatcher

`.pi/skills/using-coherence/SKILL.md` carries the routing table — the map the model reads
when it needs to reason, mirroring `superpowers:using-superpowers`. The command itself is
deterministic:

**No argument.** Run the read-only probes concurrently (`trace check`,
`register check`, `run-state current`, newest audit age, `membership --gate`), rank by a
fixed precedence — interrupted run > failing gate > stale audit > proposed backlog >
nothing pending — and render a menu. Selecting an entry launches the owning surface
(a skill session, a CLI verb, mission control, or the browser).

**With an argument.** Exactly one model call, constrained to an intent enum —
`UNDERSTAND · VERIFY_CLAIM · CLOSE_GAPS · AUTHOR_REQUIREMENTS · BUILD · RECOVER ·
TRIAGE · TEACH` — plus an optional scope ref extracted from the text. Code launches from
there. The classification is always printed with an escape hatch ("not that? pick from the
menu"), so a misclassification costs one keystroke and never a wrong write.

### 6.2 `coherence status`

One screen, one exit code, the union of the gates, each line naming the command that
produced it and the command that resolves it. Mirrored as a persistent line in the `pif`
TUI beside the existing factory widget:

```
coherence · 47 gaps · 134 proposed · audit 16d · run INTERRUPTED
```

### 6.3 `coherence focus`

`coherence focus feat:FEAT-NAV-017` writes a session-scoped default that `/trace-fix`,
`/coverage-review`, `/system` and the audit verbs inherit. Cleared with
`coherence focus --none`. Stored beside the existing session context, not in the repo.

## 7. Gate protocol

One implementation, `coherence.gate`, adopted by every human gate in the system.

- **Decision file.** `{gate_id, artifact_ref, decisions: [{item_id, decision:
  accept|reject|defer, reason?, review_after?}], decided_at, decided_by}`, written
  atomically beside the run it belongs to.
- **Never proceeds silently.** A gate with no decision blocks, or exits non-zero when
  running unattended (`--no-gates` remains the explicit opt-out). This retires the coverage
  gate's 300s timeout, which today produces a report that reads as human-reviewed and is
  not (TN-02).
- **Resumable.** An existing valid decision file short-circuits re-prompting, exactly as
  per-SR verdict files already do.
- **`reject` and `defer` require a reason**, and `defer` accepts `review_after`. §8 uses it.
- **One renderer** in `pi-ext`, so accept/reject/defer looks and behaves identically
  whether it came from an audit, the doctor, a review, or a trace gap.

## 8. Inbox

`coherence.inbox` computes a single triage queue from disk on every read — no new state
store. Sources:

| Source | Item kind |
|---|---|
| `coverage-reviews/*/report.json` | proposed requirement, workflow issue |
| session summaries | session-review suggestion |
| `kb/` | candidate entry awaiting confirmation |
| requirement frontmatter | deferral whose `review_after` has passed |
| register closure | binding whose checksum went stale |

Item schema: `{id, source, kind, ref, summary, evidence, resolve_cmd, review_after?}`.
Decisions are written back into the owning artifact through that artifact's own writer —
the doctor for a proposal, `trace defer` for a gap, the register for a binding — never by
the inbox itself. The inbox routes; it does not author.

**Expiring deferrals** are the mechanism that keeps this from rotting: a deferral is a
promise with a due date, and it returns to the inbox when due rather than sitting in
frontmatter forever.

## 9. Shared utilities: code map and knowledge base

Two capabilities are needed identically by execution and by assurance, and are currently
filed under whichever layer happened to need them first. Both move to `substrate`, and
they compose.

### 9.1 Code map (TN-13)

`substrate.codemap` merges two half-solutions:

- `factory.codeindex` parses with tree-sitter (stdlib `ast` as fallback), maintains a
  fingerprint, and stores signatures — but no import edges, and only the orchestrator's
  context packet consumes it.
- `factory.coverage.imports` walks Python imports with stdlib `ast` to compute the audit's
  overlap check — a second parser, Python-only, with no freshness model.

The merged module keeps the index's engine and fingerprint and adds an import-edge layer;
`coherence.audit` computes overlap from it. Two consequences beyond deduplication: the
audit gains whatever languages the index parses, and a missing or renamed binding test
becomes a distinct finding instead of being indistinguishable from "this test genuinely
touches nothing" — the failure mode `compute_overlap` has today.

### 9.2 Knowledge base (TN-14, TN-15)

`substrate.kb` holds the entry model, index and retrieval. It is a knowledge store, not an
execution detail: the orchestrator reads it to brief a dev agent and writes to it from
session review, while the assurance side both produces the failure records it exists to
accumulate (audit `tool_failures`, workflow issues) and consumes it as a source in the
inbox (§8).

Two defects surface once it is shared:

- **TN-14 — signatures are matched but never supplied.** `select_entries` implements
  `sig_hit` against an entry's `scope.error_signatures`; its only caller passes an empty
  list, so selection is file-glob-only in practice. The fix is a caller change plus a
  signature source: gate output and node failure snippets already contain the strings.
- **TN-15 — scope by symbol, not by glob.** With import edges available (§9.1), an entry's
  scope can name a symbol or module and fire when the changed files actually *reach* it,
  instead of matching a path pattern. This subsumes the common case where a KB entry is
  about a function that has since moved file. Optional, in the tail; TN-14 stands alone.

## 10. Artifact families currently uncovered

These are the holes the tool set does not reach, addressed in the last increment.

- **Specs** (TN-05) gain `id`/`title`/`status` frontmatter and a `spec:` node kind, so
  `plan_no_spec` stops depending on a regex over a literal path and a spec becomes
  answerable to "do requirements cover this".
- **Courses** (TN-04, TN-12) stay Markdown under `docs/course/` (D10). A coherence check
  resolves every id a note declares — both the `traceability:` frontmatter block and any
  `[[wikilink]]` in the body — against the trace graph, failing on an unknown id, and emits
  the drift snapshot as command output rather than a hand-edited file beside the notes.
  Because links are bidirectional by convention, the check also reports requirements and
  specs that no course note reaches, which is the graph view the notes exist to give. A
  pi-teach classroom, if wanted, is *generated* from these notes; it is never authored
  separately.
- **Tests** (TN-07) gain `@pytest.mark.sr("SR-032")`, collected into the register, with a
  gate that fails when a bound SR's `experiment` names a file carrying no matching marker.
- **Business requirements** remain referenced (`upstream: [BR-002]`) and unmodelled. TN-03's
  `unlink` makes the dangles removable; a `BR-*` tier is explicitly out of scope here.

## 11. Increments

| # | Contents | Gate |
|---|---|---|
| 0 | TN-01 evidence manifests record `changed_files`; TN-11 bootstrap this repo's own register | an audit of a real feature returns non-empty overlap; `trace check` runs against a non-empty register |
| 1 | `substrate` extraction (paths, config, schemas, ledger, agents, validators, evidence read model, freshness, codemap, kb) + shims; TN-14 signatures reach retrieval | full gate green; no module in `substrate` imports `factory` or `coherence`; a KB entry with an error signature is selected by a failing gate's output |
| 2 | `coherence.trace` + `coherence.register`; `coherence` console entry; TN-03 `unlink` | `coherence trace check` and `coherence register check` behave identically to their predecessors |
| 3 | `coherence.navigate` + `presentation` + `goals` + `simulation`; TN-06 bundle authoring; TN-10 remediation as tools; `membership` rename | navigator serves every route; `membership --gate` matches old `coverage --gate` |
| 4 | `coherence.audit` + `coherence.measurement`; TN-09 parallel per-SR audits; TN-13 codemap overlap; remaining TN-08 renames | a multi-SR feature audits concurrently with identical verdicts |
| 5 | `coherence status`, `focus`, `explain`; TUI widget; `/using-coherence` + skill; `/factory-doctor` → `/factory-selfcheck` | dispatcher routes all eight intents; menu ranks correctly against seeded states; the old command name still runs and warns |
| 6 | Gate protocol (absorbs TN-02) + inbox + expiring deferrals | no gate can finalise without a decision; every finding source appears in the inbox |
| 7 | Unified long-run surface for factory runs, audits and measurement | one status protocol, one mission control, completion notification |
| 8 | Artifact families: TN-05, TN-04, TN-07, TN-12; TN-15 KB scope by symbol | course check fails on an unknown id in frontmatter *or* in a `[[wikilink]]`; a bound SR with an unmarked test fails the gate; a KB entry scoped to a moved symbol still fires |

Increments 6–8 are cuttable without stranding earlier work.

## 12. Testing

Each move increment is a refactor with a behavioural invariant: the existing unit suites
for `trace`, `requirements`, `doctor`, `coverage` and `system` must pass unchanged except
for import paths, and a shim test asserts the old path still imports and warns. New
behaviour — `status`, `focus`, the dispatcher, the gate protocol, the inbox, the codemap
overlap — is test-driven, with the dispatcher tested against seeded repository states
rather than a live model: the intent enum is the seam, and the launcher is tested per
intent.

## 13. Risks

- **Consumer breakage.** `cool_physical_ai_project` declares `factory.system coverage
  --gate` in its `full` gate. Shims cover it; the migration of that file is a separate,
  deliberate change made after increment 3 lands.
- **Long refactor on a repo whose pipeline is interrupted.** Mitigated by increment 0
  landing first and by one package per increment.
- **The dispatcher becomes a place to hide bad routing.** Mitigated by printing the
  classification, by the menu escape hatch, and by keeping intents an enum small enough to
  enumerate in tests.
- **The inbox becomes a second source of truth.** Mitigated by D6: computed on read,
  decisions written through the owning artifact's writer.

## 14. Resolved in review

The three items left open when this design was first drafted are now decided and folded into
the sections above:

- **Gate runner** — stays with the orchestrator (D9, §4.2). `coherence.measurement` owns
  harnesses and reports, not process execution.
- **`doctor` collision** — resolved by renaming rather than absorbing: `/factory-selfcheck`,
  with `/factory-doctor` aliased for one release (§5, increment 5).
- **Courses** — Markdown in `docs/course/`, checked against the trace graph including
  `[[wikilinks]]`; classrooms are a generated export (D10, §10, increment 8).

No open items remain.
