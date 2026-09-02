# T-5 evidence report — acceptance integrity

Worktree: `C:/coding/pi-agent-factory-wt/feat001-slice`  
Branch: `feat/feat001-slice`  
Final source/test HEAD: `44d585a5a0898ed52b8aa296b387cac3c948120b`

This report is under the ignored `.superpowers/` tree and is intentionally not
committed. T-5's S-5 implementation scope is:

- the 11 T-3-named unit-test files, with decorators only;
- `src/coherence/policy/compiler.py`;
- `tests/unit/coherence/policy/test_compiler.py`.

The separate `989134a` reference-run documentation commit is adjacent
controller-owned evidence, not T-5 implementation, and is excluded from the
implementation-scope review. The final hardening commit changed only the two
source/test paths listed below.

## TDD evidence

### RED — before the production fix

At baseline `676e743338a9ce5f4a9562320a00d29099fae892`, after adding the focused
regressions and before changing `compiler.py`:

```text
$ uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts='' -k 'parent_component_inside_root or current_drive_rooted_ref_inside_root or duplicate_profiles_are_ambiguous_and_blocking'
FFFF                                                                     [100%]
...
4 failed, 29 deselected in 1.76s
```

The failures were the expected missing behaviors: the parent component and
current-drive rooted ref were accepted when their canonical targets remained
under the root, and both declaration orders selected a profile instead of
producing ambiguous obligations.

### GREEN — focused final run

```text
$ uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts=''
............................s....                                        [100%]
32 passed, 1 skipped in 37.21s
```

The one skip is the existing symlink-specific regression on this Windows host.
The focused warning guard also passed after the junction test switched to binary
subprocess capture and replacement decoding:

```text
$ uv run pytest tests/unit/coherence/policy/test_compiler.py -q -o addopts='' -W error::pytest.PytestUnhandledThreadExceptionWarning
............................s....                                        [100%]
32 passed, 1 skipped in 2.90s
```

## Implemented fixes

- Acceptance refs reject lexical `..` components before canonical resolution,
  even when normalization would remain inside the root.
- Acceptance refs reject POSIX absolute paths, Windows absolute paths, UNC
  paths, drive-relative paths, and current-drive rooted/anchored Windows paths
  using both native and Windows lexical path semantics. Canonical containment
  remains enforced after these checks.
- Duplicate SR declarations are detected from the list-valued trace/register
  views before profile resolution or ID-keyed register lookup. Mixed
  `high_assurance`/`prototype` duplicates return exactly four open, blocking
  obligations (`ci_verification`, `verification_result`, `human_review`, and
  `test_marker`) with `source_policy="ambiguous"`, independently of file order.
- Legacy binding-first marker behavior and the existing duplicate-marker
  regression remain covered by the focused suite.
- The junction regression no longer starts a reader thread that decodes
  Windows `cmd` output as UTF-8; the focused warning guard confirms no new
  `PytestUnhandledThreadExceptionWarning`.

## Required checks at final source/test HEAD

### Lint

```text
$ uv run ruff check src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py
exit 0; no diagnostics
```

### Typecheck

```text
$ uv run pyright src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py
0 errors, 0 warnings, 0 informations
```

### Full unit suite — authoritative command used

The command run and cited here is exactly `tests/unit` with pytest addopts
cleared. The separate `uv run pytest -m unit -q -o addopts=''` command was not
used or cited.

```text
$ uv run pytest tests/unit -q -o addopts=''
=========================== short test summary info ===========================
FAILED tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser
1 failed, 2915 passed, 13 skipped, 114 warnings in 475.94s (0:07:55)
```

The sole failure is the known pre-existing
`tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser`.
It is outside the allowed paths and was not changed. The final 114-warning
count is the exact count from this rerun; the junction decoding warning is not
present. The remaining `PytestUnhandledThreadExceptionWarning` is the
pre-existing warning from
`tests/unit/orchestrator/test_config_gate_runner.py::test_python_placeholder_is_quoted_when_the_interpreter_path_has_a_space`.

### Diff and status

```text
$ git diff --check -- src/coherence/policy/compiler.py tests/unit/coherence/policy/test_compiler.py
exit 0

$ git status --short --untracked-files=all
(no output)
```

The report remains ignored and uncommitted; scoped commit staging contained only
the two source/test paths listed above.

## Commit

`44d585a5a0898ed52b8aa296b387cac3c948120b`  
`fix: harden T-5 acceptance integrity`
