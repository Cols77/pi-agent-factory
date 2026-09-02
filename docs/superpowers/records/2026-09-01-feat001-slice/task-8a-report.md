# T-8a report — wire `human_review` to a durable review DecisionFile

## Canonical gate identity settled on, and why

- **Item id / gate id**: `review:<sr_id>` (e.g. `review:SR-001`), always identical to each other
  (`decision_file.gate_id == item_id`).
- **`run_dir`**: the project `root` passed into `compile_obligations`/`resolve_profile` — the same
  `root` every other obligation helper in `compiler.py` already receives, and the same convention
  the existing `sr:` authoring-consent gate in `coherence/inbox.py::_authoring_consent_items` already
  uses (`decision_path(root, f"sr:{req.id}")`). There is no separate "run" concept for a per-SR
  review decision anywhere else in the codebase, so introducing one would be a second, undocumented
  identity scheme. Mirroring the already-shipped `sr:` gate keeps exactly one identity convention for
  every per-SR human gate.
- **`artifact_ref`**: `f"artifact:{<sr file path relative to root, posix>}"`, computed from the SR's
  own trace node path (`_sr_node_path`, already used by `_verification_result_obligation`). This
  again mirrors the `sr:` gate's `expected_artifact_ref = f"artifact:{requirement_path}"` exactly,
  and `tests/unit/coherence/test_inbox.py::test_review_decision_does_not_satisfy_sr_authoring_consent`
  already anticipated a `review:SR-001` gate with `artifact_ref: "artifact:requirements/SR-001.md"` —
  i.e. this identity was already implicit in a prior task's test fixture, not invented here.

This was a case where the brief said "ask rather than inventing" if the identity required an
un-settled choice — I did not need to ask because the identity was already fully determined by two
independent existing conventions (the `sr:` gate's own pattern, and the inbox test's own fixture for
a `review:` gate) that agree with each other.

## How the decision is resolved and validated

In `src/coherence/policy/compiler.py::_human_review_obligation`:

1. `item_id = f"review:{sr_id}"`; `path = decision_path(root, item_id)` (existing store helper).
2. If the SR has no trace node (`_sr_node_path` returns `None`), `reviewed` stays `False` — this is
   unchanged from before my change.
3. Otherwise compute `expected_artifact_ref` from the SR's own file path, relative to `root`. If that
   relative-path computation fails (SR path outside root), `reviewed` stays `False`.
4. If `path.is_file()`, load it with the existing `coherence.gate.store.load_decision` (which itself
   routes through `DecisionFile.from_dict` and `validate_decisions` — no new parsing, no new
   validation). A `CorruptDecisionFile` is caught and leaves `reviewed = False` — never re-raised as
   a raw traceback, never treated as truthy.
5. `reviewed` is `True` **only** when *all* of:
   - `decision_file.gate_id == item_id`
   - `decision_file.artifact_ref == expected_artifact_ref`
   - `len(decision_file.decisions) == 1`
   - `decisions[0].item_id == item_id`
   - `decisions[0].action == "accept"`

`reviewed` is initialized to `False` and only one branch ever sets it to `True`; there is no
`try/except` that swallows an error into a truthy value, no default, and no fallback.

`requiredness` logic (`blocking` under `high_assurance`, `not_applicable` otherwise) and `state`
derivation (`"satisfied" if reviewed else "open"`) are unchanged in shape from the pre-existing
(hard-coded) function — only `reviewed`'s source changed.

`resolve_cmd`/`reason` never claim a review occurred: the reason is always
`"{profile} requires a recorded human review decision for {sr_id}"` regardless of state, and
`resolve_cmd` names the exact `gate_id`/`item_id`/`artifact_ref`/file path a human reviewer still
needs to act on (or the reason resolution is impossible: no trace node / SR path outside root).

## Case list and what each yields

| Case | `state` | Notes |
|---|---|---|
| Missing decision file | `open` | unchanged pre-existing behaviour |
| Valid human `accept` for `review:<sr_id>` (matching gate_id/artifact_ref/item_id) | `satisfied` | only path to `satisfied` |
| `reject` | `open` | action != `accept` |
| `defer` | `open` | action != `accept` |
| Malformed/corrupt JSON file | `open` | `CorruptDecisionFile` caught, not raised |
| Wrong item id inside file (`decisions[0].item_id` != `review:<sr_id>`) | `open` | item_id check |
| Wrong `gate_id` field inside file (file at correct path, `gate_id` names a different SR) | `open` | gate_id check |
| `sr:` authoring-consent decision (different item family) | `open` | different filename (`sr-...` vs `review-...`), and even if colocated would fail item_id/gate_id checks |
| `accept` for `review:SR-002` vs. obligation for `SR-003` | `open` for SR-003 | different `decision_path` filename entirely — no cross-SR leakage |
| `prototype` profile, no decision | `requiredness=not_applicable`, `state=open` | unchanged |
| `prototype` profile, valid `accept` present | `requiredness=not_applicable`, `state=satisfied` | `reviewed` computed independent of profile, same as `verification_result`'s own pattern |
| `high_assurance` profile, no decision | `requiredness=blocking`, `state=open` | unchanged |
| `high_assurance` profile, valid `accept` | `requiredness=blocking`, `state=satisfied` | the new, correct outcome |

## TDD evidence

### RED (real assertion failures against the hard-coded `reviewed = False`)

Command: `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts='' -k "human_review"`

```
...F.......F                                                             [100%]
================================== FAILURES ===================================
____________ test_human_review_valid_accept_satisfies_only_that_sr ____________

tmp_path = WindowsPath('C:/Users/33630/AppData/Local/Temp/pytest-of-33630/pytest-6352/test_human_review_valid_accept0')

    def test_human_review_valid_accept_satisfies_only_that_sr(tmp_path):
        _seed_high_assurance_sr(tmp_path, "SR-101")
        _write_review_decision(tmp_path, "SR-101")

        obligations = compile_obligations(tmp_path, "sr:SR-101")
        hr = next(o for o in obligations if o.kind == "human_review")
>       assert hr.state == "satisfied"
E       AssertionError: assert 'open' == 'satisfied'
E
E         - satisfied
E         + open

tests\unit\coherence\policy\test_compiler.py:329: AssertionError
_____ test_human_review_prototype_accept_is_satisfied_but_not_applicable ______

tmp_path = WindowsPath('C:/Users/33630/AppData/Local/Temp/pytest-of-33630/pytest-6352/test_human_review_prototype_ac0')

    def test_human_review_prototype_accept_is_satisfied_but_not_applicable(tmp_path):
        (tmp_path / "requirements").mkdir()
        (tmp_path / "requirements" / "SR-110.md").write_text(
            "---\nid: SR-110\ntitle: t\nstatement: s\ndomain: d\n---\n",
            encoding="utf-8",
        )
        _write_review_decision(tmp_path, "SR-110")

        obligations = compile_obligations(tmp_path, "sr:SR-110")  # project default: prototype
        hr = next(o for o in obligations if o.kind == "human_review")
        assert hr.requiredness == "not_applicable"
>       assert hr.state == "satisfied"
E       AssertionError: assert 'open' == 'satisfied'
E
E         - satisfied
E         + open

tests\unit\coherence\policy\test_compiler.py:448: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/coherence/policy/test_compiler.py::test_human_review_valid_accept_satisfies_only_that_sr
FAILED tests/unit/coherence/policy/test_compiler.py::test_human_review_prototype_accept_is_satisfied_but_not_applicable
2 failed, 10 passed, 31 deselected in 27.50s
```

Both failures are real assertion failures (`'open' == 'satisfied'`) driven by the hard-coded
`reviewed = False`, not import/collection errors — proving the defect the task exists to fix, not
merely that an API changed. All 10 other new `human_review` cases passed even before the fix,
because the pre-existing hard-coded `False` already produces the correct `open`/`not_applicable`
outcome for every "must stay open" case — only the two "must become satisfied" cases could fail RED,
and both did.

### GREEN

Command: `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts=''`

```
......................................s....                              [100%]
42 passed, 1 skipped in 1.89s
```

Command: `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py tests/unit/coherence/test_gate.py tests/unit/coherence/test_inbox.py -q -o addopts=''`

```
......................................s................................. [ 61%]
.............................................                            [100%]
116 passed, 1 skipped in 3.36s
```

## Verification commands run

1. `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts=''` → `42 passed, 1 skipped`
2. `rtk proxy uv run pytest tests/unit/ -q` (run in the **foreground**, blocked ~9 min, no background/`run_in_background`):
   ```
   FAILED tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser
   1 failed, 2953 passed, 13 skipped, 113 warnings in 538.02s (0:08:58)
   ```
   Exactly the one known, pre-existing failure named in my task instructions
   (`test_every_shell_command_names_a_real_subparser`) — and no other failure. I verified this is
   the only `FAILED` line in the entire run.
3. `rtk proxy uv run ruff check .` → `All checks passed!`
4. `rtk proxy uv run pyright src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py` → `0 errors, 0 warnings, 0 informations`
5. `rtk proxy uv run coherence navigate health --json` → see below.

## What `human_review` reads now, and why

```json
{ "name": "human_review", "satisfied": 0, "expected": 0, "exempt": 0 }
```

Still **0/0**, identical to before my change. This is correct, not a regression or a missed wiring:

- I checked every requirement source in this worktree — no `docs/features/*.md` declares
  `profile: high_assurance`, and `.factory/factory.yaml` sets no project-default `profile:` override
  (`grep -rl "profile: high_assurance" docs/features requirements .factory` → no matches; `grep -i
  profile .factory/factory.yaml` → no matches). The project default profile is therefore `prototype`
  for every real SR in this repo today.
- Under `prototype`, `human_review`'s `requiredness` is `not_applicable` for every SR (unchanged
  behaviour, preserved by this task). The health dimension counts only `required`/`blocking`
  obligations toward `expected`, so `expected` stays `0` regardless of whether any `review:<sr_id>`
  DecisionFile exists.
- No real `review:<sr_id>` DecisionFile exists anywhere in this repo (confirmed: `find . -iname
  "gate-decisions"` returns nothing at all in the working tree).

So `0/0` reads exactly as it should: the mechanism is now wired and will report a real number the
moment (a) any SR is put under `high_assurance` and (b) a human writes a real `review:<sr_id>`
`accept` DecisionFile for it. Neither condition holds today, and I did not manufacture either one —
per the task's explicit instruction, that is the correct outcome, not something to "fix" by adding a
decision or a profile override myself.

## No decision file exists outside `tmp_path`

- `git status --porcelain=v1` shows only the two files I intentionally changed
  (`src/coherence/policy/compiler.py`, `tests/unit/coherence/policy/test_compiler.py`) plus one
  pre-existing, controller-owned change to
  `docs/superpowers/plans/2026-09-01-feat001-reference-run.md` that I did not touch and did not
  stage.
- `find . -iname "gate-decisions"` (run from the worktree root) returns **no matches** — there is no
  `gate-decisions` directory anywhere in the repository tree, confirming every `DecisionFile` I
  created in this task (all via `write_decision`/raw JSON writes in the new tests) lives only inside
  pytest's own `tmp_path` fixtures, which are outside the repository entirely and never staged.
- I never called `write_decision`, nor hand-wrote a decision JSON file, against `root` in
  `src/coherence/policy/compiler.py` itself — the production code only *reads* via
  `coherence.gate.store.decision_path`/`load_decision`; it never writes a decision.

## Files changed

- `src/coherence/policy/compiler.py` — `_human_review_obligation` rewritten to resolve a real
  `review:<sr_id>` decision through the existing gate store instead of a hard-coded `False`.
  `_verification_result_obligation` and `_test_marker_obligation` untouched.
- `tests/unit/coherence/policy/test_compiler.py` — 12 new focused tests covering the case list above
  (`test_human_review_missing_decision_stays_open_under_high_assurance`,
  `test_human_review_valid_accept_satisfies_only_that_sr`,
  `test_human_review_accept_for_one_sr_does_not_satisfy_another`,
  `test_human_review_reject_leaves_obligation_open`,
  `test_human_review_defer_leaves_obligation_open`,
  `test_human_review_malformed_decision_file_stays_open`,
  `test_human_review_wrong_item_id_inside_file_stays_open`,
  `test_human_review_wrong_gate_id_inside_file_stays_open`,
  `test_human_review_authoring_consent_decision_does_not_satisfy`,
  `test_human_review_prototype_accept_is_satisfied_but_not_applicable`, plus the two pre-existing
  `human_review` tests left unmodified).

No other files were changed. `src/coherence/gate/model.py`, `gate/service.py`, and `gate/store.py`
were **not** touched — the existing store/model machinery was sufficient as-is; no narrowly-justified
shared-validation fix was needed.

## Self-review findings

Re-read the diff with the task's own question in mind: **is there any path by which the obligation
reaches `satisfied` without a human decision on disk?**

- `reviewed` is initialized `False` and set `True` in exactly one place, gated by a five-way `and`
  chain (`gate_id`, `artifact_ref`, decision count, `item_id`, `action == "accept"`). There is no
  `or`, no `.get(..., True)`, no truthy default anywhere in the chain.
- The only `except` clause (`CorruptDecisionFile`) explicitly sets `reviewed = False` in its body —
  it does not `pass` into a prior truthy value, and it catches only the store's own typed exception,
  never a bare `except:`.
- `sr:` decisions cannot leak in: `decision_path(root, "review:<sr_id>")` and
  `decision_path(root, "sr:<sr_id>")` are different files (`review-SR-x.json` vs `sr-SR-x.json`), so
  an authoring-consent decision is never even read by this function, and the explicit
  `test_human_review_authoring_consent_decision_does_not_satisfy` test pins that.
  `test_human_review_wrong_gate_id_inside_file_stays_open` additionally pins that even a
  maliciously/accidentally mislabeled file *at the correct path* cannot satisfy the obligation via
  its internal `gate_id` field.
  `test_human_review_wrong_item_id_inside_file_stays_open` pins the internal `item_id` field the same
  way.
- Cross-SR leakage is impossible by construction: the store path is keyed by `item_id`, which embeds
  `sr_id`, so `review:SR-002`'s file is never consulted when compiling `SR-003`'s obligation
  (`test_human_review_accept_for_one_sr_does_not_satisfy_another` pins this).
- `requiredness` (`blocking`/`not_applicable`) is derived purely from `profile`, independent of
  `reviewed` — no path where a profile choice silently flips `state`.
- No `DecisionFile` with an accept/reject/defer outcome was written anywhere outside a `tmp_path`
  fixture (confirmed above via `git status` and the repo-wide `gate-decisions` search).

I found no path to a false `satisfied`.

## Concerns

None that block this task. Two observations for whoever picks up the surrounding work:

1. `human_review` currently reads `0/0` for the whole real project because no SR here is under
   `high_assurance` yet — the dimension will stay silent (not wrong, just uninformative) until some
   later task actually puts a real SR under that profile. That is expected/by-design for this task,
   not a defect.
2. There is still no CLI surface for a human to *author* a `review:<sr_id>` `accept` decision (only
   the Python `write_decision` API and the existing gate model/store). That is out of this task's
   scope (T-8a is the agent-owned read/wire half of R-7 only) but is presumably the next piece needed
   before `human_review` can move off `0/0` in practice.
