# Controlled Pi host integration for pi-agent-factory

**Status:** design
**Date:** 2026-08-23
**Scope:** distribution and host integration
**Relationship:** standalone companion to the Coherence designs; it does not amend
`2026-08-22-coherence-progressive-assurance-design.md`.

## 1. Decision summary

The product should be able to run as a controlled Pi package/extension, while retaining the
Python factory and Coherence core. This design does **not** decide whether the product is open
source, commercially distributed or publicly listed. The package is a **Pi host adapter**, not
a second factory implementation and not a sandbox.

The supported long-term shape is two coordinated artifacts:

1. an npm Pi package containing the `factory-watch` extension, package-owned skills and
   the resources needed to launch factory workers; and
2. an installable Python distribution containing the `factory`, `coherence` and
   `substrate` packages, schemas and stable CLI entry points.

The first implementation is for controlled internal use or trusted collaborators through a
local path, private Git source or private tarball. There is no public npm/Pi registry release
at this stage. It may preserve source-checkout compatibility, but it must not call an
installed package standalone until its Python backend resolver has been proved in a clean
project. A missing or ambiguous backend is an actionable error, never a silent source-tree
fallback.

This is an orthogonal host-integration track. Coherence increments remain responsible for
Coherence semantics and their canonical JSON contracts. The controlled package consumes those
contracts when available; it does not add an obligation kind, reimplement status, change
lifecycle semantics, or become a new Coherence increment.

## 2. Why this is worth doing

The current `pi-ext/factory-watch/package.json` is private, has no `pi` manifest, and keeps
Pi runtime imports in development dependencies. Maintainers therefore need a repository
checkout and local tooling. A controlled Pi package can provide reproducible installation,
project/global scope, update and rollback semantics without committing us to public
publication or community distribution.

The earlier proposal is directionally right but overclaims three things:

- an npm package is not automatically sandboxed or signed; Pi explicitly warns that package
  extensions execute with full system access;
- bundling a Python interpreter is not the first adoption step and would create platform,
  update and supply-chain complexity; and
- global availability is not the same as safe automatic startup mutation.

## 3. Goals

- Make the interactive factory surface loadable through Pi's package mechanism for
  maintainers and explicitly authorized users.
- Preserve current commands, tools, UI surfaces and Python ownership.
- Support clean-project execution outside the factory source checkout.
- Define an explicit Python/core runtime contract and diagnostic path.
- Resolve package-owned resources from the installed package and project-owned state from
  `ctx.cwd`, with no checkout-relative guessing.
- Keep child-agent write/shell enforcement explicit and fail-closed.
- Make startup inert: loading the package registers capabilities but does not unexpectedly
  spawn Python, start servers, refresh indexes or write project files.
- Provide clean-room tests for package loading, resource resolution, runtime resolution,
  security separation and representative end-to-end commands.
- Retain source-checkout development and the existing installer until the controlled package
  path is proven and documented.
- Keep public publication, licensing and community distribution as explicit future decisions.

## 4. Non-goals

- Rewriting the Python core in TypeScript, Rust or WASM.
- Bundling a Python interpreter or virtual environment in the package in the first
  controlled release.
- Publishing to the public npm/Pi package ecosystem or package gallery at this stage.
- Deciding open-source versus proprietary licensing or public source visibility.
- Moving tasks, sessions, evidence, simulations, `.factory` state or Coherence stores into
  the package.
- Making npm/package metadata part of the progressive-assurance obligation model.
- Reopening shipped Coherence increments 0–3 or changing the meaning of increments 4–8.
- Reimplementing Python status, obligations, routing, evidence or lifecycle logic in the
  extension.
- Auto-loading `scope-guard` in a user's normal interactive session.
- Bundling the generic `permission-gate` as an implicit policy override for all users.
- Starting a background daemon, telemetry service or remote coordination service.
- Claiming universal Pi-version, shell, OS or terminal compatibility without a tested matrix.

## 5. Runtime topology

### 5.1 Interactive parent

Pi loads the controlled `factory-watch` extension from a local path, private Git source or
private tarball. It registers commands, tools and UI handlers. It resolves the target
repository from the current Pi context (`ctx.cwd`) and invokes the Python backend through a
validated runtime configuration.

The extension is allowed to use Python subprocesses when a command or tool needs them, but
module load and ordinary `session_start` must not perform backend work or mutate the target.
Any session-scoped server, watcher or timer starts only when a feature needs it and is
closed on `session_shutdown`.

### 5.2 Python backend

The Python wheel owns factory and Coherence semantics, schemas, record stores, serializers,
gates and CLI behavior. It runs with the target project as the state root even when its
installed package resources live elsewhere. Package data is resolved using Python package
resources rather than a source-checkout parent walk.

The supported interpreter resolution order must be explicit and testable. The design should
prefer a configured target command (for example `PI_FACTORY_PYTHON` or a project setting),
then a documented `uv`/project environment, and otherwise fail with a diagnostic naming the
missing executable or Python package. It must never silently invoke an unrelated global
Python or treat the npm package directory as the target project.

Every Python invocation must use this one resolver, including code-context injection,
evidence, coverage, system/navigation, trace, factory-init, polish and child-launch paths.
There must be no caller-specific bare `python`/`uv` fallback that swallows an error. The
release target includes a wheel/install-layout path; source-checkout compatibility is an
additional development mode, not a substitute for proving the installed backend.

### 5.3 Child workers

`factory-watch` and `scope-guard` have different jobs:

- `factory-watch` is the interactive host adapter and may be loaded in the parent.
- `scope-guard` is a child-agent policy extension. It is loaded only by an explicit worker
  launch profile, with validated `PI_SCOPE_ALLOW` and `PI_SCOPE_BASH` values.

The child launcher must preserve the guard's fail-closed behavior and its load-order
invariant. The canonical launch contract is `--no-extensions` followed by an explicit,
validated worker extension list containing the guard and only the extensions the worker
needs; both the TypeScript subagent launcher and Python orchestrator/coverage/polish launch
paths must use or prove this contract. A later `tool_call` handler must not be able to mutate
an approved path or command without the launcher detecting the violation. The parent session
must remain usable when worker policy variables are absent.

## 6. Package contract

The controlled package may expose a manifest equivalent to:

```json
{
  "name": "@factory/pi-agent-factory-internal",
  "private": true,
  "pi": {
    "extensions": ["./extensions/factory-watch.ts"],
    "skills": ["./skills"]
  }
}
```

The final private package name and versioning policy are release decisions, but the
controlled package must:

- declare the Pi core modules it imports as compatible peer dependencies, according to Pi's
  package rules;
- put non-Pi runtime imports in production `dependencies`, not only `devDependencies`;
- choose a real shipped entrypoint (the current `src/index.ts`, a wrapper, or a deliberate
  build output); illustrative paths such as `./extensions/factory-watch.ts` are not valid
  until that file exists and its transitive imports/resources are included;
- include only package-relative resource paths in the manifest;
- exclude tests, secrets, absolute checkout paths and development-only fixtures from the
  tarball; and
- make the package's supported Pi API range and Node range visible to users.

The package may carry `scope-guard` source as a non-autoloaded worker resource, or the guard
may be a separately installed package. Either choice must leave it absent from the parent's
`pi.extensions` list and must be covered by a worker launch test.

## 7. Resource and state ownership

| Resource | Owner/resolution rule |
|---|---|
| Extension code, package skills, worker extension assets | Installed package resources |
| Project tasks, `.factory`, sessions, evidence, simulations, git state | Target `ctx.cwd` |
| Python schemas and immutable runtime data | Python package resources |
| Project-local `.pi/skills` and settings | Target project, subject to Pi trust and `ctx.isProjectTrusted()` |
| Temporary run/session files | Existing factory session/run contracts |

`factory-path.ts`, `factory-skills.ts`, `substrate.paths` and child launchers must stop using
an assumed source-checkout depth for installed execution. Development checkout behavior may
remain as a compatibility path, but it must be explicit, observable and lower priority than
configured package/backend paths. Direct reads of project-local skills/settings must honor
Pi's project-trust decision rather than bypassing it.

## 8. Coherence integration boundary

This track does not amend the progressive-assurance design. Its compatibility obligations
are limited to consuming canonical surfaces owned by the relevant Coherence work:

- Increment 5's status/focus/dispatcher work remains the owner of status semantics and
  deterministic routing; the package only adapts the host UI and commands.
- Increment 7 remains the owner of the unified long-run/mission-control protocol and Pi
  mission-control integration; the package does not create a parallel serializer or store.
- `serialize_run_statuses()` and other declared JSON contracts are authoritative. The
  extension must preserve null/absent distinctions, freshness/error states and display-only
  resolver commands.
- Package tests may validate transport compatibility, but they do not introduce new
  obligations, profiles, test markers or lifecycle relationships.

Basic package work may proceed as an auxiliary track after the substrate/resource contracts
needed by Increments 1B/1C are stable. For this plan, “stable” means the resource/path API,
package-data fixture and outside-checkout import test have an owner-approved green gate.
Full claims about the packaged mission-control surface wait for Increment 7. This dependency
is recorded here rather than by modifying the Coherence increment map.

## 9. Security and trust

Pi packages execute arbitrary code with the user's permissions. Installation, global scope,
project trust and package updates are trust decisions, not a sandbox boundary. Documentation
must say this plainly.

The package must not silently install or enable unrelated global policy. `permission-gate`
is a user-controlled safety extension. `scope-guard` is a factory worker policy. Their
presence, ordering and scope must be explicit. Noninteractive worker execution denies by
default when policy cannot be established. The path policy must also define symlink handling:
lexical allowlist matches are insufficient if an allowed path resolves outside the target;
realpath/parent-containment behavior, including nonexistent write targets, must be tested.

No extension path, backend command, project root or resolver command may be accepted from
unvalidated free-form model output. Displayed `resolve_cmd` values remain display-only unless
an existing, separately authorized factory protocol executes them.

## 10. Acceptance contract

A controlled release candidate is acceptable only when all of the following are demonstrated.
This is not authorization to publish publicly:

1. `npm pack --dry-run` contains the manifest, extension entrypoint, declared skills and
   worker resources, with no accidental checkout paths or secrets.
2. A clean temporary Pi installation loads the package globally and project-locally, and
   project trust refusal/approval and global/project precedence behave as documented.
3. Production-only npm installation succeeds; the extension does not rely on dev dependencies.
4. Starting Pi outside the factory checkout registers the expected commands/tools without
   spawning Python, starting servers, or writing project files. The same no-side-effect
   assertion applies to `session_start`, reload and the first `before_agent_start`; automatic
   code-context indexing is opt-in or requires an explicitly initialized/consented project.
   Session shutdown may persist its existing session-memory record, and that exception is
   documented and tested.
5. A configured Python backend runs representative factory and Coherence commands against
   the temporary target project; missing/invalid backend states produce deterministic,
   actionable diagnostics.
6. Package skills and target-local skills resolve without accidental duplication or shadowing.
7. Child-agent tests prove `scope-guard` is not loaded in the parent, denies empty/unset
   policy, preserves path/shell allowlists, and cannot be bypassed by a later handler. The
   manifest or separate-guard artifact records which worker-resource choice was made.
8. Windows and POSIX smoke tests cover spaces in package/project paths, symlink escapes,
   trust refusal/approval, and both source-checkout and installed layouts.
9. Existing extension typecheck/unit gates and relevant Python gates remain green. The
   retained `scripts/install-pif.sh` path remains green until the package path is formally
   declared the replacement.
10. Package adapter fixtures preserve canonical Coherence null/absent distinctions,
    freshness/error states and display-only resolver-command fields without re-deriving them;
    mission-control fixtures are enabled only once Increment 7 owns that contract.
11. Documentation provides install, update, rollback, backend setup, trust and supported
    version guidance.

## 11. Deferred decisions

- Whether the product is open source, source-available or proprietary, including licensing
  and source-visibility decisions.
- Public npm/Pi registry, package-gallery or community distribution workflow.
- The final private package name and external versioning policy.
- Whether the Python artifact is published to PyPI, installed with `uv tool`, or configured
  as a project dependency first.
- Whether `scope-guard` is a non-autoloaded resource in the main package or a separate package;
  the implementation plan must resolve this before any wider distribution.
- Automatic release signing and provenance attestations.
- A bundled native executable or interpreter.
- Full compatibility with every Pi release and every shell/platform combination.
