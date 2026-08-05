# Session Report — 2026-08-05T01-09-10Z

## Pipeline Summary

| Task | Outcome | Iterations | Key Nodes |
|------|---------|------------|-----------|
| **T-051** — Pytest Marker Update and Smoke Test | ✅ **completed** | 4 | context-gather (pass) → dev (pass) → validation (pass) → review (**changes-requested**, 0 findings, 0 gate) → dev (pass, timed out) → validation (pass) → review (pass) → dev (pass) → validation (pass) → review (**changes-requested**, 0 findings, 0 gate) → dev (pass, 2 attempts, timed out) → validation (pass) → review (pass) |

### T-051 — Pytest Marker Update and Smoke Test (Completed)

**4 iterations** through the pipeline. The review returned **changes-requested** twice with **0 findings, 0 gate, and empty verify** — both false positives caused by a pi_backend JSON parsing bug (see below). The dev agent was killed by timeout twice (1200s total). The human made two factory bug fixes during the session.

#### Deliverables

- `pyproject.toml` — Added `sim` marker to `[tool.pytest.ini_options].markers`
- `tests/sim/test_smoke.py` (46 lines) — Smoke test suite with 2 tests:
  - `test_import_all_modules` — Imports all 11 sim modules (scenario, detection_spawner, recorder, text_input, renderer, hud, testbench, injector, bug_capture, plotter, bug_to_task)
  - `test_load_all_scenarios` — Loads and validates all 5+ scenario YAML files from `scenarios/`
- `scripts/gates/sim_smoke.py` — Standalone gate that runs `pytest -m sim`

#### Review Iteration Details

| Iteration | Result | Findings | Gate | Key Issue |
|-----------|--------|----------|------|-----------|
| 1 | changes-requested | 0 | 0 | **False positive** — pi_backend parsed a literal ```` ```json ```` fragment from the agent's thinking block instead of the real JSON output. The parser used `findall` (forward search), which matched the quoted fence first. |
| 2 | pass | — | — | Review passed. But the dev agent was killed by total timeout (1200s) — `backend_ok: false`. The human committed the smoke test file (`9615a9a`). |
| 3 | changes-requested | 0 | 0 | **False positive** — same root cause. The fix (`c9ecaf8`) was applied by the human after this iteration. |
| 4 | pass | — | — | Final review passed with static confidence. Reviewer could not run pytest or git (bash disabled in REVIEW role). |

#### Factory Bug Fixes Applied During Session

Two fixes were committed by the human during this session:

1. **`c9ecaf8` fix(pi-backend): parse last json block to avoid false changes-requested from literal fence in thinking**
   - Changed `_JSON_BLOCK` regex forward `findall` to backward search using `rfind("```json")` + `find("```")` after the start.
   - The agent's thinking block frequently quoted the prompt ("Emit ONLY a fenced ```json block"), creating a literal ```` ```json ```` that the forward regex matched first, swallowing the real JSON block.
   - Added regression test `test_parse_extracts_json_when_thinking_contains_literal_fence`.
   - **This directly fixes the two "false changes-requested" iterations in this session.**

2. **`ba6da8a` fix(orchestrator): stop the reviewer asking humans to run gates it cannot run**
   - REVIEW role has `Scope(bash="deny")` by design, but only CONTEXT_GATHERER's prompt said so. The reviewer hit the denial at runtime with no guidance and improvised by telling the human to run commands that `run_validation` had already executed deterministically.
   - Fixed: REVIEW's prompt now states bash is disabled and that sim/integration suites already ran, pointing at the run summary.
   - `run_review` now receives `events` and passes them to `compose_prompt` (only SESSION_REVIEW was getting them before).
   - An invariant test (every bash-denied role must say so) caught SESSION_REVIEW having the same gap; its prompt was fixed too.

## Pipeline Health

- **All gates pass** — `pytest -m sim` passes (2 tests), `pytest -m unit` unaffected.
- **`scripts/gates/sim_smoke.py` exists** and runs `pytest -m sim -q`.
- **`kb-0007` still NOT resolved** — The `.pi/skills/context-completeness-audit/SKILL.md` still contains the old example format. Flagged in 6 consecutive session reports now.
- **`scripts/gates/all.py` import still broken** — The `from _proc import` issue persists. Flagged in 4 consecutive session reports.
- **`tests/sim/__init__.py` still missing** — Flagged in T-041 through T-049. Not relevant to T-051 but still missing.

## KB Entry Assessment

**Two new KB entries warranted** — both surfaced as factory bug fixes applied during this session.

### New: kb-0011 — pi_backend forward regex for ```json blocks misparses when thinking contains literal ```json fragment

| Symptom | Root Cause | Rule / Fix |
|---------|------------|------------|
| Review returns `changes-requested` with `findings: 0, gate: 0, verify: []` (empty). The agent's JSON output is correct but the pipeline doesn't see it. The session log shows `parse_pi_json` returning `{}`. | The `_JSON_BLOCK` regex used `findall` (forward search). The agent's thinking block frequently quotes the prompt ("Emit ONLY a fenced ```json block"), creating a literal ```` ```json ```` that the forward regex matches first. The real JSON block at the end is never parsed. | Search backward: use `rfind("```json")` to find the last occurrence, then `find("```")` after it to extract the real JSON. This is what `c9ecaf8` implements. |

### New: kb-0012 — REVIEW role has bash=deny but no prompt instruction; agent wastes time discovering it at runtime and asks human to run already-executed gates

| Symptom | Root Cause | Rule / Fix |
|---------|------------|------------|
| Reviewer returns pass with confidence but adds verify items telling the human to run commands that `run_validation` already executed deterministically. The review agent spends time/effort trying bash commands, failing, and improvising. | REVIEW role has `Scope(bash="deny")` set in the role definition, but only CONTEXT_GATHERER's prompt mentioned bash is disabled. The REVIEW prompt had no guidance, so the agent only discovered the denial at runtime and had no fallback instructions. | Every bash-denied role must state in its prompt that bash is disabled and point to the run summary for already-executed validation results. Add an invariant test that catches any role with bash=deny missing this instruction. This is what `ba6da8a` implements. |

### Existing KB entries status

| KB ID | Issue | Status |
|-------|-------|--------|
| kb-0004 | Windows `nul` file breaks `git add -A` | **RESOLVED** — file removed from working tree |
| kb-0007 | Context-completeness-audit skill example contradicts schema | **NOT resolved** — skill file still has old example (6th consecutive report) |
| kb-0008 | Context-gather agent times out before emitting manifest | **active** — not triggered in this session |
| kb-0009 | Review gate causes wasted iterations on 0-finding runs | **active** — not triggered in this session (T-051's false reviews were from pi_backend parsing, not the gate) |
| kb-0010 | matplotlib `use("Agg")` E402 workaround | **active** — not triggered in this session |

## Suggestions

1. **Fix kb-0007 properly** — Update `.pi/skills/context-completeness-audit/SKILL.md` to remove the stale `proven`/`pass`/`evidence` example format. Flagged in 6 consecutive session reports.

2. **Fix `scripts/gates/all.py` import** — The `from _proc import` issue is noted in 4 consecutive session reports. Either fix the import path or add a note that it must be run from the `scripts/gates/` directory.

3. **Create `tests/sim/__init__.py`** — Empty file, referenced in the plan in Task 1, missing since T-041. Adding it would eliminate a recurring distraction.

4. **Monitor dev agent timeout behavior** — The dev agent was killed by timeout twice in this session (1200s total). The same pattern occurred in T-048. The agent likely completes the work but stalls in a long-running interaction. Consider:
   - Adding per-turn limits (e.g., 300s idle + 900s total) to avoid losing completed work.
   - Having the runner capture partial output before killing the agent, so the commit message and diff are preserved.

5. **The two factory fixes applied during this session (`c9ecaf8`, `ba6da8a`) should be reviewed for completeness** — The pi_backend fix now uses backward search (`rfind`), which is correct for the current prompt structure. However, if the agent ever emits a ```` ```json ```` block in a text block *after* the real JSON output (e.g., a postscript), the backward search would pick the wrong one. Consider whether the protocol should be changed to enforce that the agent emits exactly one ```` ```json ```` block, or that the real JSON is always the last message block rather than the last occurrence of the fence pattern.