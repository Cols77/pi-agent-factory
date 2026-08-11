# Increment 7 — Context Delta + Goal-aware Validation Status (Implementation Plan)

**Status:** Draft for written review. Assumes locked D1–D6 (SCC browser sole human surface; no Obsidian).
**Source phase:** Engineering Context spec §37 **Phase 7 — Context Delta** and spec §28–§31.
**Landing repo:** pi-agent-factory (+ optional index) + cool_physical_ai_project (checkpoints).
**Sub-agents:** dev=`pi -p prompts/increment-07-dev.md`, review=`pi -p prompts/increment-07-review.md`.

## Goal

Close the human mental-model gap the spec leads with (§1, §31): **`/catchup <feature>`**
reports "what changed since I last reviewed this," backed by developer checkpoints, plus the
**goal-aware requirement status** (`VALIDATED / VERIFICATION_STALE / REGRESSED`, spec §28–§30)
and a change-impact probe for stale-evidence detection (spec §29–§30).

## Reuse (do not rebuild)

- **Freshness/stale detection:** `factory.freshness` + `factory.evidence.reconcile` already
  fingerprint code and flag stale evidence — this is the change-impact engine's core.
- **Goal-aware status:** Inc 2 Task 7 derived `requirement_validation`.
- **Change history / commits:** `factory.system.feature.recent_changes` (Inc 1) + `git_ops`.
- **Run/sim evidence:** Inc 3.
- **Human views:** Inc 6 views; `/catchup` output is a rendered **"Catch me up"** view in the
  SCC browser (a new additive tab/view), presented at REVIEW.

## Global constraints (Program §6 + D3)

- Additive; existing verbs untouched. `/catchup` and a `catchup` subcommand are new.
- Developer checkpoints are recorded, never inferred (spec §31 `developer_checkpoint.commit`).
- "Changed since" is computed from recorded checkpoints + git history + goals/history — never from
  an LLM summarizing the past. The delta is deterministic.
- Introduce a derived index NOW only if `query_goal_history`/`recent_changes` prove slow on the
  real repo; otherwise keep on-demand (spec §33 SQLite optional). If built, it must be rebuildable
  from canonical artifacts (AC-10).

## File structure (additive)

| File | Responsibility |
|---|---|
| `src/factory/commands/catchup.py` | `/catchup` handler + `factory catchup` CLI. |
| `src/factory/delta/__init__.py` `compute.py` `checkpoint.py` | delta computation + checkpoint store read/write. |
| `pi-ext/factory-watch/src/system-catchup-view.ts` | **"Catch me up"** view in `/system` (additive tab). |
| `pi-ext/factory-watch/test/system-catchup-view.test.ts` | render tests. |
| `src/factory/trace/validation_status.py` (extend additive) | `VALIDATED/VERIFICATION_STALE/REGRESSED` derivation. |
| `src/factory/system/queries.py` (extend additive) | `query_catchup`. |
| `src/factory/system/cli.py` (extend additive) | `catchup` subcommand; optional `index` build. |
| `tests/unit/delta/test_compute.py` `test_checkpoint.py` `tests/unit/commands/test_catchup.py` | tests. |

## Task 1: Developer checkpoints

**Interfaces:**
```python
@dataclass(frozen=True) class Checkpoint: feature: str; commit: str; reviewed_at: str
def save_checkpoint(pi_dir: Path, cp: Checkpoint) -> None
def load_checkpoint(pi_dir: Path, feature: str) -> Checkpoint | None   # missing = no review yet
```
- [ ] **Step 1: Failing tests** — write→read round-trip (`.pi/checkpoints.json`); missing feature
  returns `None` (legitimate, not an error); malformed file degrades rather than crashes.
- [ ] **Step 2: Implement** minimal JSON store under `.pi/` (canonical-only, not evidence).
- [ ] **Step 3:** full suite + lint + commit.

## Task 2: Delta computation

**Interfaces:**
```python
@dataclass(frozen=True) class ContextDelta:
    feature: str; since_commit: str
    prs_merged: list[str]; requirements_changed: list[str]
    adrs_added: list[str]; scenarios_added: list[str]
    goals_reached: list[str]; goals_regressed: list[str]
    metric_changes: list[dict]      # [{metric, from, to, regression?}]
    new_open_items: list[str]
def compute_delta(root, feature, since_commit) -> ContextDelta
```
- [ ] **Step 1: Failing tests** — from a seeded git history + goals/history + sim runs, produce the
  spec §31 / §9.4 delta (`2 PRs merged, goal reached, metric 87%→95%, new concern false-reacquisition↑`).
  Assert metric regression is flagged.
- [ ] **Step 2: Implement** — compose:
```python
def compute_delta(root, feature, since_commit):
    return ContextDelta(
      prs_merged=git_ops.prs_since(root, since_commit, paths=feature_files),
      requirements_changed=git_diff_requirements(root, since_commit),
      adrs_added=[a for a in load_adrs(root) if authored_after(a, since_commit)],
      scenarios_added=simulation.new_scenarios_since(root, since_commit),
      goals_reached=goals_transitioned(root, "REACHED", since_commit),
      goals_regressed=goals_transitioned(root, "REGRESSED", since_commit),
      metric_changes=metric_deltas(metric_history, since_commit),
      new_open_items=open_questions_since(root, since_commit),
    )
```
- [ ] **Step 3:** full suite + lint + commit.

## Task 3: `/catchup` + `query_catchup`

- [ ] **Step 1:** `/catchup FEAT-NAV-017` loads the checkpoint, computes `compute_delta`, upgrades
  the checkpoint to HEAD, and (at REVIEW) presents via Inc 5/Inc 6 surfaces. Deterministic text block
  matching spec §31 wording.
- [ ] **Step 2:** `query_catchup` exposes it in the claim/freshness plumbing for agent (Inc 4) use.
- [ ] **Step 3:** render the delta as an additive **"Catch me up"** view in the SCC browser
  (system-page.ts, on top of SP-B/Inc 6), emulating the spec §31 / §9.4 block:

```
Since your last review:
Requirements       +1 changed
Design decisions   +1
Implementation     3 PRs merged
Goals              1 reached
Regressions        1
Metrics            reacquisition_rate 82% -> 91%
```

  It renders *computed* `ContextDelta` fields only (never an LLM summary of the past), via the
  existing claim/freshness render helpers. `system-page.ts` is edited additively, after Inc 6.
- [ ] **Step 4:** TS vitest + `uv run python -m pytest -q` + lint green; commit.
- [ ] **Step 3:** full suite + lint + commit.

## Task 4: Goal-aware requirement status (additive, spec §28–§30)

- [ ] **Step 1:** extend Inc 2 `requirement_validation` to emit:
  - `VALIDATED` — all goals REACHED and code unchanged since latest evidence;
  - `VERIFICATION_STALE` — code affecting the requirement changed since latest evidence
    (reuse `freshness`/`reconcile` fingerprint);
  - `REGRESSED` — a formerly-REACHED goal is now below target;
  - `VERIFICATION_PENDING` — goals exist, none reached;
  - and keep v1 behaviour when the requirement has no goals.
- [ ] **Step 2: Failing tests** — a goal goes REACHED→REGRESSED and the requirement status follows
  (spec §29 "validated requirement whose goal regressed"); a code change after validation marks
  `VERIFICATION_STALE` (spec §30 example, `A→C`).
- [ ] **Step 3:** full v1 suite green (the new states are additive, reported through the derived
  status only); commit.

## Task 5: Derived impaction probe + v-cycle health report (spec §29)

- [ ] **Step 1: Failing tests** — detect `requirement without test`, `requirement without
  implementation`, `implementation without traceable requirement`, `goal without metric source`,
  `metric without experiment`, `simulation without commit`, stale evidence (already covered by Task 4),
  feature with failing verification.
- [ ] **Step 2: Implement** `factory.system/health.py` `vcycle_health(root) -> list[Finding]` as a
  pure query (reusing trace gaps + goals + simulation), exposed via a `health` subcommand and the Inc 6 surfaces.
- [ ] **Step 3:** full suite + lint + commit.

## Task 6: Optional rebuildable index

- [ ] **Step 1:** measure. If `query_catchup`/`query_goal_history` on the real repo exceed a
  threshold, add a SQLite index under `.pi/` built by `factory index build` from canonical artifacts;
  deleting it and rebuilding reconstructs the same graph (AC-10). If fast enough, skip (record the decision).
- [ ] **Step 2:** if built: `--rebuild` deterministic, indexed only for read queries; commit.

## Task 7: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §28–§31, §9.4, AC-10 rebuildability,
  AC-07 regression, D3 additive rule; deterministic-delta rule (no LLM over the past).
- [ ] **Step 2:** fix findings; update checkboxes.

## Acceptance for Increment 7

- `/catchup FEAT-NAV-017` returns a deterministic, correct "since your last review" delta and
  records the new checkpoint (spec §31).
- Requirement status correctly reflects accumulated `VALIDATED/VERIFICATION_STALE/REGRESSED`
  from goals + code freshness (spec §28–§30).
- `vcycle_health` surfaces the spec §29 inconsistencies through agent + human views.
- v1 suite green; additive only; index (if added) rebuildable (AC-10).
