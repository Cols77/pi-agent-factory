# T-2 report — give `requirement_quality` a real criterion

## What I implemented

`src/coherence/navigate/health.py`, dimension 1 (`requirement_quality`) inside
`compile_health_dimensions`:

- Added a private helper `_has_resolvable_acceptance(root, req)` (new, placed just above
  `compile_health_dimensions`) that returns `True` when a `Requirement` carries at least one
  `AcceptanceCriterion` whose `VerificationBinding` is resolvable:
  - `kind == "manual"` → resolvable as-is (parser already guarantees a nonblank `reason`).
  - `kind in ("test_marker", "harness")` → resolvable only when `(root / binding.ref).exists()`.
  - `req is None` (no matching register entry) → `False`, never raises.
- Replaced `req_quality_ok = len(sr_nodes)` with a real computation: load the register once
  (`register_by_id = {r.id: r for r in register_module.load_register(root / "requirements")}`),
  then `req_quality_ok = sum(1 for n in sr_nodes if _has_resolvable_acceptance(root, register_by_id.get(n.id)))`.
- `expected` stays `len(sr_nodes)` (55). `exempt` stays `0`. Neither changed.

## Route taken for reaching acceptance data, and why

Investigated both options named in the task:

1. **Trace-graph SR nodes** (`coherence.trace.model.Node`) — checked `src/coherence/trace/model.py`.
   `Node` is a lightweight frontmatter reader (`id, kind, title, path, exempt, deferred, proposed,
   diagram_file, scope_error, migration_hint`) — it never parses `acceptance:` and was explicitly
   documented as reading only what it needs "so `build_graph` never loads config or imports target
   code." Not usable without changing T-1's schema module or the Node dataclass, both out of scope.
2. **Load the register directly** — `health.py` already imports
   `from coherence.register import register as register_module` at module level, and
   `bundle_readiness` in the same file (lines ~131-135) already establishes the exact pattern:
   `register = {r.id: r for r in register_module.load_register(root / "requirements")}`, loaded
   once per call, looked up by id, missing entries handled as `None`.

I took route 2, reusing the established pattern verbatim (same loader call, same hoisting
discipline, same dict-by-id shape) rather than introducing a new one. `coherence → coherence` only;
nothing from `factory` was touched or imported.

An SR node with no matching register entry (`register_by_id.get(n.id)` → `None`) is handled by
`_has_resolvable_acceptance`'s explicit `if req is None: return False` — never raises.

## TDD evidence

**RED** — wrote the tests first (5 new tests in `tests/unit/coherence/test_health_dimensions.py`,
new "Dimension 1: requirement_quality" section), then ran them against the untouched tautology:

```
rtk proxy uv run pytest tests/unit/coherence/test_health_dimensions.py -k "requirement_quality" -q
```

Result: `2 failed, 4 passed`. The two failures were exactly the "does not count" cases, for exactly
the expected reason — the old code counted every SR unconditionally:

```
tests/unit/coherence/test_health_dimensions.py::test_requirement_quality_sr_without_acceptance_does_not_count
    assert (rq.satisfied, rq.expected) == (0, 1)
    AssertionError: assert (1, 1) == (0, 1)

tests/unit/coherence/test_health_dimensions.py::test_requirement_quality_test_marker_with_missing_ref_does_not_count
    (same failure shape)
```

The 4 "counts" tests passed even before the fix, which is expected and correct: the old tautology
(`req_quality_ok = len(sr_nodes)`) counts *every* SR regardless of content, so any single-SR fixture
asserting "this counts" happens to already read `(1, 1)`. Only the "does not count" assertions can
distinguish the tautology from a real predicate — which is exactly why the brief names that case as
the load-bearing one.

**GREEN** — after implementing `_has_resolvable_acceptance` and rewiring `req_quality_ok`:

```
rtk proxy uv run pytest tests/unit/coherence/test_health_dimensions.py -q
```

Result: `14 passed, 16 warnings in 1.23s` (14 = 9 pre-existing + 5 new).

## Full required suite

```
rtk proxy uv run pytest tests/unit/coherence/ tests/unit/system/ tests/unit/trace/ tests/unit/requirements/ -q
```

Result: `1 failed, 1331 passed, 1 skipped`.

The one failure, `tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser`,
is **pre-existing and unrelated**: it asserts that the `factory.simulation` CLI shim file still
contains `add_parser("run"...)` text, but that shim is now a pure `sys.modules` redirect to
`coherence.measurement.cli` with no `add_parser` calls of its own — a drift between the shim and
this test, nothing to do with `acceptance:`/`requirement_quality`. Confirmed pre-existing by
stashing my changes and re-running the same single test against unmodified `HEAD`:

```
git stash
rtk proxy uv run pytest tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser -q
  -> FAILED (same assertion, same message)
git stash pop
```

I did not touch this test or the shim — out of scope for T-2.

## `coherence navigate health --json` — the drop to 0/55

```
rtk proxy uv run coherence navigate health --json
```

`dimensions` block (verbatim):

```json
"dimensions": [
  { "name": "requirement_quality", "satisfied": 0, "expected": 55, "exempt": 0 },
  { "name": "decomposition_allocation", "satisfied": 17, "expected": 20, "exempt": 0 },
  { "name": "implementation_trace", "satisfied": 2, "expected": 24, "exempt": 0 },
  { "name": "verification_strategy", "satisfied": 55, "expected": 55, "exempt": 0 },
  { "name": "executed_evidence", "satisfied": 0, "expected": 55, "exempt": 0 },
  { "name": "validation_scenarios", "satisfied": 0, "expected": 55, "exempt": 0 },
  { "name": "evidence_freshness", "satisfied": 0, "expected": 0, "exempt": 0 },
  { "name": "suspect_relationships", "satisfied": 55, "expected": 55, "exempt": 0 },
  { "name": "nonconformance_closure", "satisfied": 1, "expected": 1, "exempt": 0 },
  { "name": "deferrals_waivers", "satisfied": 57, "expected": 173, "exempt": 0 },
  { "name": "human_review", "satisfied": 0, "expected": 0, "exempt": 0 }
]
```

`requirement_quality` is `0/55`, as expected: no SR in the current register yet carries an
`acceptance:` array (T-3 lands those). `verification_strategy` (NC-B's other half, `health.py:694-710`)
is unchanged at `55/55` — untouched, confirming the scope boundary held.

## Existing tests changed

None. Grepped the whole `tests/` tree for `requirement_quality` and `compile_health_dimensions`
outside `test_health_dimensions.py` — no other test references this dimension's values, so nothing
encoded the old tautology elsewhere.

## Files changed

- `src/coherence/navigate/health.py` — new `_has_resolvable_acceptance` helper (+28 lines);
  `req_quality_ok` computation replaced (comment + 6 lines of logic in place of the old
  `req_quality_ok = len(sr_nodes)` one-liner). File grew from 817 → 844 lines.
- `tests/unit/coherence/test_health_dimensions.py` — new `_write_sr_with_acceptance` fixture helper
  and a new "Dimension 1: requirement_quality" section with 5 tests (+104 lines).

Commit: `9e6ac6a feat(health): give requirement_quality a real criterion (NC-B, half 1)`.

## Self-review findings

Read the diff (`git diff HEAD~1`) with fresh eyes before reporting:

- Naming: `_has_resolvable_acceptance` names exactly what it checks; `register_by_id` mirrors the
  existing `register` local in `bundle_readiness` closely enough to read as the same pattern.
- No `factory` import added; `coherence → coherence` only (`register_module` was already imported
  at module top for `bundle_readiness`'s use).
- No exemption logic added (`exempt` stays hardcoded `0` as instructed).
- `verification_strategy` block (694-710, now shifted by the same +28 lines but otherwise
  byte-identical) is untouched — diffed it directly against `HEAD~1` to confirm.
- `register.py`/T-1 schema untouched; no `acceptance:` authored into any `requirements/SR-*.md`;
  no `@pytest.mark.sr` decorator added anywhere.
- Tests exercise real behavior (write actual SR files to `tmp_path`, actual sibling files for
  `ref` resolution, run the real `compile_health_dimensions`) — no mocking of the loader or the
  helper.
- Considered and rejected adding an extra test for "SR node exists but register load raises
  entirely" (e.g., a malformed sibling SR file) — `load_register` fails the whole call on any
  malformed file (pre-existing behavior, already relied on identically by `bundle_readiness` in
  this same module), so that failure mode is not new here and is out of this task's scope.

## Concerns

- `verification_strategy` (`health.py:694-710`) is exactly what the brief describes: it still
  fabricates a nonzero `verification_strategy_ok` from "any obligation with a nonblank
  `resolve_cmd`" rather than a real satisfaction check — it reads as NC-B's still-open second half,
  owned by FEAT-002. Confirmed unchanged, not touched, per scope limits.
- `health.py` grew from 817 to 844 lines (already noted in the task brief as a known concern for
  this file); I kept the addition to one small helper plus a 6-line call site rather than inlining,
  per the brief's guidance, and did not restructure the file.
- None of the 55 real SRs will show `requirement_quality` progress until T-3 authors
  `acceptance:` entries — this is the intended, stated outcome of this task, not a regression.
