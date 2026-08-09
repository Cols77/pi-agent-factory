# Design: System Navigator Increment B — V-Cycle Navigator

**Date:** 2026-08-09
**Status:** Draft for written review
**Author:** Colin AUBE (with AI assistance)
**Builds on:**
- `2026-08-08-system-navigator-briefing-validation-guide-design.md` (Increment B, first slice)
- `2026-08-07-factory-evidence-lifecycle-and-recovery-design.md` (Increment A)

## 1. Context

The increment plan this design serves was written on 2026-08-06 by a `gpt-5.6-sol` session in `cool_physical_ai_project`. It set out three increments:

- **A — durable evidence foundation.** Durable implementation and review records, final commit and commit range, archived review guides, validation history, lightweight decision records.
- **B — V-cycle navigator.** The 60-second feature/SR briefing; aggregate implementation tasks, code, reviews, decisions and tests; the verification matrix with freshness; **task implementation-story pages**; **reverse navigation from code and tests back to requirements**.
- **C — grounded guide.** Natural-language question bar, cited explanations, guided tours, impact investigation, "what changed" digests.

It also recorded two rules that bind this design: **"The LLM is the narrator, not the source of truth"**, and the UI must separate *recorded rationale*, *evidence*, *AI-generated synthesis*, and *missing knowledge*. And one sequencing warning: *"I would avoid starting with the chatbot. First make the evidence durable, explicit, and navigable; otherwise the chatbot will produce convincing explanations over incomplete provenance."*

What exists today is the first slice of B: briefing, validation matrix, decision timeline, and a deterministic guide, over declared bundles and SRs. What is missing is the half that makes it a *V-cycle* navigator — the descent from requirement to code, and the climb back.

**Increment A only began working on 2026-08-09.** The evidence pipeline was wired but silently destroyed by a runaway in checkpoint recording: `write_patch` wrote its untracked-files sidecar into an untracked directory, so each checkpoint embedded every earlier one (768MB → 1.8GB → 4.3GB → 10GB) until `MemoryError` killed the run before `finalize_run_evidence`. Fixed in `812c2bd`, with two further defects behind it (`f6e0ab9`, `dd32e61` in the target repo). The first evidence manifests in any repo date from that day. This is not background colour — §6 depends on it.

## 2. Approved decisions

Answered by the user on 2026-08-09 during design.

1. **`task:` becomes an openable scope.** "How was this implemented" is answered per task, so a task needs a page of its own.
2. **Reverse navigation walks recorded links only.** file → `changed_files` → manifest → `task_id` → task → `satisfies` → SR. Every hop is a recorded artifact; there is no inference step.
3. **No whole-suite test pass rate.** Manifests hold per-run validation, not suite totals. The navigator reports what is recorded and never computes a repo-wide percentage.
4. **No git-derived history, but session records are read.** Manifests are never reconstructed. Where no manifest exists, run history comes from `sessions/*.session.json` — a recorded artifact — and implementation stays `missing`. See §6 and §6.1.
5. **The claim-class model is unchanged.** The four-way separation from the 2026-08-06 plan maps onto the existing classes; B introduces no new claim vocabulary. See §3.3.

## 3. Information model

### 3.1 Scope kinds

| ref | opens | new? |
|---|---|---|
| `bundle:<id>` | feature briefing | existing |
| `sr:<id>` | requirement briefing | existing |
| `task:<id>` | implementation story | **new** |
| `file:<repo-relative-path>` | reverse navigation | **new** |

`spec:` and `plan:` remain member kinds, not openable scopes.

### 3.2 Namespace mapping — settle it, do not assume it

Trace node ids are `spec:<basename>`; `satisfies` edges point at a bare `SR-146`; navigator scope refs are `spec:<path>` and `sr:SR-146`. These namespaces have never met, so the mismatch has been parked twice. Reverse navigation makes them meet.

The implementation must define one explicit mapping function, in one place, with a test per direction. It must not be inferred at each call site, and a ref that does not map is `missing` — never fuzzy-matched.

### 3.3 The four-way separation

The 2026-08-06 plan requires the UI to separate recorded rationale, evidence, AI synthesis, and missing knowledge. The existing claim classes already carry this:

| plan's category | claim class | distinguished by |
|---|---|---|
| recorded rationale | `recorded` | citation kind `decision` / `review` |
| evidence | `recorded` / `derived` | citation kind `manifest` / `validation` / `trace` |
| AI-generated synthesis | `synthesized` | deterministic in B; model-narrated in C |
| missing knowledge | `missing` | coupled to freshness `n/a` |

No new vocabulary. Increment C changes who writes `synthesized` text, not what the class means.

## 4. Views

### 4.1 Task implementation story (`task:<id>`)

The unit of work, told from evidence:

- statement and status, from the task ledger
- **every run against it**, from `evidence/runs/*.json` filtered on `task_id` — including escalated runs, because a failed attempt is part of the story
- per run: outcome, commit range (`start_commit` → `result_commit`), `changed_files`, validation result, reviews, decisions
- the SRs it satisfies, via the trace `satisfies` edge

Runs are ordered by recorded `started_at`. Where two runs share a timestamp, ordering falls back to the manifest path — never to array position across documents, the defect fixed in the timeline query.

### 4.2 Reverse navigation (`file:<path>`)

The V-cycle's right-hand side, walked backwards:

```
file → changed_files → manifest → task_id → task → satisfies → SR
```

The result is a **citation path**: each hop names the artifact that establishes it. Any hop that does not resolve renders `missing` with its reason, and the chain stops there rather than guessing the remainder.

A file touched by several runs yields several paths; all are shown, ordered by recorded time. This is the common shape for a file amended across attempts, and collapsing it would hide rework.

### 4.3 Feature briefing gains implementation

The bundle brief lists members today. It gains, per member task: run count, latest outcome, changed-file count, and latest validation result — enough to answer "what has been built and does it pass" without opening each task.

Aggregates are `derived`, cite the manifests they came from, and degrade when any contributing manifest is unreadable.

## 5. Data sources — one owner per fact

| fact | source |
|---|---|
| task statement, status | `factory.orchestrator.ledger` |
| runs for a task | `factory.evidence.manifests.list_run_manifests`, filtered on `task_id` |
| changed files, commit range, patch | `manifest.implementation` |
| validation outcome | `manifest.validation` |
| reviews, decisions | `manifest.reviews`, `manifest.decisions` |
| task → SR | trace `satisfies` edge |
| document titles | `trace.model.load_nodes` |
| SR statement | `factory.requirements.register` |
| run history where no manifest exists | `sessions/*.session.json` (§6.1) |

No new parsers. Every source is already loaded somewhere in the navigator; B composes them, it does not re-read artifacts itself.

**Freshness** stays content-based. A `changed_files` entry whose current bytes differ from the run's `result_commit` state marks that claim `stale`. No mtime, anywhere.

## 6. What the navigator will honestly show today

Evidence manifests exist only from 2026-08-09. Every task completed before then has no recorded implementation story, and B will render it `missing`.

Git commit messages look like a fallback — `T-058: mark mission manager…`, `feat: … (T-057)` — and were rejected. The convention demonstrably lies: commit `3d1ab1b` in `cool_physical_ai_project` is titled *"T-059: Implement the Common Planner Protocol and Reactive Planner"* and contains **none** of T-059's implementation, because `commit_all` swept unrelated work in. Reading task identity out of commit prose puts it in the same category as plan checkboxes, which the parent design already bars by name (§3.4 there).

The navigator therefore gets richer as runs accumulate, and starts sparse. That is the honest state, and stating it is preferable to fabricating history.

### 6.1 Session records are a second recorded source

Manifests cannot be reconstructed for historical tasks. The schema requires `start_commit`, `result_commit` and `implementation{changed_files, patch}`, and none of those survive: of 37 session records in this repo, exactly **one** has `commits` populated, and no artifact anywhere records the changed files or patch of a pre-2026-08-09 run. Writing "manifests" for that history would mean inventing required fields — manufacturing evidence in the one store whose value is that it never does.

`sessions/*.session.json` is, however, a genuinely recorded artifact: written by the run, at run time, describing what that run did. The navigator reads it as a **second, thinner evidence source**, not as a manifest.

It supplies: `task_id`, `started_at`/`ended_at`, `outcome`, per-node results with their `extra` payloads, `dod.met`, and `git.head`. Across the 37 factory records that is 17 completed, 15 rejected and 5 escalated task-runs — the rejected and escalated ones being the history most worth having.

Rules:

- a claim sourced this way cites the **session record**, with citation kind `session`, never a manifest;
- `implementation` is `missing` for such a run, because it genuinely was never recorded — not degraded, not inferred from `git.head`;
- session-record history renders visibly thinner than manifest history. That asymmetry is permanent and correct: those runs *are* less well evidenced, and flattening the two would be the lie;
- where both a manifest and a session record exist for the same `run_id`, the manifest wins and the session record is not read.

Nothing is written, no schema changes, and no field is invented.

**Known gap:** `manifest.reviews` is empty on runs made with `--auto`, because `finalize` archives records written by the *human* review gate, which `--auto` skips. Both manifests that exist today are `--auto` runs. The review column of §4.1 is therefore unexercised against real data, and the plan must not assume its shape from the schema alone — it needs one non-`--auto` run before that column is trusted.

## 7. Failure handling

Every absence is a named claim, never an empty page.

- No `evidence/` directory → run sections render `missing`; the repo has no recorded runs.
- Task with no manifest → statement, status and SR links still render; run history is `missing`.
- Corrupt manifest → `list_run_manifests` skips it silently, so the query counts the gap and surfaces it in `degraded_reasons`, as `timeline` already does. A skipped manifest must never read as "no runs".
- File in no manifest → reverse navigation returns `missing` with its reason, not an empty result.
- `satisfies` naming a non-existent SR → `missing`; the task page degrades rather than dropping the link.
- Unmappable ref between namespaces (§3.2) → `missing`, never fuzzy-matched.

## 8. Testing

Follows the parent design's discipline, with one addition earned this session.

- Unit tests marked `unit`; integration tests marked `integration` and run with `-m 'unit or integration'`. A gate that collects nothing is a failing gate.
- **Fixtures must be built through the real writers.** `write_run_manifest` for manifests, the real register and ledger parsers for their artifacts. A hand-rolled dict that merely resembles a manifest is what let Task 3 ship a query reading a storage layout no producer writes; its tests passed because the fixtures encoded the same wrong assumption as the code.
- At least one integration test drives the real `python -m factory.system` CLI end to end.
- Assertions target rendered outcomes, not the implementation's own structure restated back.
- Reverse navigation is tested per hop and for each hop's absence.

## 9. Security

`file:<path>` is the first scope kind whose identifier is a free-form path supplied by the caller, so it is the first that can be pointed outside the repository.

- A `file:` ref resolves under the repo root or it does not resolve. `..` segments and symlinks are resolved **before** the containment check, and a ref landing outside is `missing` — never read, never cited.
- Reverse navigation reads manifests and computes hashes. It never serves file **contents**; the existing artifact route stays the only content path, and it remains digest-addressed.
- An exported guide is still not a citable source (parent design §4.5). Reverse navigation must not resolve a `file:` ref that points at one, or a synthesized artifact re-enters as evidence through the new door.
- Paths from manifests are treated as untrusted input on the way out: a `changed_files` entry is confined and escaped before rendering, exactly like any other payload string.

## 10. Non-goals

- No whole-suite or repo-wide test pass rate (§2.3).
- No git-derived implementation history (§6).
- No natural-language question bar — that is Increment C (§11).
- No editing, no write path beyond the existing guide export.
- No new claim classes.
- No browser-side interpretation: Python computes, TypeScript renders.

## 11. Deferred to Increment C

Recorded here so B's completion hands over cleanly rather than stopping dead.

Increment C is the grounded guide: a natural-language question bar, cited explanations, guided feature tours, impact and production-bug investigation flows, and "what changed since my last visit" digests.

The governing rule is already agreed: **the LLM narrates, it is never the source of truth.** It may explain and order recorded facts; every material statement carries a citation; synthesis stays visually separated from recorded rationale and evidence; gaps are stated rather than smoothed over. The `spans` field and the verbatim-containment check built in the parent design are the verifier C inherits.

C begins when B is complete — per the 2026-08-06 warning, not before.
