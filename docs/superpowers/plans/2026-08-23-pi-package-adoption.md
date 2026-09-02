# Pi package adoption implementation plan

> **For agentic workers:** execute this plan only after the design spec has been reviewed. Use
> focused subagents for independent fixture/research work, but preserve the ownership rules
> below. Every implementation task ends with its listed tests and a reviewable commit.

**Design spec:** `docs/superpowers/specs/2026-08-23-pi-package-adoption-design.md`

**Goal:** Make the interactive `factory-watch` surface installable as a Pi package while
retaining the Python factory/Coherence core, preserving source-checkout development, and
proving installed-layout behavior in clean projects.

**Architecture:** A controlled/private Pi package is a thin host adapter. Python remains authoritative
for factory and Coherence semantics. The package resolves package resources separately from
target-project state and invokes a configured Python backend. `scope-guard` remains an
explicit child-worker policy, never a normal parent-session autoload.

**Track position:** This is a standalone distribution track, not a new Coherence increment.
The implementation may prepare controlled-package seams after the substrate/resource contracts needed
by Increments 1B/1C are stable. For this plan, that readiness means the resource/path API,
package-data fixture and outside-checkout import test have an owner-approved green gate.
Increment 5 and Increment 7 are compatibility consumers; this plan does not edit their plans
or the progressive-assurance design. Full mission-control package claims wait for Increment 7.

## Global constraints

- Python support remains 3.11–3.12; Node/Pi support is documented and tested rather than
  implied.
- `ctx.cwd` is the target-project root for project state. Package installation directories
  are never treated as target roots.
- No module-load or ordinary `session_start` path may spawn Python, start a server/watcher,
  refresh an index or write project files.
- Missing or ambiguous Python/backend configuration fails with an actionable diagnostic.
  Never silently fall back to arbitrary global Python or a checkout discovered by parent-walk.
- `factory-watch` may load in the parent; `scope-guard` may load only in an explicit worker
  profile. `permission-gate` is not silently bundled as a factory policy.
- Canonical Python JSON/status/obligation contracts are consumed, not re-derived in TypeScript.
- Do not modify shipped Coherence increment implementation files or reopen their semantics.
- Do not use `git add -A`; preserve unrelated worktree changes.
- Each task records changed files and leaves its own typecheck/test gate green.

## Ownership and coordination

| Area | Owner in this plan | Boundary |
|---|---|---|
| Pi package metadata, tarball fixtures, package README | Adoption track | One worker owns `pi-ext/factory-watch/package.json` and lockfiles at a time |
| Package/backend resource resolution | Adoption track with existing module owners | Preserve existing adapters and source-checkout compatibility |
| Python schemas/resources | Python substrate owner | Use package resources; do not move project state |
| `scope-guard` policy semantics | Existing scope-guard owner | Adoption work only makes installed worker resolution explicit |
| Coherence semantics and serializers | Coherence increment owners | Adoption tests consume contracts; no duplicate implementation |
| Mission-control integration | Increment 7 | Package track adds compatibility fixtures only after its contract exists |

## Task 1: Inventory and prove the topology

**Depends on:** design review only.

**Files:**
- Read: `pi-ext/factory-watch/src/index.ts`, `factory-path.ts`, `factory-skills.ts`,
  `process-control.ts`, `subagent-tool.ts`, `factory-init-command.ts`.
- Read: `pi-ext/factory-watch/src/code-context-inject.ts`, `evidence-client.ts`,
  `coverage-run-command.ts`, `system-cli.ts`, `system-worker.ts`, `trace-cli.ts`,
  `cli-runner.ts` and polish command paths; enumerate every Python spawn rather than assuming
  `process-control.ts` is the only caller.
- Read: `src/substrate/paths.py`, `src/substrate/agents/backend.py`, `pyproject.toml`,
  `pi-ext/scope-guard/README.md`.
- Create: `pi-ext/factory-watch/test/package-topology.test.ts` or an equivalent fixture file.
- Modify: package-specific README only if needed to record the proven topology.

**Steps:**

1. Enumerate every package-owned resource, every `process.cwd()`/parent-walk assumption,
   every Python subprocess command, every session-start side effect and every child extension
   path.
2. Build a temporary fixture project outside the checkout and a fixture installed-package
   layout. The fixture must be able to detect accidental reads/writes against the package
   directory.
3. Make the separately installed Python wheel/install layout the release target. Source-checkout
   backend support remains a compatibility mode. Record the configured-interpreter precedence
   in the test and README; do not hide an unresolved choice in implementation code.
4. Add failing tests for the two root domains: package resources resolve from the package;
   project state resolves from fixture `ctx.cwd`, with no source-tree fallback. Add an inventory
   assertion that every Python caller will use the shared resolver.

**Acceptance:** the topology inventory names all current assumptions; the fixture proves the
selected layout; no production behavior is changed by this task; unresolved backend choices
are recorded as explicit failures, not guessed defaults.

## Task 2: Make Python resources and backend invocation install-safe

**Depends on:** Task 1 and an owner-approved green readiness gate for the substrate/resource
contracts from Increment 1B/1C: resource/path API, package-data fixture and outside-checkout
import test.

**Files:**
- Modify: `src/substrate/paths.py` and relevant package-resource modules.
- Modify: `pyproject.toml` and package-data configuration.
- Modify: Python CLI entrypoint modules and/or a new backend resolver module.
- Test: `tests/substrate/` and relevant `tests/factory/` fixtures.
- Modify: `pi-ext/factory-watch/src/process-control.ts` or a focused backend client module.
- Test: `pi-ext/factory-watch/test/` backend-resolution tests.

**Steps:**

1. Move schemas and immutable runtime assets to explicit Python package resources where they
   are currently found through a source checkout. Preserve import compatibility.
2. Define the backend contract: configured `PI_FACTORY_PYTHON`/project setting, documented
   `uv` project environment, and deterministic failure output. Validate executable and module
   availability before running a command; do not fall through to bare global `python`.
3. Route every Python invocation through the shared resolver, including code-context injection,
   evidence, coverage, system/navigation, trace, factory-init, polish and child-launch paths.
   A caller-specific swallowed failure or implicit `uv` fallback is a test failure.
4. Separate command cwd (the target project) from Python project/package location. Preserve
   JSON stdout/stderr and exit-status behavior expected by existing callers.
5. Keep optional code-index behavior explicit: an unavailable or ABI-incompatible accelerator
   selects the documented stdlib fallback rather than making packaging appear broken.
6. Add tests that run the Python modules outside the source checkout with target state in a
   temporary directory, including paths containing spaces.

**Acceptance:** a wheel/install-layout fixture resolves schemas and CLI modules outside the
checkout; target artifacts land only under the target project; missing Python, missing factory
module, invalid configuration and ambiguous backend selection each produce distinct actionable
diagnostics; source-checkout mode remains green; no arbitrary global interpreter fallback
exists.

## Task 3: Convert `factory-watch` into a valid Pi package

**Depends on:** Task 1; Task 2's backend contract may be stubbed by a deterministic fixture.

**Files:**
- Modify: `pi-ext/factory-watch/package.json`.
- Create/modify: package entrypoint/resource directories (for example
  `pi-ext/factory-watch/extensions/`, `skills/`, and worker-resource paths).
- Modify: `pi-ext/factory-watch/tsconfig.json` and package lock only if required.
- Test: `pi-ext/factory-watch/test/package-manifest.test.ts`.
- Create/modify: package-specific README/install documentation.

**Steps:**

1. Select and record a private package identity/version policy for controlled local, private
   Git or private tarball use. Keep the package private; public naming, licensing and registry
   publication remain deferred.
2. Choose a real shipped entrypoint: either ship the current `src/index.ts` source tree,
   add a wrapper that points to it, or add a deliberate build output. Do not use an illustrative
   `./extensions/factory-watch.ts` path unless that file and all transitive imports exist.
3. Add a `pi` manifest whose paths stay within the package. Do not add gallery/discovery
   metadata such as `keywords: ["pi-package"]` until public distribution is approved. Point Pi
   at the chosen entrypoint and the intentionally selected skill set.
4. Classify Pi core imports as peer dependencies according to Pi's package rules. Move every
   non-Pi runtime import into production dependencies; keep test/type tooling in dev
   dependencies. If `scope-guard` is included, its runtime `minimatch` dependency is production.
5. Resolve and record the worker-resource choice: bundled but non-autoloaded guard, or separate
   guard package. Add a manifest assertion for the selected choice.
6. Verify `npm pack --dry-run` contents and reject absolute paths, secrets, tests and accidental
   checkout-only files.

**Acceptance:** the manifest parses; all declared resource paths exist; production-only
installation loads the extension; package contents are minimal and reviewable; the parent
loads `factory-watch` exactly once and does not load `scope-guard`.

## Task 4: Replace checkout-relative resource and child-launch assumptions

**Depends on:** Tasks 2 and 3.

**Files:**
- Modify: `pi-ext/factory-watch/src/factory-path.ts`.
- Modify: `pi-ext/factory-watch/src/factory-skills.ts`.
- Modify: `pi-ext/factory-watch/src/subagent-tool.ts` and child command builders.
- Modify: `src/factory/orchestrator/pi_backend.py` and `src/factory/orchestrator/__main__.py`
  only where explicit worker-resource configuration is needed.
- Test: `pi-ext/factory-watch/test/factory-path.test.ts`, `factory-skills.test.ts`,
  `subagent-tool.test.ts` and Python child-launch fixtures.

**Steps:**

1. Define separate resolvers for package resources, target project root and configured Python
   backend. Use `import.meta.url`/package resources for installed assets and `ctx.cwd` for
   project data.
2. Make target-local `.pi/skills` precedence and package-owned skills deterministic, with no
   duplicate loading; direct target-local reads must honor `ctx.isProjectTrusted()`.
3. Define one canonical child launch contract: `--no-extensions` followed by an explicit,
   validated worker extension list. Apply and test it in the TypeScript subagent launcher and
   Python orchestrator/coverage/polish launch paths. Preserve project root cwd, context files,
   recursion guard and `PI_SCOPE_*` values.
4. Remove or quarantine source-tree parent walking for installed execution. Keep it only as
   an observable development compatibility path.
5. Define symlink policy using realpath/parent containment, including nonexistent write targets;
   lexical glob approval alone must not allow an escape outside the target.
6. Add installed-layout tests for Windows/POSIX separators, spaces, absolute paths outside the
   project, symlink escapes and missing worker assets.

**Acceptance:** installed and checkout layouts resolve the same intended assets; no child
launch can silently omit the guard; worker policy remains fail-closed; parent functionality is
not blocked by unset worker variables; path traversal/outside-root cases are denied.

## Task 5: Make startup and runtime diagnostics inert and explicit

**Depends on:** Tasks 3 and 4.

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` and `factory-init-command.ts` as needed.
- Modify: `pi-ext/factory-watch/src/docs-server.ts`/resource lifecycle modules if needed.
- Test: startup/reload/shutdown tests in `pi-ext/factory-watch/test/`.
- Modify: package README and troubleshooting documentation.

**Steps:**

1. Audit module load, `session_start`, reload and the first `before_agent_start`. Defer Python,
   server, watcher and index work until an explicit command/tool needs it. In particular,
   remove or make opt-in the current startup index refresh/alignment and ordinary-prompt code
   context spawn for packaged mode.
2. Add process and filesystem sentinels proving module load, startup, reload and first prompt
   perform no backend spawn or project write. Document the existing session-shutdown memory
   persistence as the one allowed lifecycle write and test it separately.
3. Add a preflight/diagnostic path for backend absence, incompatible Pi host APIs and missing
   project initialization. The error must identify the remedy and preserve machine-readable
   failure shape where callers already use JSON.
4. Verify `/factory`, `/factory-init`, `/system`, `/task` and representative `eng_*` tools
   resolve `ctx.cwd` and do not inspect the package directory as a project.
5. Ensure every resource started after startup has an idempotent `session_shutdown` cleanup.
6. Document global versus project installation, trust, update, rollback, Python setup and the
   fact that package code is not sandboxed.

**Acceptance:** loading/reloading the package performs no unsolicited writes or subprocesses;
missing-runtime behavior is deterministic; explicit commands still work; shutdown leaves no
process/timer leak; documentation matches observed behavior.

## Task 6: Build the clean-room adoption and security suite

**Depends on:** Tasks 1–5.

**Files:**
- Create: `tests/package-adoption/` fixtures/scripts, or the repository's established package
  fixture location.
- Modify: `pi-ext/factory-watch/test/` and `pi-ext/scope-guard/test/` only for integration
  coverage, not policy redesign.
- Modify: `scripts/gates/` only if an existing gate owner approves a package smoke hook.

**Steps:**

1. Pack the npm artifact and install it into an isolated temporary global Pi home
   (`PI_CODING_AGENT_DIR` or equivalent) and a temporary project-local `.pi` home. Do not
   touch the developer's real settings, trust store, sessions or package cache.
2. Install the Python wheel in clean Python 3.11 and 3.12 fixtures; also exercise source-checkout
   compatibility separately so a failed clean-room test cannot be masked by repository imports.
3. Exercise global/project package precedence, `autoload: false`, trust refusal/approval,
   reload, package skill loading and a representative Python-backed command outside the
   checkout. Verify a minimal project with no `pyproject.toml`, no checkout ancestry and no
   local `node_modules` fails clearly rather than falling back.
4. Prove the security separation: parent `factory-watch` loads; parent `scope-guard` does not;
   both TS and Python child launchers use the explicit extension list; child unset/empty policy
   denies; allowed paths/shell work; a later handler mutation is rejected or the launch
   invariant fails visibly.
5. Add canonical Coherence transport fixtures for null/absent fields, freshness/error states
   and display-only resolver commands. Enable mission-control fixtures only after Increment 7
   owns that protocol; package tests must compare serialized fields, not re-derive them.
6. Run Windows and POSIX variants, including paths with spaces, shell metacharacters, symlink
   escapes and traversal cases supported by the platform.

**Acceptance:** the clean-room matrix passes with no hidden checkout dependency, no global
settings mutation, no package-side duplicate resource, and no bypassable child guard. Failures
identify package, backend, resource, host, platform or policy categories separately.

## Task 7: Release and compatibility handoff

**Depends on:** Task 6 and the relevant Coherence consumer contracts.

**Files:**
- Modify: package-specific README/release documentation.
- Create: package changelog/release checklist if the project has no existing equivalent.
- Do not modify: `2026-08-22-coherence-progressive-assurance-design.md`, shipped increment plans,
  or Coherence obligation/status implementation solely for packaging.

**Steps:**

1. Record the supported Pi, Node, Python, `uv`, shell and OS matrix and the exact clean-room
   commands used to verify it.
2. Document one install path, one update path, one rollback path and explicit backend setup.
3. Retain and regression-test `scripts/install-pif.sh` until the package path is formally
   declared its replacement; document both paths during the transition.
4. State that Increment 5 owns status/focus semantics and Increment 7 owns mission-control
   integration; package compatibility tests consume those contracts after they land.
5. Run the full existing extension gate, relevant Python gates and package clean-room suite.
6. Review the final diff for changed-file ownership and confirm no shipped Coherence increment
   was implicitly reopened.

**Acceptance:** an authorized maintainer or collaborator can install/remove the controlled
artifact through the documented local, private Git or private tarball path, understand the
Python prerequisite and trust model, and recover from a bad update. No public registry or
community distribution path is created by this plan. The review records the exact artifact
versions, tested hosts and changed files.

## Verification checklist

- [ ] Design spec reviewed and separate from progressive-assurance semantics.
- [ ] Python package resources work outside the checkout.
- [ ] Pi manifest and production dependencies are valid.
- [ ] Package resource paths and target state paths are distinct.
- [ ] Startup is inert and shutdown is clean.
- [ ] `scope-guard` is worker-only and fail-closed.
- [ ] Clean-room global/project installs pass without modifying real settings.
- [ ] Isolated package homes cover trust and global/project precedence.
- [ ] Source-checkout compatibility remains green.
- [ ] Existing installer remains green during transition.
- [ ] Increment 5/7 contracts are consumed, not reimplemented.
- [ ] Documentation covers install, backend, trust, update and rollback.
