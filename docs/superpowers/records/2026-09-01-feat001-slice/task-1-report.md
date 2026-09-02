# Task T-1 report — `acceptance:` schema field

## What I implemented

In `src/coherence/register/register.py` (canonical module):

- `_VERIFICATION_KINDS = ("test_marker", "harness", "manual")`.
- `VerificationBinding` frozen dataclass: `kind: str`, `ref: str | None = None`,
  `reason: str | None = None`.
- `AcceptanceCriterion` frozen dataclass: `id: str`, `criterion: str`,
  `verification: VerificationBinding`, plus `qualified_id(req_id: str) -> str`
  returning `f"{req_id}/{self.id}"` — the `<SR-ID>/<AC-ID>` addressability helper
  the parent spec requires. It's the one obvious way to build the ref string; it
  takes `req_id` as a parameter rather than storing it, since a criterion doesn't
  own its parent SR's id. No resolver, index, or CLI verb was built (YAGNI, per
  the brief).
- `Requirement` gained `acceptance: tuple[AcceptanceCriterion, ...] = ()` as its
  last field (keyword-constructed elsewhere in the codebase, so appending a
  defaulted field at the end is safe — verified by grepping every `Requirement(`
  call site).
- `_parse_acceptance(path, raw) -> tuple[AcceptanceCriterion, ...]`: validates and
  builds the tuple, raising a plain `ValueError` in the existing convention
  (`f"{path.name}: ..."`) for every malformed case, naming the offending
  criterion's `id` once known, or its list index when the `id` itself is missing/
  blank or the entry isn't a mapping. Duplicate `id` within one SR is rejected.
  `test_marker`/`harness` require non-blank `ref`; `manual` requires non-blank
  `reason` instead. Unknown `kind` is rejected. The whole list is validated before
  any tuple is returned, so a malformed second entry rejects the first
  well-formed entry too — never a partial keep.
- `parse_requirement` calls `_parse_acceptance` only when `"acceptance" in meta`;
  otherwise `acceptance=()`, so an SR without the field parses exactly as before.
- `__all__` gained `"AcceptanceCriterion"` and `"VerificationBinding"`.

## Files changed

- `src/coherence/register/register.py` — schema + parser (93 insertions, 0
  deletions; no existing code removed or altered beyond the two integration
  points).
- `tests/unit/requirements/test_acceptance.py` — new test file, 18 tests.

No other file was touched. `src/factory/requirements/register.py` (the
deprecated shim) needed **no change** — it does `from coherence.register.register
import *` and sets `__all__ = _canonical.__all__` dynamically at import time, so
it picked up `AcceptanceCriterion` and `VerificationBinding` automatically.
Verified directly:

```
$ rtk proxy uv run python -c "
import warnings; warnings.simplefilter('ignore')
from factory.requirements.register import AcceptanceCriterion, VerificationBinding
print('shim re-exports ok:', AcceptanceCriterion, VerificationBinding)
"
shim re-exports ok: <class 'coherence.register.register.AcceptanceCriterion'> <class 'coherence.register.register.VerificationBinding'>
```

`src/coherence/navigate/health.py`, `requirements/SR-*.md` authoring, and
`@pytest.mark.sr` decorators were left untouched, per scope.

## `content_checksum` — confirmed unaffected

Read `content_checksum` (`register.py:80-98` before my change) before touching
anything. It hashes only `req.statement.strip()`, `b.harness`, `b.experiment`,
`b.metric`, `b.assert_expr`, `b.trials`, and `repr(b.window)` — all drawn from
`req.binding`. It never reads `req.acceptance`. Since I added a new field with a
default and never referenced it in `content_checksum`, the digest for every
existing SR (bound or proposed) is byte-for-byte identical to before. This is
also proven empirically below: `requirements/index.json` (which embeds every
bound SR's checksum) is byte-identical after the change.

## TDD evidence

**RED** — wrote `tests/unit/requirements/test_acceptance.py` importing
`AcceptanceCriterion`/`VerificationBinding` (not yet implemented) before
touching `register.py`:

```
$ rtk proxy uv run pytest tests/unit/requirements/test_acceptance.py -q
=================================== ERRORS ====================================
_________ ERROR collecting tests/unit/requirements/test_acceptance.py _________
ImportError while importing test module '...\tests\unit\requirements\test_acceptance.py'.
...
E   ImportError: cannot import name 'AcceptanceCriterion' from 'coherence.register.register' (...\src\coherence\register\register.py)
=========================== short test summary info ===========================
ERROR tests/unit/requirements/test_acceptance.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.47s
```

This is the expected failure: the schema didn't exist yet, so collection failed
on the import — not a logic failure, confirming the tests actually exercise code
that had to be written.

**GREEN** — after implementing the schema and parser:

```
$ rtk proxy uv run pytest tests/unit/requirements/test_acceptance.py -q
..................                                                       [100%]
18 passed in 1.30s
```

18/18 passing, pristine output (no warnings).

## Full verification run

```
$ rtk proxy uv run pytest tests/unit/requirements/ tests/unit/coherence/ -q
...
689 passed, 27 warnings in 29.87s
```

Baseline (same command, before any change) was `671 passed, 27 warnings` — the
27 warnings are pre-existing `DeprecationWarning`s from unrelated
`factory.trace`/`factory.goals`/`factory.simulation` shims imported by other
test modules, present before my change and unaffected by it. The +18 tests are
exactly `test_acceptance.py`. No new warnings were introduced.

## Backward-compatibility proof (D3)

Command and full output:

```
$ rtk proxy uv run coherence register index
{... 55 entries, all {"id": ..., "checksum": null, "proposed": true} ...}
```

```
$ git diff --stat requirements/index.json
(no output — empty diff)
```

```
$ sha256sum requirements/index.json
fce6d8f1d1bd91520d73e7262eff05bd4dbf76daaea0bd87c91f389d26295a89 *requirements/index.json
```

I captured the file's SHA-256 (`fce6d8f1...`) *before* touching `register.py`
and re-ran `coherence register index` after implementing the change: identical
hash, identical `git diff --stat` (empty). `requirements/index.json` is
byte-identical.

Direct load-and-count proof:

```
$ rtk proxy uv run python -c "
from pathlib import Path
from coherence.register.register import load_register
reqs = load_register(Path('requirements'))
print('count:', len(reqs))
print('all acceptance empty:', all(r.acceptance == () for r in reqs))
"
count: 55
all acceptance empty: True
```

All 55 existing SRs parse without error, and every one carries `acceptance ==
()` since none has the field yet.

## Self-review findings

- Read the full diff (`git diff -- src/coherence/register/register.py`, 93
  insertions, 0 deletions) after implementing. Confirmed:
  - Field names (`id`, `criterion`, `verification`, `kind`, `ref`, `reason`)
    match the brief verbatim.
  - `acceptance` is a `tuple`, defaulting to `()`, as required.
  - No new exception hierarchy — plain `ValueError` throughout, matching
    `parse_requirement`'s existing style.
  - No CLI verb, resolver, or lookup index was added for addressability — just
    the one helper method, per YAGNI instruction.
  - `cmd_index`/`requirements/index.json` shape untouched — verified via the
    checksum/diff comparison above, and by not editing `cli.py` at all.
  - `health.py`, `requirements/SR-*.md`, and `@pytest.mark.sr` were not touched.
  - All 15 malformed cases the brief lists are covered, plus the happy path,
    the addressability helper, and a "malformed second entry rejects the whole
    list, not just that entry" test.
- Nothing found worth fixing. Test names are descriptive; no mocks — all tests
  exercise `parse_requirement` end-to-end against real YAML frontmatter text
  written to `tmp_path`.

## Concerns

None. The change is additive, isolated to `register.py`, fully covered by
tests, and proven not to disturb the existing 55-SR register or its index.

---

## Fix report — review finding (Important)

**Finding:** In `tests/unit/requirements/test_acceptance.py`, all 13 malformed-case
tests used `pytest.raises(ValueError, match=...)` regexes that asserted only the
SR filename (`"SR-001.md"`) or the criterion id (`"AC-1"`/`"AC-2"`), never the
actual failure reason. Since `_parse_acceptance` prefixes every error with
`path.name` and (once known) the entry id, almost any validation failure on the
same fixture would satisfy the same regex — so the 13 tests did not distinguish
the 13 malformed cases from one another. Two Minor findings from the same review
(silently-ignored extra field on `manual`/`test_marker`/`harness`; a ~105-char
line in `register.py:151-153`) were explicitly deferred to the final whole-branch
review and were **not** touched here.

### What I changed

Tightened every malformed-case test's `match=` to the distinguishing substring
of the actual message `_parse_acceptance` raises for that specific case, with
regex metacharacters escaped where needed (`verification\.kind`):

| test | old `match=` | new `match=` |
|---|---|---|
| not-a-list | `"SR-001.md"` | `"acceptance: must be a list"` |
| entry not a mapping | `"SR-001.md"` | `"entry must be a mapping"` |
| missing `id` | `"SR-001.md"` | `r"missing required field 'id'"` |
| missing `criterion` | `"AC-1"` | `r"AC-1.*missing required field 'criterion'"` |
| blank `criterion` | `"AC-1"` | `r"AC-1.*missing required field 'criterion'"` |
| missing `verification` | `"AC-1"` | `r"AC-1.*missing required field 'verification'"` |
| unknown `kind` | `"AC-1"` | `r"AC-1.*verification\.kind must be one of"` |
| `test_marker`/`harness` missing `ref` | `"AC-1"` | `r"AC-1.*requires a non-blank 'ref'"` |
| `test_marker`/`harness` blank `ref` | `"AC-1"` | `r"AC-1.*requires a non-blank 'ref'"` |
| `manual` missing `reason` | `"AC-1"` | `r"AC-1.*requires a non-blank 'reason'"` |
| `manual` blank `reason` | `"AC-1"` | `r"AC-1.*requires a non-blank 'reason'"` |
| duplicate id | `"AC-1"` | `r"AC-1.*duplicate criterion id"` |
| malformed-entry-rejects-whole-list | `"AC-2"` | `r"AC-2.*missing required field 'verification'"` |

`_parse_acceptance`'s behaviour in `register.py` was **not** changed to
accommodate the tests, per the review's instruction. I did make one temporary,
reverted mutation to `register.py` purely to prove discrimination (see below) —
confirmed via `git diff --stat` that it left no trace.

Blank-criterion and missing-criterion share a message (blank is folded into the
same "missing required field" branch as absent, which is correct behaviour), so
those two tests intentionally share the same `match=`; they still discriminate
from all 11 other cases.

### Sanity check that the new assertions actually discriminate

Per the reviewer's own example, I temporarily edited
`src/coherence/register/register.py` line 105 so the missing-`criterion` branch
raised `"...missing required field 'verification'"` instead of `"...missing
required field 'criterion'"` (i.e. exactly the wrong-but-adjacent message the
finding described), then ran only the affected test:

```
$ rtk proxy uv run pytest tests/unit/requirements/test_acceptance.py -k test_an_entry_missing_criterion_is_rejected -q
F                                                                        [100%]
================================== FAILURES ===================================
_________________ test_an_entry_missing_criterion_is_rejected _________________
...
>       with pytest.raises(ValueError, match=r"AC-1.*missing required field 'criterion'"):
E       AssertionError: Regex pattern did not match.
E         Expected regex: "AC-1.*missing required field 'criterion'"
E         Actual message: "SR-001.md: acceptance[AC-1]: missing required field 'verification'"

tests\unit\requirements\test_acceptance.py:141: AssertionError
1 failed, 17 deselected in 0.37s
```

This is exactly the discrimination the finding asked me to prove: the old
`match="AC-1"` would have passed against this wrong message; the tightened
`match=` correctly fails against it. I then reverted the mutation:

```
$ git checkout -- src/coherence/register/register.py
$ git diff --stat src/coherence/register/register.py
(no output -- empty diff, register.py unchanged from before the sanity check)
```

### Verification with the real code

```
$ rtk proxy uv run pytest tests/unit/requirements/test_acceptance.py -q
..................                                                       [100%]
18 passed in 0.95s
```

18/18 passing, pristine output.

Full covering suite, re-run once before committing:

```
$ rtk proxy uv run pytest tests/unit/requirements/ tests/unit/coherence/ -q
...
689 passed, 27 warnings in 29.01s
```

Same result as before the fix (689 passed; the 27 warnings are the same
pre-existing, unrelated `factory.*` shim `DeprecationWarning`s noted in the
original report). No functional code changed in this fix -- only the test
file's assertions.

### Files changed (this fix)

- `tests/unit/requirements/test_acceptance.py` — tightened all 13
  malformed-case `match=` assertions to the specific failure reason.
- `src/coherence/register/register.py` — untouched (verified via `git diff
  --stat` showing no changes after the sanity-check mutation was reverted).
