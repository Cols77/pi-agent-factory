# Design: Project-Configurable Validation Gates

Date: 2026-08-05
Status: Approved (brainstorming) — ready for implementation planning
Builds on: `2026-08-01-req-validation-inc2-webapp-live-harness-and-polish-node-design.md`
(§3.1 project harness registry — this is the same seam applied to gates).

## 1. Problem

`factory-run` cannot produce a green fix in any repo but the factory itself.
`SubprocessGateRunner` hard-codes the factory's own layout:

```python
_SCRIPTS = {
    "unit": "scripts/gates/unit.py",
    "sim":  "scripts/gates/sim_smoke.py",
    "full": "scripts/gates/all.py",
}
```

and runs those paths with `cwd=<target repo>`. CareerOS has no `scripts/gates/`,
so every gate exits non-zero with empty output. Observed live on 2026-08-05
(polish-live-11, 46 minutes): the polish loop routed a finding, isolated a
worktree, and ran the dev agent for three full attempts — 12.5 MB and 37 MB of
agent transcript — against a validation gate it could never satisfy. The run
ended `failed` with 0-byte `unit-gate.log` and `sim-gate.log`.

This is the last blocker between the polish loop and a landed fix. Everything
around it is proven: synthesis, Gate 1, worktree isolation, the dev agent,
fast-forward integration, Gate 2, teardown.

Unlike the three sibling bugs fixed the same day (scope-guard path in polish,
role skills, scope-guard path in `factory-run`), this one is **not** fixable by
resolving from the factory. Running the factory's own pytest against CareerOS is
meaningless. The target project must declare what "green" means for it.

## 2. Decisions locked during brainstorming

1. **An undeclared gate skips and passes.** A webapp has no `sim`; forcing it to
   invent one invites `exit 0` stubs, which are worse than an honest skip.
2. **A gate is an ordered list of steps**, each `cmd` + optional `cwd`. Real
   repos span sub-projects: CareerOS's "unit" is pytest in `backend/` *and*
   `npm test` in `frontend/`. A single command string would force `&&` chaining
   through cmd.exe — the exact fragility that broke the Playwright `webServer`
   and the pi prompt earlier the same day.
3. **No fallback.** The hard-coded map is deleted and the factory declares its
   own gates like every other project. One code path, and the mechanism is
   dogfooded by its own author.
4. **Config lives in a neutral `factory.config`.** `FactoryConfig`/`load_config`
   move out of `factory.polish` (which already imports `factory.validation`, so
   it was never really polish's to own) and gain a `gates` field. The
   orchestrator core must not import from a consumer package.
5. **`pytest` exit code 5 ("no tests collected") passes**, with the reason in the
   gate log. See §4.
6. **A config with no `gates:` section at all is a hard error**, distinct from an
   individual gate being absent. See §4.

## 3. Config shape

`gates:` joins `playgrounds:` and `harnesses:` in `.factory/factory.yaml`:

```yaml
gates:
  <name>:
    - { cmd: "<shell command>", cwd: "<dir relative to repo root, optional>" }
```

Gate names are the fixed vocabulary the pipeline already calls: `unit` (dev
node), `sim` and `integration` (validation node), `full` (review node). The
evidence `test_result` connector uses `unit`/`sim`/`full`. This design does not
introduce project-defined gate names.

### CareerOS (`markdown_pdf_system`)

`sim` is absent, so it skips:

```yaml
gates:
  unit:
    - { cmd: "{python} -m pytest -q", cwd: backend }
    - { cmd: "npm test", cwd: frontend }
  integration:
    - { cmd: "npx playwright test", cwd: frontend }
  full:
    - { cmd: "npx tsc --noEmit", cwd: frontend }
    - { cmd: "{python} -m pytest -q", cwd: backend }
```

### The factory itself (new file — it currently has no `.factory/`)

Migrated faithfully from `scripts/gates/_proc.py`:

```yaml
gates:
  unit:
    - { cmd: "{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py" }
  sim:
    - { cmd: "{python} -m pytest -m sim -q" }
  integration:
    - { cmd: "{python} -m pytest tests/integration/ -q -m integration" }
  full:
    - { cmd: "{python} -m ruff check ." }
    - { cmd: "{python} -m pyright" }
    - { cmd: "{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py" }
    - { cmd: "{python} -m pytest -m agent -q" }
```

`--ignore=tests/gates/test_all_gate.py` must survive migration or the unit gate
recurses into the test that runs the full gate.

### `{python}`

`{python}` expands to `sys.executable`. `_proc.py` uses `sys.executable`
deliberately so tools resolve from the venv even when the subprocess PATH does
not include its `Scripts/` directory. A bare `python` in committed config would
silently resolve a different interpreter; an absolute venv path is not portable.
`{python}` is the only substitution — no general templating.

## 4. Execution semantics

- Steps run **in order**. The first non-zero exit fails the gate and its code is
  returned. Later steps do not run.
- Each step runs via `subprocess.run(cmd, shell=True, cwd=repo_root/cwd)`,
  matching how `playgrounds.services` already launches commands. Shell is
  required on Windows regardless (`npm`/`npx` are `.cmd` shims). Gate commands
  are single-line developer-authored config, so they avoid the embedded-newline
  hazard that silently dropped `--mode json` from the pi invocation.
- **The gate log** is the combined stdout+stderr of the steps that ran, written
  to `<log_dir>/<name>-gate.log`. When `log_dir` is `None` the steps stream to
  the console instead and nothing is captured — the same two modes
  `SubprocessGateRunner` has today.
- **Exit code 5 passes**, for *any* step, not only pytest ones. pytest returns 5
  for "no tests collected"; a declared gate that matches nothing is a false
  *red* — the mirror of the false greens removed on 2026-08-05 — and it fires
  the moment a repo split moves tests out (see §7). The rule is deliberately
  blanket rather than pytest-sniffing: exit 5 is close to unused elsewhere, and
  inspecting a command string to guess whether it is "a pytest step" would be
  guesswork with a worse failure mode. The log records that the gate matched
  nothing, so a genuine tool returning 5 is visible rather than silent.
- **Undeclared gates pass** and are recorded as skipped. `ConfigGateRunner`
  exposes which gates were declared, ran, and skipped, and validation records it,
  so a typo'd key reads as `sim: not declared` instead of vanishing silently.
- **No `gates:` section at all raises.** "This project has no sim" and "this
  project never said what to check" are different statements. Without the
  distinction, any repo lacking config would validate nothing while reporting
  green — precisely the failure mode this work exists to remove.

## 5. Components and data flow

**New/moved:**

- `src/factory/config.py` — `GateStep(cmd: str, cwd: str | None)`,
  `FactoryConfig(playgrounds, harnesses, gates)`, `load_config(project_root)`.
  Moved from `factory/polish/config.py`, which re-exports for back-compat.
- `ConfigGateRunner(repo_root, gates, log_dir=None)` in
  `factory/orchestrator/backends.py`, implementing the existing `GateRunner`
  protocol.

**Deleted:** `SubprocessGateRunner` and its `_SCRIPTS` map.

**Changed:** `factory/orchestrator/__main__.py` builds `ConfigGateRunner` from
`load_config(repo_root).gates`.

**Unchanged — this is the point:** nodes still call `gates.run("unit")`,
`("sim")`, `("integration")`, `("full")`; `runner.py` still takes a `GateRunner`;
the evidence `test_result` connector is untouched; `FakeGateRunner` still
satisfies the protocol, so every existing node and runner test keeps working.
Only construction changes.

## 6. Migration

1. Add `src/factory/config.py`; re-export from `factory/polish/config.py`.
2. Add `ConfigGateRunner`; wire it in `__main__.py`; delete
   `SubprocessGateRunner`.
3. Create the factory's `.factory/factory.yaml` with §3's gates.
4. Delete `scripts/gates/{all,unit,sim_smoke,lint,typecheck}.py` and `_proc.py`,
   plus `tests/gates/test_all_gate.py` and `tests/gates/test_proc.py`. This
   retires the long-standing `from _proc import` break in `all.py` that has
   failed every full-suite run.
5. Add CareerOS's `gates:` section.

`scripts/gates/{ext,watch_ext,validate_kb,validate_manifest,validate_session}.py`
are **not** touched: they are standalone checks, not part of the gate map.

## 7. Context: the factory/drone repo split

A parallel effort is moving the drone and sim code out of the factory into
`cool_physical_ai_project` (which has `scripts/gates/` inherited from the
original split but no `.factory/`). Two consequences:

- It is a **third consumer** of this mechanism, and the one project for which
  `sim` is the meaningful gate.
- When the sim tests leave the factory, the factory's `sim` gate matches nothing.
  The exit-5 rule (§4) means that degrades to a pass rather than a red, so the
  split does not have to be synchronised with a config edit. Dropping the `sim:`
  key from the factory's config afterwards is then tidying, not a fix.

## 8. Testing strategy

- **`ConfigGateRunner`** against a temp repo with trivial commands: steps run in
  order; the first non-zero short-circuits and its code is returned; `cwd` is
  honoured; the log holds combined output; an undeclared gate passes and is
  reported skipped; exit 5 passes and is noted.
- **Config:** `gates:` parses into `GateStep`s; an absent `gates:` section
  raises; a malformed step reports which gate and why.
- **Migration guard:** a test asserting the factory's own `.factory/factory.yaml`
  declares `unit` and `full`, so the dogfood config cannot quietly disappear.
- **Untouched:** node/runner tests keep using `FakeGateRunner`; no test needs to
  change to accommodate the new runner.

## 9. Non-goals

- Project-defined gate **names** — the vocabulary stays `unit`/`sim`/
  `integration`/`full`.
- Parallel step execution, per-step timeouts, retries, env-var injection.
- Any change to what the nodes do with a gate result.
- Touching the standalone `ext`/`watch_ext`/`validate_*` scripts.
