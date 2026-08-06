# Design: `factory init` — Project Onboarding

Date: 2026-08-06
Status: Approved (brainstorming) — ready for implementation planning
Builds on:
- `2026-08-06-requirement-doctor-design.md` §10 — deferred `factory init` and named
  its three parts: a default config, an interview for project specificities, and
  an extension task that becomes the project's first development work
- `2026-08-05-project-configurable-gates-design.md` — the project-declares-its-own
  seam, and the "no fallback, one code path" rule applied here to extensions
- `2026-08-05-drone-factory-separation-design.md` §3.5, §7 — the factory is the
  base and a project is a plug; making the drone repo a first-class target was
  deferred to exactly this spec

## 1. Problem

The factory can run against another repository, but nothing helps a repository
become a target. Everything a project must declare is hand-authored, and most of
what the factory offers is invisible from outside the factory's own checkout.

Measured on 2026-08-06:

| | state |
|---|---|
| `cool_physical_ai_project/.factory/factory.yaml` | hand-written by a human, comments and all |
| `cool_physical_ai_project/.pi/` | empty |
| harness types a project may name | 2, both factory-side (`sim-testbench`, `playwright-e2e`) |
| project extension points | 1 bespoke key per subsystem (`harnesses.*.scorers`) |
| `pif` run from another repo | `cd`s into the factory checkout |
| factory skills visible from another repo | 0 of 14 |
| commands registered by `factory-watch` | 10 — `doctor` is not one |

Two failures follow, and they compound.

**A project cannot describe how its own requirements get verified.** `_build`
(`config.py:31`) resolves `type:` against a factory-side map, so any project whose
verification is neither a recorded-trace sim nor a Playwright suite raises
`UnknownTypeError` permanently. The scorer seam solved this one level down —
a project owns its metrics — but the apparatus that runs them is still the
factory's to enumerate. This is the piece that genuinely differs per project.

**The factory is not discoverable from the repo it is meant to serve.** The
symptom raised was the doctor: its skill exists at `.pi/skills/doctor/SKILL.md`
and its CLI at `factory doctor`, and neither is reachable from a target repo.
§8 shows the doctor is not special — it is the case where nothing else papered
over the defect.

### 1.1 Why this is init's problem and not a separate cleanup

Init is *the onboarding command for another repository*. Shipping it while `pif`
still relocates the session into the factory would be shipping a door with no
room behind it. §8 is a prerequisite in the same sense that gate resolution was a
prerequisite of the repo split, not follow-on tidying.

## 2. Decisions locked during brainstorming

1. **Init is an onboarding surface, not a scaffolder.** It writes exactly one
   file, `.factory/factory.yaml`. It creates no directories, authors no project
   code, and edits no `pyproject.toml`.
2. **Skill drives, CLI writes.** The doctor's split, unchanged. See §3.
3. **One extension-registration point.** A project names one module that
   registers harness types, playground types, scorers and skill directories.
   `harnesses.*.scorers` is deleted, not deprecated. See §5.
4. **`validation:` records only what cannot be derived.** A non-empty register is
   the active state; the key exists solely to distinguish an empty register that
   is deliberate from one that is owed. See §6.
5. **Init does not choose a harness for a greenfield project.** A measuring
   apparatus cannot be picked before there is something to measure. See §7.
6. **The doctor is retrofit; greenfield specification is a separate workflow.**
   `/specify` is spec #2 and is not designed here. See §7.1.
7. **A registered skill directory is added to the search path, never substituted
   for it.** `paths.py` exists because deriving skills from the target repo caused
   three separate silent failures. See §5.3.

## 3. What init is

A skill and a CLI, split on the line this codebase has already drawn: code owns
work that is mechanical and fails silently; everything that shapes what the agent
can perceive or express belongs to the agent.

| CLI owns | Skill owns |
|---|---|
| Report PIF's registered capabilities | Which gates this project needs |
| Report raw repo facts | What each gate command actually is |
| Resolve a `type:` against built-ins + project registrations | Whether a built-in harness fits |
| Construct and write YAML | Whether this project wants system validation at all |
| Verify the extensions module imports and report what it registered | When onboarding is finished |

`factory init context` reports. It does not rank, filter, score or recommend.
The reasoning is `propose.py:97-100`'s, applied to repo facts rather than trace
gaps: a heuristic that decided which facts reach the agent caps what the agent
can notice, and a repo shape nobody anticipated is exactly the case onboarding
must survive.

The skill is `init`, vendored at `.pi/skills/init/SKILL.md`, and it is
discoverable from any repo by §8.2.

## 4. `factory init context`

One report, two halves.

**What PIF offers**

- The gate vocabulary: `unit`, `sim`, `integration`, `full`, and which node runs
  each.
- Built-in harness types and built-in playground types, with their required
  params.
- The registry slots a project may extend (§5).
- The `role -> skills` map, and every vendored skill with its description.
- The pi extensions (`scope-guard`, `factory-watch`) and the commands they
  register.
- **Which factory CLIs this repo can actually invoke.** `factory doctor`,
  `trace`, `requirements`, `polish`, `validation` are `python -m factory.*`
  against the *factory's* interpreter; from another repo they exist only if the
  factory is importable there. A skill that tells the agent to run
  `factory doctor context` in a repo where it is not installed fails at the worst
  possible moment, so init states the fact up front rather than discovering it
  mid-conversation.

**What this repo has**

- The parsed `.factory/factory.yaml`, key by key, including unrecognised keys.
- Requirement count, task count.
- Whether the declared `extensions:` module imports, and what it registered.
- Skill-name collisions between the factory's skills and the repo's (§8.4).
- Raw build facts: whether `pyproject.toml` exists and which pytest markers it
  declares; `package.json` scripts; `Makefile` targets; the presence of
  `.venv/`, `uv.lock`, `node_modules/`.

Build facts are reported as facts. Init never concludes "this is a pytest
project" — that inference, and the gate command that follows from it, is the
agent's.

`--json` mirrors `doctor context`.

## 5. The extension registry

The seam this spec exists to create.

```yaml
# .factory/factory.yaml
extensions: myproj.factory_ext
```

```python
# src/myproj/factory_ext.py
def register(r: Registry) -> None:
    r.harness("my-bench", MyBench.from_config)
    r.playground("my-sandbox", MySandbox.from_config)
    r.scorers({"latency_p95": score_latency})
    r.skills(Path(__file__).parent / "skills")
```

### 5.1 Resolution

The module name is resolved against the target repo's `src/` by the same
`sys.path` insert-import-remove mechanism `load_scorers`
(`validation/scorer_registry.py`) already uses and documents. Importing target
repo code is the trust posture the gate steps already carry.

`load_config` seeds a `Registry` with the built-ins, then applies the project's
`register()`. `_build` resolves `type:` against the merged map. `UnknownTypeError`
names both sets, so "you meant a built-in and typo'd it" and "your module did not
register that" are distinguishable.

A module that declares `extensions:` but fails to import raises
`ExtensionModuleError` naming the import failure — the same shape as
`ScorerModuleError`, and for the same reason: a silently empty registry would
present as `UnknownTypeError` on a type the project did register.

### 5.2 `scorers:` is deleted

`harnesses.*.scorers` becomes `r.scorers({...})`. No compatibility path, per the
gates design's decision 3 verbatim: the hard-coded map is deleted and the factory
uses the same mechanism it offers everyone else, one code path, dogfooded by its
author. `cool_physical_ai_project/.factory/factory.yaml` is the only live user
and migrates in this spec's work; `SimTestbenchHarness.from_config` stops calling
`load_scorers` and takes its scorers from the registry.

### 5.3 `r.skills()` adds a path, it never replaces one

`paths.py` opens with the reason this rule exists: anything shipping with the
factory "must resolve from here and never from the repo being worked on.
Deriving these from the target repo has now caused three separate silent
failures." A project registering a skills directory must not be able to reinstate
that failure.

So: `factory_skills_dir()` remains the base of the search path; registered
directories are appended; `load_skill_block` searches base-first. A name present
in both is a **hard error at registration**, not a silent override and not a
warning. A project that wants different content for a role uses a different name.

This differs deliberately from pi's own loader, which warns and keeps the first
skill found (§8.4). The Python registry is ours and can be strict; pi's is not.

### 5.4 Why one point and not four keys

Each subsystem that needed extending has so far added a key. The cost is not the
keys, it is that `type:` reads differently depending on whether the type is the
factory's or the project's, and that the next subsystem adds a fifth. With a
registry, `type: my-bench` and `type: sim-testbench` are the same sentence, and
extending a new subsystem adds a `Registry` method rather than a config schema
change.

## 6. `validation:` — recording the choice without a state that can lie

The register's governing principle is that state is derived, never declared:
`binding is None` means proposed, and there is deliberately no `status:` field
that could disagree with the content (`register.py:9-11`).

Applied here, **a non-empty register is the active state**. Derivation reaches
everything except one case: an empty register, which today cannot distinguish a
project that opted out from one whose specification pass has not happened. That
single ambiguity is what the key records.

```yaml
validation: none      # deliberate: no system requirements, by choice
validation: pending   # wanted; /specify has not run yet
```

- **Required** iff `requirements/` holds no `SR-*.md`.
- **Forbidden** iff it does. `validation: none` above three requirements is
  precisely the declared-versus-content disagreement the register was designed to
  make impossible, so `load_config` raises rather than picking a winner.
- `trace status` reads it: `opted out (validation: none)` versus
  `0% -- SR pass not yet run`.

**It is not a gate.** `trace check` does not fail on `pending`. A `pending` that
never resolves is a visible fact; turning it into a failing check trains people
to write `none` to silence it, which destroys the only signal the key carries.

The same reasoning as the gates rule — "this project has no sim" and "this
project never said what to check" are different statements — reaching the
opposite conclusion about enforcement, because here the honest answer is
genuinely allowed to be "no".

## 7. Where init stops

Init writes gates, `extensions:`, `validation:`, and any harness or playground
the repo **already** has. For a greenfield project it declares no harness: the
apparatus cannot be chosen before the requirements that define what it measures
exist. That is `/specify`'s work, and `/specify` writes it by calling the same
`factory init harness` verb. One writer, two callers.

Then the skill says what is next:

- `validation: pending` -> offer `/specify` in the same session. One command,
  from the human's side.
- `validation: none` -> done. Nothing in this repo mentions requirements again.

### 7.1 Why not the doctor

The doctor is a retrofit tool. Its skill scopes itself to "a project whose specs
have moved ahead of its requirements", its step 2 is "read the specs yourself, in
full", and `mint --source <spec path>` takes a prose artifact as provenance. A
greenfield repo hands it an empty input set.

`/specify` is the greenfield sibling: an interview producing a system
specification and the testbench able to falsify it, designed together. It is
spec #2 and is not designed here. One consequence is already visible and belongs
in its spec, not this one: an SR minted from a conversation has no `source:`
file, so `/specify` either writes a system-spec document first — after which
`source:` works unchanged and the doctor becomes the tool that maintains it —
or `source:` learns a non-file value.

## 8. Prerequisite: discoverability from a target repo

Four defects. The doctor is a symptom of the second.

### 8.1 D1 — `pif` never leaves the factory

All three shims generated by `install-pif.sh` (lines 31, 40, 46) begin
`cd "$REPO_ROOT"`, documented as "always operating on this repo regardless of
which directory `pif` is invoked from". That was correct when the factory and the
drone were one repository. After the split it means **`pif` run in another repo
gives you a session in the factory checkout**, and every other defect here is
downstream of it.

The shim stays in the caller's working directory. Only `--extension` carries an
absolute path into the factory.

### 8.2 D2 — factory skills are not on pi's search path

Pi loads skills from `~/.pi/agent/skills`, `~/.agents/skills`, `<cwd>/.pi/skills`,
`.agents/skills` up to the repo root, package `skills/` directories, the
`skills` settings array, and `--skill <path>` (repeatable, additive; verified
present on the installed build). The factory's 14 skills live at
`<factory>/.pi/skills`, which is searched only when cwd is the factory.

**This is why the doctor is invisible**: nothing registers it as a command, and
its directory is never searched. The shim passes
`--skill "<factory>/.pi/skills"`. Every factory skill then reaches the system
prompt for model invocation and is available as `/skill:<name>` from any repo,
while the target repo's own `.pi/skills` continues to load on top — the
installed-package-plus-repo-extension shape, at no extra cost.

**Consequence: the doctor needs no command.** `/trace-fix`, `/polish` and `/plan`
are commands because they do work before seeding — run `trace check` and inject
its report, drive the polish orchestrator, compose two skill blocks. The doctor's
skill only instructs the agent to call `factory doctor context`. With D2 fixed it
is discoverable as authored, and registering `/doctor` would be ceremony. The
same test applies to `/init`: it seeds a skill and nothing more, so it is
`/skill:init`, not a registered command.

### 8.3 D3 — two skill resolvers, one broken

`/trace-fix` resolves via `findSkillFile(cwd, name)`, which falls back to
`factorySkillsDir()` and carries a comment explaining exactly why. `/plan` calls
`loadSkills({ cwd, agentDir, skillPaths: [], includeDefaults: true })`, so
`brainstorming` and `writing-plans` resolve only from the target repo or
`~/.pi/agent`. **`/plan` therefore fails in any repo that vendors neither, where
`/trace-fix` works.** One resolver, used by every command.

### 8.4 D4 — name collisions are pi's to arbitrate, not ours

Pi warns on a duplicate skill name and keeps the first found, so load order
decides and a project cannot reliably override a factory skill by name. This is
pi's behaviour and is not changed here. `init context` reports collisions so they
are visible at onboarding rather than as a confusing prompt later, and `/specify`
and everything downstream should treat skill names as global.

### 8.5 D5 — the Python CLIs

Reported by `init context` (§4), not fixed here. Publishing PIF to an index so a
target repo installs it without a relative path dependency remains a non-goal
(§12); this spec makes the gap legible instead of silent.

## 9. CLI surface

```
factory init context [--json]
factory init config    --validation none|pending [--extensions MODULE]
factory init gate      <name> --step "<cmd>" [--cwd <dir>] [--step ... ]
factory init harness   <name> --type <type> [--params-json <json>]
factory init playground <name> --type <type> [--params-json <json>]
```

- `--step` is repeatable and **argv order is step order**; `--cwd` binds to the
  preceding `--step`.
- `--params-json` rather than `k=v`, for the reason `--window-json` already
  carries: params hold typed values a flat key-value syntax cannot express.
- `init gate` rejects a name outside the fixed vocabulary, naming the four.
- `init harness` / `init playground` resolve `--type` against built-ins plus
  whatever the declared extensions module registers. **An unresolvable type is a
  hard error when no `extensions:` module is declared** — it can never resolve —
  **and a warning when one is**, because a greenfield project legitimately
  declares the seam before writing the code behind it. `init context` then
  reports the type as unresolved until it is, and `load_config` raises at run
  time as it does today.

Every verb is idempotent and re-runnable. There is no `factory init` bare
command: the entry point is the skill, and a human wanting a one-shot is better
served by writing the four lines of YAML than by a flag set nobody maintains.

## 10. Re-running against a configured repo

The drone repo is the case: hand-authored config, explanatory comments, an empty
`.pi/`. Init must improve it without damaging it.

- Every verb reads, updates in place, and writes. Keys init does not manage are
  preserved verbatim.
- **Comments are preserved.** `pyyaml` cannot round-trip them, and silently
  deleting a human's explanation of why a gate is written a certain way is
  exactly the class of silent loss this repo keeps designing against. The init
  writer uses `ruamel.yaml` in round-trip mode; `load_config` keeps reading with
  `pyyaml` and is untouched. This adds one dependency, used in one module.
- Nothing is deleted. Removing a gate or harness is a human editing the file.
- The skill presents the delta before writing and waits, mirroring the doctor's
  one-proposal-one-confirmation rule.

## 11. Components

**New**

- `src/factory/registry.py` — `Registry` with `harness`, `playground`, `scorers`,
  `skills`; `ExtensionModuleError`; built-in seeding; collision rules.
- `src/factory/init/{__init__,__main__,cli,context,write}.py` — mirroring
  `factory/doctor/`'s layout.
- `.pi/skills/init/SKILL.md`.

**Changed**

- `src/factory/config.py` — `load_config` builds and applies the registry;
  `_build` resolves against it; `validation:` parsed and its
  required/forbidden rule enforced.
- `src/factory/validation/sim_harness.py` — scorers from the registry;
  `load_scorers` call removed.
- `src/factory/polish/config.py` — `PLAYGROUND_TYPES` / `HARNESS_TYPES` become
  the registry's built-in seed.
- `src/factory/orchestrator/skills.py` — search path rather than single dir plus
  one fallback.
- `src/factory/trace/` status output — reads `validation:`.
- `scripts/install-pif.sh` — no `cd`; adds `--skill`.
- `pi-ext/factory-watch/src/index.ts` — `/plan` uses the shared resolver.

**Deleted**

- `harnesses.*.scorers`, and `validation/scorer_registry.py` entirely. A project
  supplies scorers through `r.scorers({...})` in a module the registry has
  already imported, so a second importer is dead weight. Its insert-import-remove
  `sys.path` handling, and the comment explaining why a target repo's `src/` is
  not importable by default, move to the registry's module loader — that
  knowledge is the part worth keeping.

**Migrated**

- `cool_physical_ai_project/.factory/factory.yaml` -> `extensions:`;
  `src/drone/factory_ext.py` registering the preemption scorer.

## 12. Testing strategy

- **Registry:** built-ins resolve with no extensions declared; a project module
  registering a harness, playground, scorers and skills is applied; an
  unresolvable type names both sets in the error; a module that fails to import
  raises `ExtensionModuleError` rather than presenting as an empty registry; a
  skills-directory name collision raises at registration.
- **`validation:`** absent with an empty register raises; present with a
  non-empty register raises; `none` and `pending` both accepted with an empty
  register; `trace status` wording differs between them.
- **`init context`:** reports built-in types, the role/skill map and the command
  list; reports repo facts without concluding from them; reports an undeclared
  and an unimportable extensions module distinguishably; reports which factory
  CLIs are invocable; `--json` round-trips.
- **Write verbs:** a gate name outside the vocabulary is rejected; `--step` order
  survives; `--cwd` binds to its step; unknown top-level keys survive a rewrite;
  **comments survive a rewrite**; running the same verb twice changes nothing.
- **Shim:** generate the three shims into a temp prefix and assert none contains
  a `cd` into the factory and each passes `--skill` with the factory's skills
  directory.
- **`/plan`:** a TS test that its skills resolve in a cwd that vendors none,
  matching the existing `/trace-fix` coverage.
- **Skill prompt:** assert `.pi/skills/init/SKILL.md` names `factory init
  context`, asks the validation question with all of `none`/`pending`, and
  states that it does not choose a harness for a greenfield repo — the pattern
  `test/skill-prompt.test.ts:37` established.
- **Dogfood guard:** the factory's own `.factory/factory.yaml` continues to parse
  and declare `unit` and `full`, extending the guard the gates design added.

## 13. Non-goals

- **`/specify`.** The greenfield SR and testbench workflow is spec #2.
- **Publishing PIF to an index.** The path dev-dependency stays; §8.5 only makes
  its consequences visible.
- **A configurable node graph.** The pipeline stays as written in `runner.py`.
  Only how requirements are *verified* is project-configurable, which is the part
  that genuinely differs per project.
- **Project-defined gate names.** The vocabulary stays `unit`/`sim`/
  `integration`/`full`.
- **Directory scaffolding, code generation, `pyproject.toml` edits.**
- **Installing the `pif` shim.** Init assumes the factory is already reachable;
  it reports when it is not.
- **Registering `/doctor` or `/init` as commands.** §8.2.
