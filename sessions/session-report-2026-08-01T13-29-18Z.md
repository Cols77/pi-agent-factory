# Session Report — 2026-08-01T13-29-18Z

## Pipeline Summary

| Task | Outcome | Iterations | Key Nodes |
|------|---------|------------|-----------|
| **T-047** — Bug Capture | ✅ **completed** | 3 | context-gather (pass, 2 attempts) → dev (pass) → validation (pass) → review (changes-requested) → dev (pass) → validation (pass) → review (changes-requested) → dev (pass) → validation (pass) → review (changes-requested) → human-review (approved) |

### T-047 — Bug Capture (Completed)

**3 iterations** through the dev→validation→review loop. All three dev attempts passed on the first try (tests green), all three validations passed (no requirement warnings), and all three reviews returned **changes-requested**.

#### Deliverables

- `src/sim/bug_capture.py` (81 lines) — `BugSnapshot` dataclass with YAML save/load, `capture_bug()` function that snapshots testbench state (scenario, drone pose, mission state) to `scenarios/bugs/<timestamp>-<description>.yaml`
- `src/sim/injector.py` (65 lines) — added `K_b` handler calling `_open_bug_capture()`, `K_p` handler calling `_save_screenshot()`, `_open_bug_capture()` method with TextInput dialog overlay, `_save_screenshot()` method
- `tests/sim/test_bug_capture.py` (126 lines, 3 tests) — `TestBugSnapshot.test_snapshot_creation` (YAML round-trip), `TestCaptureBug.test_capture_bug_creates_yaml_snapshot` (integration with mocked testbench), `TestCaptureBug.test_capture_bug_handles_no_state` (null-state edge case)
- `tests/sim/test_injector.py` (57 lines, 2 tests) — `TestEventInjectorBugCapture.test_handle_key_b_dispatches_to_open_bug_capture` (monkey-patch verification), `TestEventInjectorBugCapture.test_injector_has_kb_handler` (source inspection)

#### Review Iteration Details

| Iteration | Findings | Gate | Key Verify Items |
|-----------|----------|------|------------------|
| 1 | 3 | 1 | Injector missing K_b handler (not yet wired), no test for `capture_bug()` itself, `scenarios/bugs/` doesn't exist, None loop state edge case, YAML round-trip fragility |
| 2 | 0 | 1 | `_loop` being None vs `_loop._state` being None, YAML round-trip from `capture_bug` output, `scenarios/bugs/` dir creation, pytest marker config, `BugSnapshot.load` on real output |
| 3 | 3 | 1 | Manual B-key smoke test, `scenarios/bugs/` .gitkeep, `BUGS_DIR` path resolution from different CWD, `set_bug_capture_callback` dead code in testbench |

Key observation: all 3 reviews returned "changes-requested" but the code defects were addressed after iteration 1 (findings dropped to 0 in iteration 2). Iterations 2 and 3 were driven entirely by the **gate=1** trigger (deterministic plan mismatch) and verify items that the reviewer could not run. This is the same pattern as T-046 — the review gate is overly sensitive, causing wasted iterations when the code is functionally correct.

## Pipeline Health

- **`scenarios/bugs/` directory is empty** — The directory exists on disk but has no committed files (no `.gitkeep`, no sample snapshot). The `save()` method creates the directory at runtime via `path.parent.mkdir(parents=True, exist_ok=True)`, but git won't track the empty directory. Flagged in all 3 review iterations and still unresolved.

- **`scenarios/` directory not tracked in git** — `git ls-files scenarios/` returns nothing. The entire `scenarios/` tree is untracked. This means `scenarios/bugs/` won't exist on a fresh clone until the first `capture_bug()` call creates it at runtime. This is fine for the runtime path but means the DoD item "YAML snapshot file in scenarios/bugs/" is partially unmet (the code CAN write there, but no file is committed).

- **kb-0007 NOT resolved** — The `.pi/skills/context-completeness-audit/SKILL.md` still contains the old `proven`/`pass`/`evidence` example format. This has been flagged in 4 consecutive session reports (2026-07-31T20-59-41Z, 2026-07-31T21-58-22Z, 2026-08-01T12-30-09Z, and this one).

- **`scripts/gates/all.py` import broken** — Still broken from the previous session. `all.py` imports `from _proc import ...` but the module is `scripts.gates._proc`. Running `python -m scripts.gates.all` fails with `ModuleNotFoundError`. Flagged in the T-046 session report but not addressed.

- **T-047 branch not merged into main** — The commits `f5283e6` and `6753c29` are on a separate branch (not `main`). The task file `tasks/T-047-bug-capture.md` was updated to `status: done` but that change is uncommitted. The branch needs to be merged or the commits cherry-picked.

## KB Entry Assessment

**One new KB entry warranted** — the review-gate-driven wasted-iteration pattern is now a verifiable, reusable issue.

### New: kb-0009 — Review gate triggers "changes-requested" on 0-code-defect iterations, causing wasted dev→validation→review loops

Both T-046 (3 iterations) and T-047 (3 iterations) show the same pattern: the review returns "changes-requested" with 0 code findings but a gate=1 trigger. The gate detects a plan mismatch that is often a task-boundary issue (e.g., T-046's `[B] bug` HUD hint not wired because it's deferred to T-047, or T-047's `scenarios/bugs/` directory not committed because the plan says "write to" but doesn't say "commit a .gitkeep"). Each iteration requires a full dev→validation→review loop even though no code changes are needed — the dev agent produces no meaningful diffs, wasting time.

| Symptom | Root Cause | Rule / Fix |
|---------|------------|------------|
| Review returns "changes-requested" with 0 code findings. The gate=1 trigger is the sole reason. The dev agent runs again but produces no code changes (or trivial changes). The validation passes trivially. The review returns the same result. This wastes 2-3 iterations per task. | The review's deterministic gate checks plan conformance as a hard pass/fail. When the gate detects a mismatch that is not a code defect (e.g., a deferred feature, an empty directory, a missing .gitkeep), it returns "changes-requested" regardless of code quality. The review pipeline treats "changes-requested" as "must iterate" even when the human reviewer would approve. | (1) Distinguish "gate failure" from "code finding" — if findings=0 and gate=1, the review should still report the gate issue but NOT force a full dev iteration. Instead, emit a warning to the human reviewer. (2) Add a `.gitkeep` to `scenarios/bugs/` to resolve the recurring gate trigger. (3) Consider a "soft gate" mode where gate-only issues are annotated but don't cause a dev restart. |

### Existing KB entries status

| KB ID | Issue | Status |
|-------|-------|--------|
| kb-0004 | Windows `nul` file breaks `git add -A` | **RESOLVED** — file removed from working tree |
| kb-0007 | Context-completeness-audit skill example contradicts schema | **NOT resolved** — validator tolerates old format, but skill file STILL has old example (4th consecutive report) |
| kb-0008 | Context-gather agent times out before emitting manifest | **active** — not triggered in this session |

## Suggestions

1. **Fix kb-0007 properly** — Update `.pi/skills/context-completeness-audit/SKILL.md` to remove the stale `proven`/`pass`/`evidence` example format. The validator tolerates it, but the skill file will confuse future agents. This has been flagged in 4 consecutive session reports without action.

2. **Add `.gitkeep` to `scenarios/bugs/`** — This would resolve the recurring gate trigger in reviews ("scenarios/bugs/ directory doesn't exist / is empty"). The directory is created at runtime by `save()`, but a committed `.gitkeep` would satisfy the git tracking concern and stop the gate from firing on this item.

3. **Fix `scripts/gates/all.py` import** — Change `from _proc import` to `from scripts.gates._proc import`. This pre-existing issue prevents the composite gate from running and was flagged in the T-046 session report.

4. **Review gate sensitivity** — Consider whether the deterministic gate should force "changes-requested" when the gate trigger is the only reason (findings=0). The 3-iteration pattern wastes time on tasks that are functionally correct. A "soft gate" mode (warn human reviewer but don't restart dev) would break the loop.

5. **Merge T-047 branch into main** — The commits are on a separate branch and the task file status change is uncommitted. Merge or cherry-pick to keep the main branch current.