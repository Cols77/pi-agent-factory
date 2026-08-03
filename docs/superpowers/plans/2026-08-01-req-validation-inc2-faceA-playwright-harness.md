# Increment 2 — Face A: Playwright E2E Live Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `PlaywrightE2EHarness` — the factory's first *live* validation harness (it executes seeded Playwright e2e runs and scores an N-trial pass-rate) — and wire the CareerOS webapp to validate 2 human-authored SRs against it.

**Architecture:** The project harness registry already exists and is type-dispatchable: `factory.polish.config.load_config` builds harness instances from a repo's `.factory/factory.yaml` via a `HARNESS_TYPES` dispatch table, and `factory.validation.pipeline` resolves `binding.harness` against it. So Face A adds one new `Harness` implementation, registers its *type*, and adds config + register files in the CareerOS repo. The harness separates the risky parts — report parsing and N-trial aggregation — behind an **injected trial-runner** callable, so all scoring logic is unit-tested against recorded Playwright JSON fixtures; a single slow smoke test covers the real subprocess invocation.

**Tech Stack:** Python 3.12 (factory), `pytest`, `ruff`, `pyright`; Playwright (Node, in the CareerOS `frontend/`), its built-in `json` reporter.

## Global Constraints

- Reuse existing shapes verbatim — do NOT redefine them: `Binding` (`harness, experiment, metric, assert_expr, trials:int=1, window:dict|None, cadence:str`), `HarnessResult(metric_value:float, passed:bool, trials:list[TrialResult], artifacts:list[Path], raw:dict)`, `TrialResult(seed:int, passed:bool, detail:str="")`, `Harness` Protocol (`run(self, binding, workdir) -> HarnessResult`) — all in `src/factory/requirements/register.py` and `src/factory/validation/harness.py`.
- Score assertions ONLY through `factory.validation.assertions.evaluate_assertion(value, assert_expr) -> bool`. Do not re-implement comparison parsing.
- Keep 1B's "missing/unknown harness or scenario **warns**, does not hard-fail" semantics — never change `pipeline.py`/`report.py` error posture.
- The DEV agent must never author or edit `requirements/**` or harness code — those are human-owned (trust model). This plan is authored by a human/controller, not a factory DEV task.
- Two repos: factory code in `C:/coding/pi-agent-factory` (build in an isolated worktree, never the main checkout); CareerOS in `C:/coding/markdown_pdf_system`. Every file path below names its repo.
- `pytest` for the factory runs from the factory repo root; new tests live under `tests/unit/validation/`.

---

### Task 1: Playwright JSON report parser (single-trial scoring)

**Repo:** `pi-agent-factory`

**Files:**
- Create: `src/factory/validation/playwright_harness.py`
- Create (fixture): `tests/unit/validation/fixtures/pw-report-pass.json`, `tests/unit/validation/fixtures/pw-report-fail.json`
- Test: `tests/unit/validation/test_playwright_harness.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_iter_specs(report: dict) -> Iterator[dict]` and `_spec_passed(report: dict, experiment: str) -> bool` — used by Task 2's `run`.

- [ ] **Step 1: Capture real fixtures.** From the CareerOS `frontend/`, run one existing spec through the JSON reporter to capture the *actual* shape for the installed Playwright version:

```bash
cd /c/coding/markdown_pdf_system/frontend
PLAYWRIGHT_JSON_OUTPUT_NAME=/tmp/pw.json npx playwright test <some-existing-spec> --reporter=json || true
```

Copy the emitted JSON to `pi-agent-factory` as `tests/unit/validation/fixtures/pw-report-pass.json`. Make a second copy where the target spec's `"ok"` is `false` and save as `pw-report-fail.json`. (These fixtures resolve the spec's §10 "exact reporter shape" open item — the parser is written to the real captured shape, not a guess.)

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/validation/test_playwright_harness.py
import json
from pathlib import Path

from factory.validation.playwright_harness import _spec_passed

FIX = Path(__file__).parent / "fixtures"

def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))

def test_spec_passed_true_when_matched_spec_ok():
    report = _load("pw-report-pass.json")
    assert _spec_passed(report, "sign-in") is True

def test_spec_passed_false_when_matched_spec_failed():
    report = _load("pw-report-fail.json")
    assert _spec_passed(report, "sign-in") is False

def test_spec_passed_false_when_no_spec_matches_experiment():
    report = _load("pw-report-pass.json")
    assert _spec_passed(report, "nonexistent-flow") is False
```

(Adjust the `"sign-in"` selector to a substring that appears in the file/title of the captured spec.)

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -v`
Expected: FAIL — `ImportError: cannot import name '_spec_passed'`.

- [ ] **Step 4: Write the parser**

```python
# src/factory/validation/playwright_harness.py
from __future__ import annotations

from collections.abc import Iterator


def _iter_specs(report: dict) -> Iterator[dict]:
    """Flatten Playwright's nested suites -> spec objects.

    The JSON reporter emits {"suites": [{"file", "specs": [...], "suites": [...]}]}
    with arbitrary nesting. Each yielded spec carries its inherited "file" so
    callers can match on file OR title.
    """

    def walk(suite: dict, file_hint: str) -> Iterator[dict]:
        file = suite.get("file", file_hint)
        for spec in suite.get("specs", []):
            yield {**spec, "file": spec.get("file", file)}
        for child in suite.get("suites", []):
            yield from walk(child, file)

    for suite in report.get("suites", []):
        yield from walk(suite, "")


def _spec_passed(report: dict, experiment: str) -> bool:
    """True iff at least one spec matches *experiment* (substring of file or
    title) and every matched spec is ok. No match -> False (a requirement whose
    spec did not run is not silently 'passed')."""
    matched = [
        s
        for s in _iter_specs(report)
        if experiment in s.get("file", "") or experiment in s.get("title", "")
    ]
    if not matched:
        return False
    return all(bool(s.get("ok")) for s in matched)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/factory/validation/playwright_harness.py tests/unit/validation/test_playwright_harness.py tests/unit/validation/fixtures/pw-report-pass.json tests/unit/validation/fixtures/pw-report-fail.json
git commit -m "feat(validation): Playwright JSON report parser (single-trial scoring)"
```

---

### Task 2: `PlaywrightE2EHarness.run` — N-trial aggregation

**Repo:** `pi-agent-factory`

**Files:**
- Modify: `src/factory/validation/playwright_harness.py`
- Test: `tests/unit/validation/test_playwright_harness.py`

**Interfaces:**
- Consumes: `_spec_passed` (Task 1); `HarnessResult`, `TrialResult` (`factory.validation.harness`); `evaluate_assertion` (`factory.validation.assertions`); `Binding` (`factory.requirements.register`).
- Produces: `TrialRunner = Callable[[int, str, Path], Path]` (seed, experiment, workdir) -> report_json_path; `class PlaywrightE2EHarness(run_trial: TrialRunner)` with `.run(binding, workdir) -> HarnessResult` and class attr `SUPPORTED_METRIC = "e2e_pass_rate"`. Used by Task 3 (`from_config`) and Task 4 (registry).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/validation/test_playwright_harness.py
from factory.validation.playwright_harness import PlaywrightE2EHarness
from factory.requirements.register import Binding

def _binding(trials, assert_expr="> 0.5"):
    return Binding(harness="playwright-e2e", experiment="sign-in",
                   metric="e2e_pass_rate", assert_expr=assert_expr, trials=trials)

def _fake_runner(seq):
    # seq: list of fixture names, one per seed
    calls = []
    def run_trial(seed, experiment, workdir):
        calls.append((seed, experiment))
        return FIX / seq[seed]
    run_trial.calls = calls
    return run_trial

def test_run_pass_rate_all_pass(tmp_path):
    h = PlaywrightE2EHarness(_fake_runner(["pw-report-pass.json"] * 3))
    res = h.run(_binding(3), tmp_path)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert [t.seed for t in res.trials] == [0, 1, 2]

def test_run_pass_rate_mixed_and_assertion(tmp_path):
    seq = ["pw-report-pass.json", "pw-report-fail.json", "pw-report-pass.json"]
    h = PlaywrightE2EHarness(_fake_runner(seq))
    res = h.run(_binding(3, assert_expr=">= 0.9"), tmp_path)
    assert abs(res.metric_value - (2 / 3)) < 1e-9
    assert res.passed is False  # 0.666 < 0.9

def test_run_rejects_unsupported_metric(tmp_path):
    b = Binding(harness="playwright-e2e", experiment="sign-in",
                metric="preemption_success_rate", assert_expr="> 0.5", trials=1)
    h = PlaywrightE2EHarness(_fake_runner(["pw-report-pass.json"]))
    import pytest
    with pytest.raises(ValueError):
        h.run(b, tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -k run -v`
Expected: FAIL — `cannot import name 'PlaywrightE2EHarness'`.

- [ ] **Step 3: Implement `run`**

```python
# add to src/factory/validation/playwright_harness.py
import json
from collections.abc import Callable
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult

# (seed, experiment, workdir) -> path to that trial's Playwright JSON report.
# Injected so aggregation is testable without invoking Playwright.
TrialRunner = Callable[[int, str, Path], Path]


class PlaywrightE2EHarness:
    """Live harness: run a Playwright e2e spec headless N times (seeded) and
    score the pass-rate. Executes runs instead of replaying a fixture trace."""

    SUPPORTED_METRIC = "e2e_pass_rate"

    def __init__(self, run_trial: TrialRunner) -> None:
        self._run_trial = run_trial

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        if binding.metric != self.SUPPORTED_METRIC:
            raise ValueError(
                f"PlaywrightE2EHarness supports metric {self.SUPPORTED_METRIC!r}, "
                f"got {binding.metric!r}"
            )
        trials: list[TrialResult] = []
        reports: list[dict] = []
        n = max(1, binding.trials)
        for seed in range(n):
            report_path = self._run_trial(seed, binding.experiment, workdir)
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            reports.append(report)
            trials.append(TrialResult(seed=seed, passed=_spec_passed(report, binding.experiment)))
        rate = sum(1 for t in trials if t.passed) / len(trials)
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=trials,
            artifacts=[],
            raw={"reports": reports},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/playwright_harness.py tests/unit/validation/test_playwright_harness.py
git commit -m "feat(validation): PlaywrightE2EHarness N-trial pass-rate aggregation"
```

---

### Task 3: `from_config` + real subprocess trial-runner

**Repo:** `pi-agent-factory`

**Files:**
- Modify: `src/factory/validation/playwright_harness.py`
- Test: `tests/unit/validation/test_playwright_harness.py`

**Interfaces:**
- Consumes: `PlaywrightE2EHarness` (Task 2).
- Produces: `PlaywrightE2EHarness.from_config(cls, params: dict, project_root: Path) -> PlaywrightE2EHarness` (signature matching `SimTestbenchHarness.from_config`, required by the `HARNESS_TYPES` dispatch in Task 4); module-level `_subprocess_runner(app_dir: Path, seed_env: str, test_cmd: list[str]) -> TrialRunner`.

- [ ] **Step 1: Write the failing test** (config wiring only — the subprocess itself is covered by the Task 6 smoke test)

```python
# add to tests/unit/validation/test_playwright_harness.py
def test_from_config_builds_harness_with_defaults(tmp_path):
    h = PlaywrightE2EHarness.from_config({}, tmp_path)
    assert isinstance(h, PlaywrightE2EHarness)

def test_from_config_runner_is_callable(tmp_path):
    h = PlaywrightE2EHarness.from_config({"app_dir": "frontend", "seed_env": "E2E_SEED"}, tmp_path)
    # the injected runner is a 3-arg callable (seed, experiment, workdir)
    assert callable(h._run_trial)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -k from_config -v`
Expected: FAIL — `AttributeError: ... has no attribute 'from_config'`.

- [ ] **Step 3: Implement `from_config` + `_subprocess_runner`**

```python
# add to src/factory/validation/playwright_harness.py
import os
import subprocess


def _subprocess_runner(app_dir: Path, seed_env: str, test_cmd: list[str]) -> TrialRunner:
    def run_trial(seed: int, experiment: str, workdir: Path) -> Path:
        workdir.mkdir(parents=True, exist_ok=True)
        report_path = workdir / f"pw-report-seed{seed}.json"
        env = {
            **os.environ,
            seed_env: str(seed),
            "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report_path),
        }
        with (workdir / f"pw-stdout-seed{seed}.log").open("w", encoding="utf-8") as log:
            subprocess.run(
                [*test_cmd, experiment, "--reporter=json"],
                cwd=str(app_dir), env=env, check=False,
                stdout=log, stderr=subprocess.STDOUT,
            )
        return report_path

    return run_trial


# add as a classmethod on PlaywrightE2EHarness:
    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "PlaywrightE2EHarness":
        app_dir = project_root / params.get("app_dir", "frontend")
        seed_env = params.get("seed_env", "E2E_SEED")
        test_cmd = list(params.get("test_cmd", ["npx", "playwright", "test"]))
        return cls(_subprocess_runner(app_dir, seed_env, test_cmd))
```

- [ ] **Step 4: Run tests + lint/type**

Run: `python -m pytest tests/unit/validation/test_playwright_harness.py -v && ruff check src/factory/validation/playwright_harness.py && pyright src/factory/validation/playwright_harness.py`
Expected: PASS; ruff clean; pyright clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/playwright_harness.py tests/unit/validation/test_playwright_harness.py
git commit -m "feat(validation): PlaywrightE2EHarness.from_config + subprocess trial-runner"
```

---

### Task 4: Register the `playwright-e2e` harness type

**Repo:** `pi-agent-factory`

**Files:**
- Modify: `src/factory/polish/config.py:19-21` (the `HARNESS_TYPES` table)
- Test: `tests/unit/polish/test_config.py` (or the existing config test module — confirm its path with `git ls-files | grep test_config`)

**Interfaces:**
- Consumes: `PlaywrightE2EHarness.from_config` (Task 3).
- Produces: a `.factory/factory.yaml` `harnesses:` entry of `type: playwright-e2e` now builds a `PlaywrightE2EHarness` via `load_config`. Relied on by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# in the config test module
from pathlib import Path
from factory.polish.config import load_config
from factory.validation.playwright_harness import PlaywrightE2EHarness

def test_load_config_builds_playwright_harness(tmp_path: Path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "harnesses:\n"
        "  web-e2e:\n"
        "    type: playwright-e2e\n"
        "    app_dir: frontend\n"
        "    seed_env: E2E_SEED\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert isinstance(cfg.harnesses["web-e2e"], PlaywrightE2EHarness)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -k test_load_config_builds_playwright_harness -v`
Expected: FAIL — `UnknownTypeError: 'web-e2e': unknown type 'playwright-e2e'`.

- [ ] **Step 3: Register the type**

```python
# src/factory/polish/config.py — add the import and the table entry
from factory.validation.playwright_harness import PlaywrightE2EHarness

HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]] = {
    "sim-testbench": SimTestbenchHarness.from_config,
    "playwright-e2e": PlaywrightE2EHarness.from_config,
}
```

- [ ] **Step 4: Run test + full validation suite**

Run: `python -m pytest tests/unit/validation tests/unit/polish -v`
Expected: PASS (new test + no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/factory/polish/config.py tests/unit/polish/test_config.py
git commit -m "feat(polish): register playwright-e2e harness type in HARNESS_TYPES"
```

---

### Task 5: Wire CareerOS — harness config + 2 SR register files

**Repo:** `markdown_pdf_system` (CareerOS)

**Files:**
- Modify: `.factory/factory.yaml` (add a `harnesses:` section)
- Create: `requirements/SR-010.md`, `requirements/SR-011.md`
- Test: run the factory's register parser + selection against this repo (command below)

**Interfaces:**
- Consumes: the `playwright-e2e` type (Task 4).
- Produces: two validatable SRs bound to Playwright specs — consumed live by Task 6.

- [ ] **Step 1: Confirm CareerOS specs + dev commands.** Read `markdown_pdf_system/README.md` / `COMMANDS.md` and `frontend/` Playwright specs. Identify the exact spec file/title substrings for the sign-in and tailor-CV flows and the frontend dir name. (Resolves the spec's §9/§10 "confirm CareerOS launch + spec names" open item.)

- [ ] **Step 2: Add the harness to `.factory/factory.yaml`** (the `playgrounds:` block already exists — append `harnesses:`)

```yaml
harnesses:
  web-e2e:
    type: playwright-e2e
    app_dir: frontend
    seed_env: E2E_SEED
```

- [ ] **Step 3: Author `requirements/SR-010.md`.** CRITICAL: `parse_requirement` reads `id, title, statement, domain, upstream, binding` from the **YAML frontmatter** (`meta["statement"]`, `meta["binding"]`) — the EARS statement is a frontmatter field, NOT the markdown body. The body (`post.content`) is free-text rationale only.

```markdown
---
id: SR-010
title: Sign-in flow succeeds
statement: >
  When a registered user submits valid credentials, the system shall sign them
  in and land them on the authenticated home view.
domain: behavioral
upstream: []
binding:
  harness: web-e2e
  experiment: sign-in
  metric: e2e_pass_rate
  assert: ">= 0.95"
  trials: 5
---

Rationale: sign-in gates every other flow; a regression here blocks the app.
```

- [ ] **Step 4: Author `requirements/SR-011.md`**

```markdown
---
id: SR-011
title: Tailor-CV emits a valid PDF
statement: >
  When a user runs "tailor CV" against a job description, the system shall
  produce a non-empty, parseable PDF for download.
domain: behavioral
upstream: []
binding:
  harness: web-e2e
  experiment: tailor-cv
  metric: e2e_pass_rate
  assert: ">= 0.90"
  trials: 5
---

Rationale: PDF export is the product's core deliverable.
```

(Adjust `experiment:` values to the real spec substrings from Step 1. `checksum` is intentionally omitted — a hand-authored SR parses fine without it and reads as "unstamped/stale" until the register CLI stamps it; stamp with the appropriate `factory-requirements` subcommand, confirmed in Step 5, if the workflow requires a current checksum.)

- [ ] **Step 5: Verify the register parses + selects.** From the factory repo (worktree), point the CLI at CareerOS:

Run: `python -m factory.requirements.cli index --project-root /c/coding/markdown_pdf_system` (confirm exact subcommand with `python -m factory.requirements.cli --help`)
Expected: SR-010 and SR-011 listed, no parse/checksum errors.

- [ ] **Step 6: Commit** (in the CareerOS repo)

```bash
cd /c/coding/markdown_pdf_system
git add .factory/factory.yaml requirements/SR-010.md requirements/SR-011.md
git commit -m "feat(factory): declare playwright-e2e harness + SR-010/SR-011 acceptance requirements"
```

---

### Task 6: Live smoke test — prove one SR validates green end-to-end

**Repo:** `pi-agent-factory`

**Files:**
- Create: `tests/integration/validation/test_playwright_harness_smoke.py`
- Test: itself (marked slow; runs real Playwright)

**Interfaces:**
- Consumes: `PlaywrightE2EHarness.from_config` (Task 3), the CareerOS `.factory/factory.yaml` + SRs (Task 5).
- Produces: nothing downstream — this is the Increment-2 "stochastic + live" proof.

- [ ] **Step 1: Write the smoke test** (guard-skips if CareerOS or Playwright is unavailable, so CI without the webapp stays green)

```python
# tests/integration/validation/test_playwright_harness_smoke.py
import shutil
from pathlib import Path

import pytest

from factory.polish.config import load_config
from factory.requirements.register import Binding

CAREEROS = Path("C:/coding/markdown_pdf_system")

pytestmark = pytest.mark.skipif(
    not (CAREEROS / "frontend").exists() or shutil.which("npx") is None,
    reason="CareerOS frontend or npx not available",
)

def test_signin_sr_validates_live(tmp_path):
    harness = load_config(CAREEROS).harnesses["web-e2e"]
    binding = Binding(harness="web-e2e", experiment="sign-in",
                      metric="e2e_pass_rate", assert_expr=">= 0.95", trials=2)
    res = harness.run(binding, tmp_path)
    assert 0.0 <= res.metric_value <= 1.0
    assert len(res.trials) == 2
    # a report file was produced for each trial
    assert list(tmp_path.glob("pw-report-seed*.json"))
```

- [ ] **Step 2: Run the smoke test** (start CareerOS dev servers first if the specs need them — check whether its Playwright config auto-starts servers via `webServer`)

Run: `python -m pytest tests/integration/validation/test_playwright_harness_smoke.py -v -s`
Expected: PASS — 2 report files produced, `metric_value` in `[0,1]`. If the sign-in flow is currently healthy, `res.passed` is True; then break the flow and re-run to see it go False (the live green→red proof; do not commit the break).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/validation/test_playwright_harness_smoke.py
git commit -m "test(validation): live Playwright harness smoke — Increment 2 stochastic+live proof"
```

---

## Self-Review

**Spec coverage (against the Inc 2 design §3):**
- §3.1 project harness registry — covered by discovery that it already exists (config `HARNESS_TYPES`); Task 4 registers the new type. ✅
- §3.2 `PlaywrightE2EHarness` (seeded headless run, reporter-JSON fold, N-trial pass-rate, reuse `HarnessResult`/trials guard) — Tasks 1–3. ✅
- §3.3 2–3 human-authored webapp SRs + live green→red proof — Tasks 5–6. ✅ (SR-012 optional/omitted — YAGNI; two SRs prove the thread.)
- §8 testing strategy (registry resolution, harness against recorded reporter fixture, thin live smoke) — Tasks 1,2,4,6. ✅
- Deferred/out-of-scope (Face B orchestrator, scope-guard rule, SR-002/drone, perception) — correctly NOT in this plan.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; the only "adjust to real substrings" notes point at Task 1 Step 1 / Task 5 Step 1 which capture the ground truth first. ✅

**Type consistency:** `TrialRunner = Callable[[int, str, Path], Path]` used identically in Tasks 2 & 3; `from_config(params, project_root)` matches `SimTestbenchHarness` and the `HARNESS_TYPES` value type `Callable[[dict, Path], Harness]`; `_spec_passed(report, experiment)` signature identical in Tasks 1 & 2; `SUPPORTED_METRIC="e2e_pass_rate"` matches SR bindings in Task 5. ✅

**Notes for the executor:**
- Base branch: this plan assumes a worktree off a main line that contains **1B** (in main) and ideally **1C** (currently held pending the main-tree cleanup). 1C is not required for Face A (Face A is Python-only), but merge it first if convenient so the review surfaces render these SRs.
- Confirm the config test module path (Task 4) with `git ls-files | grep -E 'polish/test_config|test_config'` before writing.
