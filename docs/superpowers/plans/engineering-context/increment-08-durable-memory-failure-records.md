# Increment 8 — Durable Memory & Failure Records (Implementation Plan)

**Status:** Draft for written review. Assumes locked D1–D9.
**Source phase:** brief §5.6 (Durable project memory) + spec §29 derived v-cycle health.
**Landing repo:** pi-agent-factory (failure-record + memory tier) + cool_physical_ai_project
(failure records for the reference slice).
**Sub-agents:** dev=`pi -p prompts/increment-08-dev.md`, review=`pi -p prompts/increment-08-review.md`.

## Goal

Make engineering **memory durable and queryable** without reinventing v1: a compact
**failure record** (repro → root cause → rejected hypotheses → fix → permanent regression)
and a **durable-memory surface** that turns decisions, evidence, root causes, and rejected
hypotheses into canonical, provenance-carrying artifacts a clean session can recover from —
never a transcript archive, never chat residue (brief §5.6).

## Ruling (brief §5.6 — "durable memory", NOT an archive)

- **In scope (canonical):** failure records, accepted/superseded/disputed decision notes with
  rationale, requirement/metric version history, open goals, rejected root-cause hypotheses
  (`kb/` already exists for recurring mistakes — reuse it), and the provenance links that make
  a clean session recover current truth.
- **Out of scope (never canonical):** unverified agent interpretations without source links,
  every intermediate thought / failed prompt, duplicated prose that competes with the
  requirement/ADR/code/evidence it describes, derived status that can't be rebuilt, and
  secrets/credentials. Derived status stays rebuildable from canonical artifacts.
- **Conflict rule (brief §5.6 #4):** if retrieved memory conflicts with code or evidence, the
  cockpit **shows the conflict** rather than silently choosing.

## Reuse (do not rebuild)

- **Recurring-mistake memory:** `factory.kb` / `kb/*.md` (v1) — a failure record that reflects a
  mistake we have made before updates/supplements `kb/`, it does not fork it.
- **Decisions:** SCC SP-A `adr:` kind — a durable decision lives in an ADR; Inc 8 only curates
  rejected-hypothesis notes and conflict surfacing around them.
- **Evidence/provenance:** `factory.evidence.manifests` + `factory.freshness` — a failure record
  links to the exact run/evidence, never a prose re-statement.
- **Derived status / freshness:** `factory.system` claim model — memory surfaces render through
  the same claim/freshness plumbing (Inc 6/7 views).
- **Comprehension (D8):** `grill-understanding`/`visual-explainer` decide whether a developer's
  divergence is misunderstanding (tutor) or design intent (→ `/plan`); any resulting durable note
  lands here as an ADR/decision, not a chat transcript.

## Global constraints (Program §6 + D3 + D8)

- Additive; existing CLI verbs/commands/schemas untouched. New `factory.memory` package +
  `memory`/`failure` subcommands only.
- Failure records are **recorded, never inferred**; every root cause cites evidence or an ADR.
- Deterministic: records carry stable ids, recorded timestamps, and provenance refs; ordering by
  recorded id/ts, never by mtime (same discipline as runs).
- Memory never becomes a second source of truth: it **links** canonical artifacts and shows
  conflicts; it does not re-state them.
- Rejected hypotheses stay small and linked; they are not a diary.

## File structure (additive)

| File | Responsibility |
|---|---|
| `src/factory/memory/__init__.py` `cli.py` | `factory memory` / `factory failure` subcommands. |
| `src/factory/memory/failure_record.py` | FailureRecord loader/store (`docs/failures/FR-*.md`). |
| `src/factory/memory/durable.py` | Durable-memory projection: decisions, hypotheses, open goals, conflicts. |
| `src/factory/memory/conflict.py` | compare a memory note against code/evidence; surface conflicts. |
| `src/factory/schemas/failure.schema.json` | Failure-record frontmatter contract. |
| `src/factory/system/queries.py` (extend additive) | `query_failure`, `query_memory`, `query_conflicts`. |
| `src/factory/system/health.py` (extend) | surface orphans (failure w/o run, hypothesis w/o outcome). |
| `pi-ext/factory-watch/...` | additive "Memory" view/tab surface (Inc 6 pattern), optional. |
| `tests/unit/memory/test_failure_record.py` `test_durable.py` `test_conflict.py` | tests. |

## Task 1: Failure record

**Interfaces:**
```python
@dataclass(frozen=True) class FailureRecord:
    id: str; title: str; path: Path
    reproduced_by: str|None       # run id / reproduction task ref
    root_cause: str;              # cites evidence or ADR
    rejected_hypotheses: list[dict]  # [{hypothesis, why_rejected, evidence}]
    fix: str; regression_link: str|None
    linked_req: list[str]; linked_feature: list[str]; scope_errors: list[str]
def load_failure(path) -> FailureRecord
def load_failures(root) -> dict[str, FailureRecord]
```
- [ ] **Step 1: Failing tests** — write→read round-trip of `docs/failures/FR-*.md`; a malformed
  record degrades to `scope_errors` (never crashes the set); a record whose `reproduced_by` run is
  missing is flagged (orphan) via `health`.
- [ ] **Step 2: Implement** mirroring `adr.py`/`load_adrs`; add `failure.schema.json`
  (id `^FR-[A-Z0-9-]+$`, required `root_cause`/`fix`; `rejected_hypotheses` optional, bounded length).
- [ ] **Step 3:** full suite + lint + commit.

## Task 2: Durable-memory projection

- [x] **Step 1: Failing tests** — `query_memory(root, scope)` returns, in one read: decisions
  (from `adr:`), failure records, rejected hypotheses, open goals, and conflicts — all with
  provenance citations; it never re-states requirement/ADR/evidence prose it links.
- [x] **Step 2: Implement** `durable.py` composing existing loaders (`adr:`, failure records,
  goals, evidence manifests); render through the claim/freshness plumbing.
- [x] **Step 3:** full suite + lint + commit.

## Task 3: Conflict surfacing

- [ ] **Step 1: Failing tests** — a memory note whose root cause contradicts current evidence/code
  fingerprints (reused `factory.freshness`) is surfaced as a `conflict` (both sides shown), never
  silently resolved; a note that agrees with evidence is not flagged.
- [ ] **Step 2: Implement** `conflict.py`: compare a record's cited evidence/commit against current
  state and, on mismatch, emit the pair (brief §5.6 "shows the conflict rather than choosing").
- [ ] **Step 3:** full suite + lint + commit.

## Task 4: `memory`/`failure` CLI + health orphans + optional Memory view

- [ ] **Step 1:** `factory memory show/conflicts` and `factory failure add/list/show` subcommands
  (additive). Extend `vcycle_health` (Inc 7) with `failure without run` / `rejected hypothesis
  without outcome` / `memory conflict` findings.
- [ ] **Step 2:** optional additive "Memory" tab/view in `system-page.ts` (Inc 6 pattern) if it
  measures useful; otherwise expose via `eng_get_memory`-style query only. (D2: SCC browser sole
  human surface; no new surface outside it.)
- [ ] **Step 3:** full suite + lint + commit.

## Task 5: Seed the reference slice + review handoff

- [ ] **Step 1:** in cool_physical_ai_project, author one real failure record for the reference
  feature (e.g. the false-reacquisition regression seen in Inc 2/3 demo), linking the failing run
  + the ADR decision + a `kb/` entry, and a rejected-hypothesis note (brief §5.6).
- [ ] **Step 2:** reviewer sub-agent — compliance vs brief §5.6 (durable ≠ archive; conflict shows
  not chooses), D3 additive, and "no second source of truth". Fix findings as `T-###`.
- [ ] **Step 3:** update checkboxes; note escalations.

## Freshness/history integration

Increment 8 consumes the provenance and reconciliation model established by HLR-09 / Inc 7.

Durable memory must distinguish:

```text
current engineering truth
from
historical engineering truth
```

Examples:

- a validation run may be historically valid for commit A while stale for HEAD;
- an explainer may accurately describe the implementation at commit B while superseded by its current
  regenerated version;
- an ADR may be superseded but remain essential rationale history;
- a rejected hypothesis remains valuable even though it is not current belief;
- a regression record remains immutable after the system recovers.

Memory SHOULD record meaningful freshness transitions where they carry engineering value:

```text
artifact X invalidated because dependency Y changed
artifact X regenerated as X'
validation E ceased proving SR-017 at commit C
goal G regressed and later recovered
```

The durable-memory layer SHALL NOT make stale artifacts current merely because they are retrievable.

Historical retrieval must surface temporal/provenance context.

---

## Acceptance for Increment 8

- Failure records persist with reproducible, evidence-cited root causes, rejected hypotheses, and
  regression links; orphans surface in health.
- `query_memory` recovers decisions/failures/conflicts for a feature in one read with provenance;
  it never re-states linked canonical prose.
- Memory conflicts are shown (both sides), never silently resolved.
- v1 suite green; additive only; no transcript archive, no secrets, no second knowledge base.
