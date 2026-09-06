# FEAT-017 Guided Planning Entrypoint (Claude Code) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Claude Code's read-only `/coherence-plan` with a guided entrypoint that walks a named planning run from an existing FEAT's drafted artifacts, through interactive intent capture, spec authoring, plan authoring, and deterministic decomposition, to executable `tasks/T-NNN.md` records and a non-executing handoff — without a human hand-sequencing any `coherence plan` subcommand.

**Architecture:** Three layers with a strict division of authority. **The backend owns structure** — durability, identity, ordering, hashes, structural parity, mechanical transformation, and *whether a required record exists*. **The model owns semantics** — what to ask, what the spec says, what the plan says, and every review judgment. **Hooks enforce that model work happened and was recorded**, and enforce channel discipline; they never adjudicate semantics. The human owns every consent, resolution, and terminal-status decision. No new planning state machine is created: the entrypoint is a validated call path over `coherence plan` subcommands that already exist (design §3h: *"the guided entrypoint does not create a second planner or scheduler"*).

**Tech Stack:** Python 3.12, stdlib + PyYAML, pytest, ruff. Claude Code slash command (Markdown), `.claude/settings.json` hooks (`command`, `agent`, `prompt` types).

**Spec:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` §3h and §4, realizing `requirements/SR-065.md`; upstream `SR-043`, `SR-044`, `SR-052`, `SR-053`, `SR-054`.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The authority split is the point of this design. Violating it is a plan failure, not a style issue:**
  - A **hook** may enforce *procedural* facts (a record exists; a call used the sanctioned channel; a file is present). A hook MUST NOT try to judge whether content is good.
  - **`detect_challenges` is a prior, not a gate.** It is ~30 lines of substring matching (`always`, `never`, `guaranteed`, `obviously`, `everyone`, `only`, `must use`, `choose`, plus `must`/`must not` pairs). Its output is surfaced as a hint. It MUST NOT block anything on its own, because it produces both false positives (the word "only" is ubiquitous) and false negatives (an unsupported claim with no trigger words passes silently). Determinism applied to an unreliable signal yields confident wrongness, not safety.
  - **An agent may never mint consent** (SR-044). Resolution choice (`resolve`/`revise`/`defer`/`accept`) and terminal status (`provisional`/`cancelled`/`needs_user`) are human decisions the model transports, never originates.
- **Provenance is load-bearing.** `coherence plan append --source` defaults to `user` and flows into each challenge's `provenance`. Human answers use `--source user`. Review-agent findings use `--source intent-review-agent`. Never blur the two.
- **Only implemented backend capability may be used.** `session.py` projects exactly three states: `capture`, `intent_provisional`, `blocked`. The spec's intermediate states (`spec_authoring` … `handoff_ready`) have no implementation; spec and plan authoring are *file authoring by the model*, validated afterwards by `check`/`bootstrap`. Never simulate a state the backend cannot produce.
- **Exit-code contract** for every `coherence plan` subcommand (`cli.py`): `0` and `1` both carry trustworthy JSON (`1` means blocked / not-ok / findings-present, which is *data*); **any other code means stdout must not be trusted**, even if it parses.
- **Argv only.** Every backend invocation is a `list[str]` with `shell=False`. Never a shell string.
- **Run-id grammar** is `legal_actions_adapter.SAFE_RUN_ID` (`^[A-Za-z0-9][A-Za-z0-9._-]*$`). Import it; never restate the regex.
- **`bootstrap` hard-requires `.factory/factory.yaml`**, or raises `BootstrapPrerequisiteError` before doing anything.
- **Hermes and Codex are out of scope.** `.hermes/plugins/coherence-plan/plugin.py` and `legal_actions_adapter.py`'s public API MUST remain unchanged and green.
- **SR-065 stays `proposed`.** This plan implements its acceptance tests. It MUST NOT edit the SR's status or self-certify adoption.
- Verify with `rtk proxy uv run pytest …` and `rtk proxy uv run ruff check …` (bare `pytest` mis-collects in this repo).
- Commits touching non-exempt paths need an `SR: SR-065` trailer.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/coherence/planning/adapter_backend.py` (create) | The one fail-closed invoke primitive: run-id gate, argv-only subprocess, exit-code contract. Everything else builds on it. |
| `src/coherence/planning/guided_entrypoint.py` (create) | Capture-session verbs (`start`/`resume`/`status`/`append`/`resolve`/`finalize`) + CLI. |
| `src/coherence/planning/artifact_navigator.py` (create) | Read-only resolution of a FEAT's drafted artifact graph, verbatim. |
| `src/coherence/planning/guided_pipeline.py` (create) | `bootstrap`/`check`/`review`/`handoff` verbs + CLI. |
| `.claude/hooks/coherence_channel_guard.py` (create) | PreToolUse: deny backend planning calls that bypass the adapters. |
| `.claude/hooks/coherence_finalize_gate.py` (create) | PreToolUse: deny `finalize` unless the review record exists and every challenge is dispositioned. Reads the journal; runs no model. |
| `.claude/hooks/coherence_challenge_surface.py` (create) | PostToolUse: inject unresolved challenges as context so the model cannot silently skip one. |
| `.claude/settings.json` (create) | Hook registration, including the `type: "agent"` pre-finalize review and the `type: "prompt"` Stop check. |
| `.claude/commands/coherence-plan.md` (replace) | The guided workflow prose. |
| `tests/unit/coherence/test_planning_guided.py` (create) | The acceptance-test file SR-065's AC-1/AC-2/AC-3 already name. |
| `tests/unit/coherence/test_artifact_navigator.py` (create) | Navigator contract. |
| `tests/unit/coherence/test_planning_hooks.py` (create) | Hook decision logic, tested as pure functions. |
| `tests/unit/coherence/test_coherence_plan_command_contract.py` (create) | Regression-protects the command file's invariants. |

`tests/unit/_legal_actions_json.py` is reused for `completed_json` only.

---

### Task 1: The fail-closed backend invoke primitive

**Files:**
- Create: `src/coherence/planning/adapter_backend.py`
- Test: `tests/unit/coherence/test_planning_guided.py`

**Interfaces:**
- Consumes: `legal_actions_adapter.is_safe_run_id`
- Produces: `BackendError(RuntimeError)`; `invoke_backend(command: list[str], project_root: Path) -> tuple[int, str]`; `require_safe_run_id(run_id: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/coherence/test_planning_guided.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coherence.planning.adapter_backend import BackendError, invoke_backend, require_safe_run_id
from tests.unit._legal_actions_json import completed_json

pytestmark = pytest.mark.unit


def test_require_safe_run_id_accepts_the_shared_grammar() -> None:
    require_safe_run_id("FEAT-018")
    require_safe_run_id("run-001")


@pytest.mark.parametrize("run_id", ["", "../escape", "run 001", "run;rm -rf", "-run", "run/001"])
def test_require_safe_run_id_rejects_unsafe_ids(run_id: str) -> None:
    with pytest.raises(BackendError, match="safe run-id grammar"):
        require_safe_run_id(run_id)


@pytest.mark.parametrize("exit_code", [0, 1])
def test_trusted_exit_codes_return_stdout(monkeypatch: pytest.MonkeyPatch, exit_code: int) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({"ok": True}, returncode=exit_code)
    )

    code, stdout = invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))

    assert code == exit_code
    assert json.loads(stdout) == {"ok": True}


@pytest.mark.parametrize("exit_code", [2, 3, 127])
def test_untrusted_exit_codes_never_return_stdout(
    monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: completed_json({"ok": True}, returncode=exit_code, stderr="segfault"),
    )

    with pytest.raises(BackendError, match="segfault"):
        invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))


def test_untrusted_exit_with_no_stderr_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({}, returncode=2, stderr="")
    )

    with pytest.raises(BackendError, match="backend exited unsuccessfully"):
        invoke_backend(["uv", "run", "coherence"], Path("/p"))


def test_launch_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise OSError("uv not found")

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(BackendError, match="uv not found"):
        invoke_backend(["uv"], Path("/p"))


def test_invocation_never_uses_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(command: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, kwargs=kwargs)
        return completed_json({}, returncode=0)

    monkeypatch.setattr(subprocess, "run", capture)
    invoke_backend(["uv", "run", "coherence"], Path("/p"))

    assert isinstance(seen["command"], list)
    assert seen["kwargs"]["shell"] is False
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: FAIL — `ModuleNotFoundError: No module named 'coherence.planning.adapter_backend'`

- [ ] **Step 3: Implement the minimal code to make the test pass**

```python
# src/coherence/planning/adapter_backend.py
"""The single fail-closed call path from a host adapter to the Coherence CLI.

Every guided-planning adapter routes its subprocess work through this module so
the safety-critical rules exist once:

- a run id outside the shared safe grammar never reaches a subprocess;
- invocations are argv lists, never shell strings;
- the exit-code contract is interpreted in exactly one place. Exit codes 0 and 1
  both carry trustworthy JSON -- 1 means "blocked", "not ok", or "findings
  present", which is *data* the host must relay, not a crash. Any other exit
  code means stdout is untrustworthy and is refused even when it parses.

This module holds no planning authority: it starts nothing, decides nothing, and
knows nothing about what the payloads mean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from coherence.planning.legal_actions_adapter import is_safe_run_id

#: Exit codes whose stdout the backend guarantees is a structured payload.
TRUSTED_EXIT_CODES = (0, 1)


class BackendError(RuntimeError):
    """A backend invocation could not be run, or its output cannot be trusted."""


def require_safe_run_id(run_id: str) -> None:
    """Raise unless `run_id` matches the shared safe run-id grammar."""
    if not is_safe_run_id(run_id):
        raise BackendError("run_id must match the safe run-id grammar")


def invoke_backend(command: list[str], project_root: Path) -> tuple[int, str]:
    """Run an argv-only backend command and return `(exit_code, stdout)`.

    Raises ``BackendError`` on a launch failure or an exit code outside
    ``TRUSTED_EXIT_CODES``; in the latter case stdout is discarded unread.
    """
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except OSError as exc:
        raise BackendError(str(exc)) from exc

    if result.returncode not in TRUSTED_EXIT_CODES:
        raise BackendError((result.stderr or "backend exited unsuccessfully").strip())
    return result.returncode, result.stdout or ""


__all__ = ["TRUSTED_EXIT_CODES", "BackendError", "invoke_backend", "require_safe_run_id"]
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/coherence/planning/adapter_backend.py tests/unit/coherence/test_planning_guided.py
git commit -m "feat(planning): add the fail-closed backend invoke primitive

SR: SR-065"
```

---

### Task 2: Capture-session verbs

**Files:**
- Create: `src/coherence/planning/guided_entrypoint.py`
- Test: `tests/unit/coherence/test_planning_guided.py`

**Interfaces:**
- Consumes: `adapter_backend.{BackendError, invoke_backend, require_safe_run_id}`
- Produces: `SESSION_VERBS: tuple[str, ...]`; `build_session_command(project_root: Path, run_id: str, verb: str, **fields: str) -> list[str]`; `parse_session_response(raw: str, run_id: str) -> dict[str, Any]`; `run_session_command(project_root: Path, run_id: str, verb: str, **fields: str) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/coherence/test_planning_guided.py`:

```python
from coherence.planning.guided_entrypoint import (
    SESSION_VERBS,
    build_session_command,
    parse_session_response,
    run_session_command,
)


def session_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": 1,
        "ok": True,
        "run_id": "run-001",
        "state": "capture",
        "next_sequence": 2,
        "journal_sha256": "a" * 64,
        "challenges": [],
    }
    payload.update(overrides)
    return payload


def challenge(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "challenge-a1-evidence",
        "kind": "unsupported_claim",
        "claim": "This always works",
        "rationale": "This consequential claim is asserted without supporting evidence.",
        "provenance": "user",
        "evidence_needed": "repository inspection or a cited external source",
        "status": "unresolved",
        "response": "",
        "response_provenance": "",
    }
    item.update(overrides)
    return item


def test_session_verbs_are_exactly_the_implemented_capture_verbs() -> None:
    assert SESSION_VERBS == ("start", "resume", "status", "append", "resolve", "finalize")


def test_start_builds_argv_only_command_with_prompt() -> None:
    command = build_session_command(Path("/p"), "FEAT-018", "start", prompt="Plan the thing")

    assert command == [
        "uv", "run", "coherence", "plan", "start",
        "--project-root", str(Path("/p")),
        "--run-id", "FEAT-018",
        "--prompt", "Plan the thing",
        "--json",
    ]


def test_append_passes_each_field_as_its_own_argv_token() -> None:
    command = build_session_command(
        Path("/p"), "run-001", "append",
        answer_id="a3", question="What breaks?", text="Nothing", source="intent-review-agent",
    )

    assert command[command.index("--answer-id") + 1] == "a3"
    assert command[command.index("--question") + 1] == "What breaks?"
    assert command[command.index("--text") + 1] == "Nothing"
    assert command[command.index("--source") + 1] == "intent-review-agent"


def test_unsupported_verb_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported planning session verb"):
        build_session_command(Path("/p"), "run-001", "adopt")


def test_parse_accepts_ok_payload_with_challenges() -> None:
    payload = session_payload(challenges=[challenge()])

    assert parse_session_response(json.dumps(payload), "run-001") == payload


def test_parse_returns_operation_failure_without_raising() -> None:
    payload = {"schema": 1, "run_id": "run-001", "ok": False, "error": "session already exists"}

    assert parse_session_response(json.dumps(payload), "run-001")["ok"] is False


@pytest.mark.parametrize(
    "payload",
    [
        session_payload(schema=2),
        session_payload(run_id="other"),
        session_payload(ok="yes"),
        session_payload(state="handoff_ready"),
        session_payload(state="spec_authoring"),
        session_payload(next_sequence=0),
        session_payload(journal_sha256=""),
        session_payload(challenges="none"),
        session_payload(challenges=[{"id": "c1"}]),
        {"schema": 1, "run_id": "run-001", "ok": False, "error": ""},
    ],
)
def test_parse_rejects_off_contract_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid planning session response"):
        parse_session_response(json.dumps(payload), "run-001")


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null"])
def test_parse_rejects_non_objects(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid planning session response"):
        parse_session_response(raw, "run-001")


def test_run_session_command_returns_validated_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = session_payload(state="intent_provisional")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert run_session_command(Path("/p"), "run-001", "finalize", status="provisional") == payload


def test_run_session_command_rejects_unsafe_run_id_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(BackendError, match="safe run-id grammar"):
        run_session_command(Path("/p"), "../escape", "status")

    assert calls == []


def test_run_session_command_wraps_malformed_payload_as_backend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=0, stdout="{bad", stderr=""),
    )

    with pytest.raises(BackendError, match="invalid planning session response"):
        run_session_command(Path("/p"), "run-001", "status")
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: FAIL — `ModuleNotFoundError: No module named 'coherence.planning.guided_entrypoint'`

- [ ] **Step 3: Implement the minimal code to make the test pass**

```python
# src/coherence/planning/guided_entrypoint.py
"""Capture-stage verbs for the guided planning entrypoint.

``legal_actions_adapter`` *renders* the read-only projection; this module
*drives* the capture session. It exposes only the six verbs ``session.py``
actually implements, and validates every response against the contract in
``cli.py::_session_command`` before a host sees it.

Semantic work is deliberately absent here. Which question to ask, whether an
answer is adequate, and which resolution applies are host/model and human
decisions; this module transports them and refuses malformed traffic. It never
originates a planning decision and never mints consent (SR-044).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from coherence.planning.adapter_backend import (
    BackendError,
    invoke_backend,
    require_safe_run_id,
)

SESSION_VERBS = ("start", "resume", "status", "append", "resolve", "finalize")

_VERB_FIELDS: dict[str, tuple[str, ...]] = {
    "start": ("prompt",),
    "resume": (),
    "status": (),
    "append": ("answer_id", "question", "text", "source"),
    "resolve": ("challenge_id", "resolution", "response", "provenance"),
    "finalize": ("status",),
}

#: The only states ``session.py::_project`` can produce. A payload claiming any
#: other state means backend drift; fail closed rather than let a host render
#: invented progress through stages that have no implementation.
_SESSION_STATES = frozenset({"capture", "intent_provisional", "blocked"})

_CHALLENGE_FIELDS = (
    "id", "kind", "claim", "rationale", "provenance",
    "evidence_needed", "status", "response", "response_provenance",
)


def build_session_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> list[str]:
    """Build the argv-only backend invocation for one session verb."""
    if verb not in _VERB_FIELDS:
        raise ValueError(f"unsupported planning session verb: {verb}")
    command = [
        "uv", "run", "coherence", "plan", verb,
        "--project-root", str(project_root),
        "--run-id", run_id,
    ]
    for name in _VERB_FIELDS[verb]:
        command.extend([f"--{name.replace('_', '-')}", fields[name]])
    command.append("--json")
    return command


def parse_session_response(raw: str, run_id: str) -> dict[str, Any]:
    """Validate one session verb's JSON response for both outcomes.

    ``ok: true`` (the verb succeeded) and ``ok: false`` (it failed for a real
    reason the host must relay) are both returned. Anything malformed,
    run-id-mismatched, or off-contract raises ``ValueError``.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid planning session response") from exc

    if (
        not isinstance(payload, dict)
        or type(payload.get("schema")) is not int
        or payload["schema"] != 1
        or payload.get("run_id") != run_id
        or not isinstance(payload.get("ok"), bool)
    ):
        raise ValueError("invalid planning session response")

    if payload["ok"] is False:
        if not isinstance(payload.get("error"), str) or not payload["error"]:
            raise ValueError("invalid planning session response")
        return payload

    if (
        payload.get("state") not in _SESSION_STATES
        or type(payload.get("next_sequence")) is not int
        or payload["next_sequence"] < 1
        or not isinstance(payload.get("journal_sha256"), str)
        or not payload["journal_sha256"]
        or not isinstance(payload.get("challenges"), list)
    ):
        raise ValueError("invalid planning session response")

    for item in payload["challenges"]:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) for field in _CHALLENGE_FIELDS
        ):
            raise ValueError("invalid planning session response")
    return payload


def run_session_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> dict[str, Any]:
    """Invoke one session verb and return its validated payload."""
    require_safe_run_id(run_id)
    _, stdout = invoke_backend(build_session_command(project_root, run_id, verb, **fields), project_root)
    try:
        return parse_session_response(stdout, run_id)
    except ValueError as exc:
        raise BackendError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence-plan-guided")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in SESSION_VERBS:
        command = sub.add_parser(verb)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", default=".", type=Path)
        if verb == "start":
            command.add_argument("--prompt", required=True)
        elif verb == "append":
            command.add_argument("--answer-id", required=True)
            command.add_argument("--question", required=True)
            command.add_argument("--text", required=True)
            command.add_argument("--source", default="user")
        elif verb == "resolve":
            command.add_argument("--challenge-id", required=True)
            command.add_argument(
                "--resolution", required=True, choices=("resolve", "revise", "defer", "accept")
            )
            command.add_argument("--response", required=True)
            command.add_argument("--provenance", default="user")
        elif verb == "finalize":
            command.add_argument(
                "--status", required=True, choices=("provisional", "cancelled", "needs_user")
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit 0: the printed JSON is trustworthy -- read ``ok`` to decide what is next.

    Exit 1: nothing trustworthy was obtained. Exit 2: usage error.
    """
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    fields = {name: getattr(args, name) for name in _VERB_FIELDS[args.verb]}
    try:
        payload = run_session_command(Path(args.project_root), args.run_id, args.verb, **fields)
    except BackendError as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


__all__ = [
    "SESSION_VERBS",
    "build_session_command",
    "main",
    "parse_session_response",
    "run_session_command",
]


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 5: Add the CLI tests**

```python
from coherence.planning.guided_entrypoint import main


def test_main_prints_payload_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = session_payload(challenges=[challenge()])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert main(["status", "--run-id", "run-001", "--project-root", "."]) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_main_exits_zero_for_operation_error_so_the_host_can_react(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"schema": 1, "run_id": "run-001", "ok": False, "error": "state is stale or missing"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=1))

    assert main(["status", "--run-id", "run-001"]) == 0
    assert json.loads(capsys.readouterr().out)["error"] == "state is stale or missing"


def test_main_exits_one_when_nothing_is_trustworthy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({}, returncode=9, stderr="boom")
    )

    assert main(["status", "--run-id", "run-001"]) == 1
    assert "boom" in json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["adopt", "--run-id", "run-001"],
        ["start", "--run-id", "run-001"],
        ["finalize", "--run-id", "run-001", "--status", "adopted"],
        ["resolve", "--run-id", "r", "--challenge-id", "c", "--resolution", "approve",
         "--response", "ok"],
    ],
)
def test_main_usage_errors_exit_two(argv: list[str]) -> None:
    assert main(argv) == 2
```

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/coherence/planning/guided_entrypoint.py tests/unit/coherence/test_planning_guided.py
git commit -m "feat(planning): add guided capture-session verbs and CLI

SR: SR-065"
```

---

### Task 3: Artifact navigator

**Files:**
- Create: `src/coherence/planning/artifact_navigator.py`
- Test: `tests/unit/coherence/test_artifact_navigator.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure file reads)
- Produces: `resolve_feature_context(project_root: Path, feature_id: str) -> dict[str, Any]`; `seed_prompt(context: dict[str, Any]) -> str`; `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/coherence/test_artifact_navigator.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.planning.artifact_navigator import (
    resolve_feature_context,
    seed_prompt,
)

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    _write(
        tmp_path / "docs/features/FEAT-018.md",
        "---\n"
        "id: FEAT-018\n"
        'title: "WIDGET-PIPELINE"\n'
        "description: Widgets flow from intake to dispatch.\n"
        "status: draft\n"
        "authority_spec: docs/superpowers/specs/widget-design.md\n"
        "implementation_plan: docs/superpowers/plans/widget-plan.md\n"
        "requirements:\n  - SR-090\n  - SR-091\n"
        "---\n\n# FEAT-018\n",
    )
    _write(
        tmp_path / "requirements/SR-090.md",
        "---\nid: SR-090\ntitle: \"Widget intake\"\n"
        'statement: "The system shall accept widgets."\ndomain: behavioral\n---\n\n'
        "> Status: proposed; semantic adoption remains subject to human consent.\n",
    )
    _write(tmp_path / "docs/superpowers/specs/widget-design.md", "# Widget design\n")
    return tmp_path


def test_resolves_feature_frontmatter_verbatim(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")

    assert context["title"] == "WIDGET-PIPELINE"
    assert context["description"] == "Widgets flow from intake to dispatch."
    assert context["status"] == "draft"
    assert context["feature_path"] == "docs/features/FEAT-018.md"


def test_resolves_each_requirement_with_its_statement_and_presence(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")
    by_id = {item["id"]: item for item in context["requirements"]}

    assert by_id["SR-090"]["present"] is True
    assert by_id["SR-090"]["statement"] == "The system shall accept widgets."
    assert "proposed" in by_id["SR-090"]["status_note"]
    assert by_id["SR-091"]["present"] is False
    assert by_id["SR-091"]["statement"] is None


def test_reports_drafted_and_missing_artifacts_without_erroring(project: Path) -> None:
    context = resolve_feature_context(project, "FEAT-018")

    assert context["authority_spec"]["present"] is True
    assert context["implementation_plan"]["present"] is False
    assert context["bundle"]["present"] is False
    assert "docs/superpowers/plans/widget-plan.md" in context["missing"]
    assert "requirements/SR-091.md" in context["missing"]


def test_unknown_feature_is_reported_not_raised(tmp_path: Path) -> None:
    context = resolve_feature_context(tmp_path, "FEAT-777")

    assert context["present"] is False
    assert context["requirements"] == []


@pytest.mark.parametrize("feature_id", ["", "FEAT-18", "feat-018", "../escape", "FEAT-018;rm"])
def test_unsafe_or_malformed_feature_ids_are_rejected(tmp_path: Path, feature_id: str) -> None:
    with pytest.raises(ValueError, match="feature_id"):
        resolve_feature_context(tmp_path, feature_id)


def test_seed_prompt_quotes_the_feature_verbatim_without_paraphrase(project: Path) -> None:
    prompt = seed_prompt(resolve_feature_context(project, "FEAT-018"))

    assert "FEAT-018" in prompt
    assert "WIDGET-PIPELINE" in prompt
    assert "Widgets flow from intake to dispatch." in prompt
    assert "docs/features/FEAT-018.md" in prompt
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_artifact_navigator.py -q -o addopts=''`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the minimal code to make the test pass**

```python
# src/coherence/planning/artifact_navigator.py
"""Read-only resolution of a feature's already-drafted artifact graph.

Planning should start from what the repository already says, not from a blank
prompt. Given ``FEAT-NNN`` this walks the graph the frontmatter already encodes
-- feature -> requirements -> authority spec -> implementation plan -> bundle --
and reports each artifact's content **verbatim** alongside whether it exists yet.

Nothing here paraphrases, summarizes, or interprets. A model reading this output
is reading the repository's own words, so seeded intent cannot drift from the
drafted record. Missing artifacts are reported as missing, never as an error:
"not drafted yet" is the normal state early in a feature's life.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

FEATURE_ID = re.compile(r"^FEAT-\d{3}$")
REQUIREMENT_ID = re.compile(r"^SR-\d{3}$")
_STATUS_NOTE = re.compile(r"^>\s*Status:\s*(.+)$", re.MULTILINE)


def _frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Return `(frontmatter, body)`; `({}, "")` when absent or unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}, ""
    if not text.startswith("---\n"):
        return {}, text
    _, _, remainder = text.partition("---\n")
    raw, separator, body = remainder.partition("\n---")
    if not separator:
        return {}, text
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}, body
    return (loaded if isinstance(loaded, dict) else {}), body


def _artifact(project_root: Path, relative: str | None) -> dict[str, Any]:
    if not relative or not isinstance(relative, str):
        return {"path": None, "present": False}
    return {"path": relative, "present": (project_root / relative).is_file()}


def _requirement(project_root: Path, requirement_id: str) -> dict[str, Any]:
    relative = f"requirements/{requirement_id}.md"
    path = project_root / relative
    if not path.is_file():
        return {
            "id": requirement_id, "path": relative, "present": False,
            "title": None, "statement": None, "status_note": None, "acceptance": [],
        }
    meta, body = _frontmatter(path)
    note = _STATUS_NOTE.search(body)
    acceptance = meta.get("acceptance")
    return {
        "id": requirement_id,
        "path": relative,
        "present": True,
        "title": meta.get("title"),
        "statement": meta.get("statement"),
        "status_note": note.group(1).strip() if note else None,
        "acceptance": acceptance if isinstance(acceptance, list) else [],
    }


def resolve_feature_context(project_root: Path, feature_id: str) -> dict[str, Any]:
    """Resolve everything already drafted for `feature_id`, verbatim."""
    if not isinstance(feature_id, str) or FEATURE_ID.fullmatch(feature_id) is None:
        raise ValueError("feature_id must look like FEAT-NNN")

    relative = f"docs/features/{feature_id}.md"
    path = project_root / relative
    context: dict[str, Any] = {
        "schema": 1,
        "feature_id": feature_id,
        "feature_path": relative,
        "present": path.is_file(),
        "title": None,
        "description": None,
        "status": None,
        "requirements": [],
        "authority_spec": {"path": None, "present": False},
        "implementation_plan": {"path": None, "present": False},
        "bundle": _artifact(project_root, f"bundles/{feature_id}.json"),
        "missing": [],
    }
    if not context["present"]:
        context["missing"] = [relative]
        return context

    meta, _ = _frontmatter(path)
    context["title"] = meta.get("title")
    context["description"] = meta.get("description")
    context["status"] = meta.get("status")
    context["authority_spec"] = _artifact(project_root, meta.get("authority_spec"))
    context["implementation_plan"] = _artifact(project_root, meta.get("implementation_plan"))

    declared = meta.get("requirements")
    for requirement_id in declared if isinstance(declared, list) else []:
        if isinstance(requirement_id, str) and REQUIREMENT_ID.fullmatch(requirement_id):
            context["requirements"].append(_requirement(project_root, requirement_id))

    context["missing"] = [
        item["path"]
        for item in (
            *context["requirements"],
            context["authority_spec"],
            context["implementation_plan"],
            context["bundle"],
        )
        if item["path"] and not item["present"]
    ]
    return context


def seed_prompt(context: dict[str, Any]) -> str:
    """Compose the capture seed from the feature's own words, never a paraphrase."""
    if not context.get("present"):
        raise ValueError(f"{context['feature_id']} has no drafted feature document")
    return (
        f"Plan {context['feature_id']} ({context['title']}): {context['description']} "
        f"[source: {context['feature_path']}]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coherence-plan-navigate")
    parser.add_argument("feature_id")
    parser.add_argument("--project-root", default=".", type=Path)
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    try:
        context = resolve_feature_context(Path(args.project_root), args.feature_id)
    except ValueError as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(context, indent=2, ensure_ascii=False))
    return 0


__all__ = ["FEATURE_ID", "main", "resolve_feature_context", "seed_prompt"]


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_artifact_navigator.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 5: Verify against the real repository**

Run: `rtk proxy uv run python -m coherence.planning.artifact_navigator FEAT-017 --project-root .`
Expected: `title: "PLANNING-BOOTSTRAP"`, all eight SRs resolved with statements, `authority_spec.present: true`, `bundle.present: true`.

Run: `rtk proxy uv run python -m coherence.planning.artifact_navigator FEAT-018 --project-root .`
Expected: resolves, and reports `bundles/FEAT-018.json` under `missing` rather than erroring.

- [ ] **Step 6: Commit**

```bash
git add src/coherence/planning/artifact_navigator.py tests/unit/coherence/test_artifact_navigator.py
git commit -m "feat(planning): resolve a feature's drafted artifact graph verbatim

SR: SR-065"
```

---

### Task 4: Pipeline verbs (bootstrap / check / review / handoff)

**Files:**
- Create: `src/coherence/planning/guided_pipeline.py`
- Test: `tests/unit/coherence/test_planning_guided.py`

**Interfaces:**
- Consumes: `adapter_backend.{BackendError, invoke_backend, require_safe_run_id}`
- Produces: `PIPELINE_VERBS: tuple[str, ...]`; `build_pipeline_command(project_root: Path, run_id: str, verb: str, **fields: str) -> list[str]`; `run_pipeline_command(project_root: Path, run_id: str, verb: str, **fields: str) -> tuple[int, dict[str, Any]]`; `main(argv) -> int`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/coherence/test_planning_guided.py`:

```python
from coherence.planning.guided_pipeline import (
    PIPELINE_VERBS,
    build_pipeline_command,
    run_pipeline_command,
)


def test_pipeline_verbs_are_the_implemented_compile_and_handoff_verbs() -> None:
    assert PIPELINE_VERBS == ("bootstrap", "check", "review", "handoff")


def test_bootstrap_passes_all_three_artifacts_and_decompose() -> None:
    command = build_pipeline_command(
        Path("/p"), "FEAT-018", "bootstrap",
        intent=".intent/intent.json",
        spec="docs/superpowers/specs/s.md",
        plan="docs/superpowers/plans/p.md",
        decompose="true",
    )

    assert command[:5] == ["uv", "run", "coherence", "plan", "bootstrap"]
    assert command[command.index("--intent") + 1] == ".intent/intent.json"
    assert command[command.index("--spec") + 1] == "docs/superpowers/specs/s.md"
    assert command[command.index("--plan") + 1] == "docs/superpowers/plans/p.md"
    assert "--decompose" in command


def test_bootstrap_omits_decompose_flag_when_not_requested() -> None:
    command = build_pipeline_command(
        Path("/p"), "FEAT-018", "bootstrap", intent="i", spec="s", plan="p", decompose="false"
    )

    assert "--decompose" not in command


def test_handoff_carries_the_workflow_selection() -> None:
    command = build_pipeline_command(
        Path("/p"), "FEAT-018", "handoff", workflow="standard-development"
    )

    assert command[command.index("--workflow") + 1] == "standard-development"


def test_pipeline_exit_one_is_findings_data_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {"ok": False, "findings": [{"code": "PLAN_TASK_PARITY"}]}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(report, returncode=1))

    code, payload = run_pipeline_command(
        Path("/p"), "FEAT-018", "check", intent="i", spec="s", plan="p"
    )

    assert code == 1
    assert payload["findings"][0]["code"] == "PLAN_TASK_PARITY"


def test_pipeline_untrusted_exit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({"ok": True}, returncode=7, stderr="bad")
    )

    with pytest.raises(BackendError, match="bad"):
        run_pipeline_command(Path("/p"), "FEAT-018", "review")


def test_pipeline_rejects_unsafe_run_id_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(BackendError, match="safe run-id grammar"):
        run_pipeline_command(Path("/p"), "run 001", "review")

    assert calls == []


def test_pipeline_rejects_non_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=0, stdout="not json", stderr=""),
    )

    with pytest.raises(BackendError, match="invalid planning pipeline response"):
        run_pipeline_command(Path("/p"), "FEAT-018", "review")
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_guided.py -q -o addopts=''`
Expected: FAIL — `ModuleNotFoundError: No module named 'coherence.planning.guided_pipeline'`

- [ ] **Step 3: Implement the minimal code to make the test pass**

```python
# src/coherence/planning/guided_pipeline.py
"""Compile-and-handoff verbs for the guided planning entrypoint.

Where ``guided_entrypoint`` drives intent capture, this module drives what
happens to authored artifacts afterwards: ``bootstrap`` (validate the
intent/spec/plan triple and, with ``--decompose``, generate ``tasks/T-NNN.md``
from the plan), ``check`` (structural parity and task metadata), ``review``, and
``handoff``.

The division of labour matters. Authoring the spec and the plan is model work --
no backend command writes them, and none can. Deciding whether the decomposition
is *structurally* sound is backend work, and it is deterministic. This module
carries artifacts to the backend and carries findings back; it judges nothing.

Exit code 1 from these verbs means "findings present" or "blocked", which is a
result, not a failure -- callers receive the code alongside the payload so they
can tell the difference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from coherence.planning.adapter_backend import (
    BackendError,
    invoke_backend,
    require_safe_run_id,
)

PIPELINE_VERBS = ("bootstrap", "check", "review", "handoff")

_VERB_FIELDS: dict[str, tuple[str, ...]] = {
    "bootstrap": ("intent", "spec", "plan"),
    "check": ("intent", "spec", "plan"),
    "review": (),
    "handoff": ("workflow",),
}


def build_pipeline_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> list[str]:
    """Build the argv-only backend invocation for one pipeline verb."""
    if verb not in _VERB_FIELDS:
        raise ValueError(f"unsupported planning pipeline verb: {verb}")
    command = [
        "uv", "run", "coherence", "plan", verb,
        "--project-root", str(project_root),
        "--run-id", run_id,
    ]
    for name in _VERB_FIELDS[verb]:
        command.extend([f"--{name}", fields[name]])
    if verb == "bootstrap" and fields.get("decompose") == "true":
        command.append("--decompose")
    command.append("--json")
    return command


def run_pipeline_command(
    project_root: Path, run_id: str, verb: str, **fields: str
) -> tuple[int, dict[str, Any]]:
    """Invoke one pipeline verb; return `(exit_code, payload)`.

    Exit code 1 means the backend reported findings or a block -- real data the
    caller must act on, not a crash.
    """
    require_safe_run_id(run_id)
    code, stdout = invoke_backend(
        build_pipeline_command(project_root, run_id, verb, **fields), project_root
    )
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BackendError("invalid planning pipeline response") from exc
    if not isinstance(payload, dict):
        raise BackendError("invalid planning pipeline response")
    return code, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence-plan-pipeline")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in PIPELINE_VERBS:
        command = sub.add_parser(verb)
        command.add_argument("--run-id", required=True)
        command.add_argument("--project-root", default=".", type=Path)
        if verb in ("bootstrap", "check"):
            command.add_argument("--intent", required=True)
            command.add_argument("--spec", required=True)
            command.add_argument("--plan", required=True)
        if verb == "bootstrap":
            command.add_argument("--decompose", action="store_true")
        if verb == "handoff":
            command.add_argument("--workflow", default="standard-development")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit 0: trustworthy payload printed. Exit 1: untrustworthy. Exit 2: usage.

    A payload reporting findings still exits 0 -- findings are content.
    """
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    fields = {name: getattr(args, name) for name in _VERB_FIELDS[args.verb]}
    if args.verb == "bootstrap":
        fields["decompose"] = "true" if args.decompose else "false"
    try:
        code, payload = run_pipeline_command(
            Path(args.project_root), args.run_id, args.verb, **fields
        )
    except BackendError as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"backend_exit_code": code, **payload}, indent=2, ensure_ascii=False))
    return 0


__all__ = ["PIPELINE_VERBS", "build_pipeline_command", "main", "run_pipeline_command"]


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and lint**

Run: `rtk proxy uv run pytest tests/unit/coherence -q -o addopts=''`
Expected: PASS
Run: `rtk proxy uv run ruff check src/coherence/planning tests/unit/coherence`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add src/coherence/planning/guided_pipeline.py tests/unit/coherence/test_planning_guided.py
git commit -m "feat(planning): add bootstrap/check/review/handoff pipeline verbs

SR: SR-065"
```

---

### Task 5: Deterministic hooks — channel guard and finalize gate

**Files:**
- Create: `.claude/hooks/coherence_channel_guard.py`
- Create: `.claude/hooks/coherence_finalize_gate.py`
- Test: `tests/unit/coherence/test_planning_hooks.py`

**Interfaces:**
- Produces: `coherence_channel_guard.decide(command: str) -> str | None` (deny reason, or `None` to allow); `coherence_finalize_gate.decide(project_root: Path, command: str) -> str | None`
- Both hook scripts read the Claude Code hook event JSON on stdin and emit a `PreToolUse` decision object.

**Design note — why these two and nothing more:** a hook may only enforce *procedural* facts. The channel guard checks "did this call use the sanctioned adapter?" The finalize gate checks "does the required review record exist, and is every raised challenge dispositioned?" Neither judges whether any content is any good. Both answers are derived from files on disk, never from the model's claims.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/coherence/test_planning_hooks.py
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

HOOKS = Path(__file__).parents[3] / ".claude" / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load("coherence_channel_guard")


@pytest.fixture(scope="module")
def gate():
    return _load("coherence_finalize_gate")


# --- channel guard -------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    ["ls -la", "git status", "rtk proxy uv run pytest -q", "echo coherence is a word"],
)
def test_guard_allows_unrelated_commands(guard, command: str) -> None:
    assert guard.decide(command) is None


@pytest.mark.parametrize(
    "verb", ["start", "resume", "append", "resolve", "finalize", "bootstrap", "check", "handoff"]
)
def test_guard_denies_direct_backend_planning_calls(guard, verb: str) -> None:
    reason = guard.decide(f"uv run coherence plan {verb} --run-id r --project-root .")

    assert reason is not None
    assert "adapter" in reason


@pytest.mark.parametrize(
    "command",
    [
        "uv run python -m coherence.planning.guided_entrypoint start --run-id r --prompt p",
        "uv run python -m coherence.planning.guided_pipeline check --run-id r --intent i "
        "--spec s --plan p",
        "uv run python -m coherence.planning.legal_actions_adapter r",
        "uv run python -m coherence.planning.artifact_navigator FEAT-018",
    ],
)
def test_guard_allows_the_sanctioned_adapters(guard, command: str) -> None:
    assert guard.decide(command) is None


def test_guard_denies_planning_verbs_outside_the_implemented_set(guard) -> None:
    assert guard.decide("uv run coherence plan adopt --run-id r") is not None


# --- finalize gate -------------------------------------------------------


def _journal(root: Path, run_id: str, events: list[dict]) -> None:
    path = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )


def _answer(sequence: int, source: str) -> dict:
    return {
        "run_id": "FEAT-018", "sequence": sequence, "kind": "answer_captured",
        "payload": {"id": f"a{sequence}", "question": "q", "text": "t", "source": source},
    }


FINALIZE = (
    "uv run python -m coherence.planning.guided_entrypoint finalize "
    "--run-id FEAT-018 --project-root . --status provisional"
)


def test_gate_ignores_commands_that_are_not_finalize(gate, tmp_path: Path) -> None:
    assert gate.decide(tmp_path, "uv run python -m coherence.planning.guided_entrypoint status "
                                 "--run-id FEAT-018") is None


def test_gate_denies_when_no_review_record_exists(gate, tmp_path: Path) -> None:
    _journal(tmp_path, "FEAT-018", [
        {"run_id": "FEAT-018", "sequence": 1, "kind": "capture_started", "payload": {"prompt": "p"}},
        _answer(2, "user"),
    ])

    reason = gate.decide(tmp_path, FINALIZE)

    assert reason is not None
    assert "intent-review-agent" in reason


def test_gate_allows_once_the_review_verdict_is_recorded(gate, tmp_path: Path) -> None:
    _journal(tmp_path, "FEAT-018", [
        {"run_id": "FEAT-018", "sequence": 1, "kind": "capture_started", "payload": {"prompt": "p"}},
        _answer(2, "user"),
        _answer(3, "intent-review-agent"),
    ])

    assert gate.decide(tmp_path, FINALIZE) is None


def test_gate_denies_while_a_raised_challenge_has_no_disposition(gate, tmp_path: Path) -> None:
    _journal(tmp_path, "FEAT-018", [
        {"run_id": "FEAT-018", "sequence": 1, "kind": "capture_started", "payload": {"prompt": "p"}},
        _answer(2, "intent-review-agent"),
        {"run_id": "FEAT-018", "sequence": 3, "kind": "challenge_raised",
         "payload": {"id": "challenge-a2-evidence"}},
    ])

    reason = gate.decide(tmp_path, FINALIZE)

    assert reason is not None
    assert "challenge-a2-evidence" in reason


def test_gate_allows_once_every_challenge_is_dispositioned(gate, tmp_path: Path) -> None:
    _journal(tmp_path, "FEAT-018", [
        {"run_id": "FEAT-018", "sequence": 1, "kind": "capture_started", "payload": {"prompt": "p"}},
        _answer(2, "intent-review-agent"),
        {"run_id": "FEAT-018", "sequence": 3, "kind": "challenge_raised",
         "payload": {"id": "challenge-a2-evidence"}},
        {"run_id": "FEAT-018", "sequence": 4, "kind": "challenge_resolved",
         "payload": {"id": "challenge-a2-evidence", "resolution": "defer"}},
    ])

    assert gate.decide(tmp_path, FINALIZE) is None


def test_gate_denies_when_the_journal_is_missing_entirely(gate, tmp_path: Path) -> None:
    assert gate.decide(tmp_path, FINALIZE) is not None


def test_gate_refuses_an_unsafe_run_id_rather_than_reading_a_path(gate, tmp_path: Path) -> None:
    reason = gate.decide(
        tmp_path,
        "uv run python -m coherence.planning.guided_entrypoint finalize "
        "--run-id ../../etc --status provisional",
    )

    assert reason is not None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_hooks.py -q -o addopts=''`
Expected: FAIL — the hook files do not exist.

- [ ] **Step 3: Implement the channel guard**

```python
# .claude/hooks/coherence_channel_guard.py
"""PreToolUse hook: keep planning traffic on the sanctioned adapter channel.

The adapters own run-id validation, argv-only invocation, exit-code
interpretation, and payload validation. A direct `uv run coherence plan ...`
call from the model bypasses all of it, so this hook denies those calls and
tells the model which entry point to use instead.

This is deliberately the *only* thing this hook decides. It checks the shape of
the call, never the merit of what is being planned -- a hook cannot judge
semantics, and pretending otherwise would trade real assurance for the
appearance of it.
"""

from __future__ import annotations

import json
import re
import sys

#: Planning verbs that must be reached through an adapter module.
_BACKEND_CALL = re.compile(r"coherence\s+plan\s+([a-z-]+)")

_ADAPTER_MODULES = (
    "coherence.planning.guided_entrypoint",
    "coherence.planning.guided_pipeline",
    "coherence.planning.legal_actions_adapter",
    "coherence.planning.artifact_navigator",
)

_REASON = (
    "Direct `coherence plan {verb}` calls bypass the validated adapter "
    "(run-id grammar, argv-only invocation, exit-code contract, payload "
    "validation). Use `uv run python -m coherence.planning.guided_entrypoint "
    "{verb} ...` for capture verbs or `...guided_pipeline {verb} ...` for "
    "bootstrap/check/review/handoff."
)


def decide(command: str) -> str | None:
    """Return a deny reason for `command`, or None to leave it alone."""
    if "coherence" not in command:
        return None
    if any(module in command for module in _ADAPTER_MODULES):
        return None
    match = _BACKEND_CALL.search(command)
    if match is None:
        return None
    return _REASON.format(verb=match.group(1))


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0  # never block because our own parsing failed
    command = str((event.get("tool_input") or {}).get("command", ""))
    reason = decide(command)
    if reason is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Implement the finalize gate**

```python
# .claude/hooks/coherence_finalize_gate.py
"""PreToolUse hook: `finalize` requires recorded review work, not a promise.

This gate enforces two *procedural* facts, both read straight from the run's
append-only journal:

1. an intent review ran and recorded its verdict (an `answer_captured` event
   whose `source` is `intent-review-agent`);
2. every `challenge_raised` has a matching `challenge_resolved`.

It deliberately does **not** evaluate whether the captured intent is any good.
That judgment belongs to the review agent and the human. What a hook can know --
and all it should claim -- is whether the required records exist. Gating on a
semantic guess (for example the keyword output of `detect_challenges` alone)
would produce false confidence, because that matcher misses any unsupported
claim phrased without its trigger words.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_FINALIZE = re.compile(r"coherence\.planning\.guided_entrypoint\s+finalize\b")
_RUN_ID = re.compile(r"--run-id[= ]+(\S+)")
_PROJECT_ROOT = re.compile(r"--project-root[= ]+(\S+)")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

REVIEW_SOURCE = "intent-review-agent"


def _events(journal: Path) -> list[dict] | None:
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    events: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return None
        if isinstance(value, dict):
            events.append(value)
    return events


def decide(project_root: Path, command: str) -> str | None:
    """Return a deny reason for a finalize `command`, or None to allow it."""
    if _FINALIZE.search(command) is None:
        return None

    run_match = _RUN_ID.search(command)
    if run_match is None or _SAFE_RUN_ID.fullmatch(run_match.group(1)) is None:
        return "finalize requires a --run-id matching ^[A-Za-z0-9][A-Za-z0-9._-]*$"
    run_id = run_match.group(1)

    root_match = _PROJECT_ROOT.search(command)
    root = project_root / root_match.group(1) if root_match else project_root

    journal = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    events = _events(journal)
    if events is None:
        return (
            f"No readable capture journal for run {run_id}. Finalize is blocked until the "
            "run has been started and its capture recorded."
        )

    reviewed = any(
        event.get("kind") == "answer_captured"
        and (event.get("payload") or {}).get("source") == REVIEW_SOURCE
        for event in events
    )
    if not reviewed:
        return (
            f"Run {run_id} has no recorded intent review. Dispatch the review agent and record "
            f"its verdict with `append --source {REVIEW_SOURCE}` (record it even when the "
            "verdict is 'no findings'), then finalize."
        )

    raised = {
        (event.get("payload") or {}).get("id")
        for event in events
        if event.get("kind") == "challenge_raised"
    }
    resolved = {
        (event.get("payload") or {}).get("id")
        for event in events
        if event.get("kind") == "challenge_resolved"
    }
    outstanding = sorted(item for item in raised - resolved if item)
    if outstanding:
        return (
            "These challenges have no recorded human disposition: "
            f"{', '.join(outstanding)}. Each needs an explicit resolve/revise/defer/accept "
            "chosen by the human before finalize."
        )
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    command = str((event.get("tool_input") or {}).get("command", ""))
    reason = decide(Path(event.get("cwd") or "."), command)
    if reason is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_hooks.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks tests/unit/coherence/test_planning_hooks.py
git commit -m "feat(claude-code): add channel-guard and finalize-gate hooks

SR: SR-065"
```

---

### Task 6: Challenge surfacing and hook registration

**Files:**
- Create: `.claude/hooks/coherence_challenge_surface.py`
- Create: `.claude/settings.json`
- Test: `tests/unit/coherence/test_planning_hooks.py`

**Interfaces:**
- Consumes: the two hooks from Task 5
- Produces: `coherence_challenge_surface.summarize(payload: dict) -> str | None`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/coherence/test_planning_hooks.py`:

```python
@pytest.fixture(scope="module")
def surface():
    return _load("coherence_challenge_surface")


def test_surface_reports_nothing_when_no_challenge_is_unresolved(surface) -> None:
    payload = {"ok": True, "challenges": [{"id": "c1", "status": "deferred"}]}

    assert surface.summarize(payload) is None


def test_surface_lists_every_unresolved_challenge_verbatim(surface) -> None:
    payload = {
        "ok": True,
        "challenges": [
            {"id": "c1", "status": "unresolved", "kind": "unsupported_claim",
             "claim": "This always works", "rationale": "No evidence.",
             "evidence_needed": "a citation"},
            {"id": "c2", "status": "resolved", "kind": "tradeoff", "claim": "x",
             "rationale": "y", "evidence_needed": "z"},
        ],
    }

    text = surface.summarize(payload)

    assert "c1" in text
    assert "This always works" in text
    assert "a citation" in text
    assert "c2" not in text


def test_surface_ignores_payloads_that_are_not_ok(surface) -> None:
    assert surface.summarize({"ok": False, "error": "boom"}) is None


def test_surface_tolerates_a_malformed_payload(surface) -> None:
    assert surface.summarize({"ok": True, "challenges": "nope"}) is None


def test_settings_register_every_hook() -> None:
    settings = json.loads(
        (Path(__file__).parents[3] / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(settings)

    assert "coherence_channel_guard.py" in serialized
    assert "coherence_finalize_gate.py" in serialized
    assert "coherence_challenge_surface.py" in serialized
    assert '"PreToolUse"' in serialized
    assert '"PostToolUse"' in serialized
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_planning_hooks.py -q -o addopts=''`
Expected: FAIL — the surface hook and settings file do not exist.

- [ ] **Step 3: Implement the challenge surfacing hook**

```python
# .claude/hooks/coherence_challenge_surface.py
"""PostToolUse hook: make raised challenges impossible to quietly skip.

After an `append` or `resolve`, the backend returns the run's full challenge
list. Relying on the model to notice an `unresolved` entry buried in JSON is
exactly the kind of "it usually remembers" assumption this design avoids, so
this hook re-reads the payload and injects the outstanding items as context.

Surfacing only. The hook does not block and does not judge -- whether a
challenge matters, and how to dispose of it, stays with the human.
"""

from __future__ import annotations

import json
import sys

_FIELDS = ("kind", "claim", "rationale", "evidence_needed")


def summarize(payload: dict) -> str | None:
    """Render unresolved challenges as context text, or None when there are none."""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    challenges = payload.get("challenges")
    if not isinstance(challenges, list):
        return None

    lines: list[str] = []
    for item in challenges:
        if not isinstance(item, dict) or item.get("status") != "unresolved":
            continue
        detail = "; ".join(f"{field}: {item.get(field)}" for field in _FIELDS)
        lines.append(f"- {item.get('id')} -- {detail}")
    if not lines:
        return None
    return (
        "Coherence raised challenges that are still unresolved. Present each one to the human "
        "verbatim and ask them to choose resolve/revise/defer/accept plus a response. Do not "
        "choose on their behalf, and do not finalize until each is dispositioned:\n"
        + "\n".join(lines)
    )


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    response = event.get("tool_response") or {}
    raw = response.get("stdout") if isinstance(response, dict) else None
    if not isinstance(raw, str):
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    text = summarize(payload)
    if text is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create `.claude/settings.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python \"$CLAUDE_PROJECT_DIR/.claude/hooks/coherence_channel_guard.py\""
          },
          {
            "type": "command",
            "command": "uv run python \"$CLAUDE_PROJECT_DIR/.claude/hooks/coherence_finalize_gate.py\""
          },
          {
            "type": "agent",
            "if": "Bash(*guided_entrypoint finalize*)",
            "timeout": 240,
            "prompt": "You are the FEAT-017 intent review for a Coherence planning run about to be finalized. Read the run's capture journal at .factory/planning/<run-id>/capture/events.jsonl (the run id is in the command being run) and the materialized .intent/intent.json. Review the captured intent for material gaps: unstated assumptions, unsupported claims that Coherence's keyword matcher would miss, contradictions between answers, scope that is not bounded, and success criteria that are absent or unmeasurable. Record your verdict in the journal by running: uv run python -m coherence.planning.guided_entrypoint append --run-id <run-id> --project-root . --answer-id <a{next_sequence}> --question 'Intent review finding' --text '<finding>' --source intent-review-agent -- record one append per finding, and record a single 'no findings' entry if the capture is adequate. You must never choose a challenge resolution or a terminal capture status; those are human decisions. Return {\"ok\": true} if you recorded your verdict and the capture is adequate to proceed, or {\"ok\": false, \"reason\": \"<what the human still needs to decide or supply>\"} if material gaps remain."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python \"$CLAUDE_PROJECT_DIR/.claude/hooks/coherence_challenge_surface.py\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "If this session ran the /coherence-plan workflow, check for overclaiming: did the assistant state that a planning stage completed without the corresponding backend command actually succeeding, describe progress into a stage Coherence cannot produce (only capture, intent_provisional, and blocked exist), choose a challenge resolution or terminal status on the human's behalf, or claim tasks were generated without a successful bootstrap --decompose? If any of those happened, respond {\"ok\": false, \"reason\": \"<what to correct>\"}. Otherwise respond {\"ok\": true}."
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Verify the agent hook's `if` filter actually scopes correctly**

The `if` glob semantics for agent hooks are not something to assume — an agent hook that fires on *every* Bash call would be slow and expensive.

Run a harmless Bash command (`git status`) in a session with these settings and confirm no agent hook fires. Then run the finalize command and confirm it does.

If the `if` filter does not scope as expected, **do not leave it firing broadly**: replace the `type: "agent"` entry with a `type: "command"` wrapper script that exits 0 immediately unless the command matches finalize, and dispatches the review only when it does. Record which of the two shapes was used in the commit message.

- [ ] **Step 6: Run tests and lint**

Run: `rtk proxy uv run pytest tests/unit/coherence -q -o addopts=''`
Expected: PASS
Run: `rtk proxy uv run ruff check .claude/hooks tests/unit/coherence`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add .claude/hooks/coherence_challenge_surface.py .claude/settings.json tests/unit/coherence/test_planning_hooks.py
git commit -m "feat(claude-code): surface challenges and register planning hooks

SR: SR-065"
```

---

### Task 7: Replace the Claude Code command

**Files:**
- Modify (full replacement): `.claude/commands/coherence-plan.md`
- Create: `tests/unit/coherence/test_coherence_plan_command_contract.py`

- [ ] **Step 1: Write the failing contract test**

```python
# tests/unit/coherence/test_coherence_plan_command_contract.py
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

COMMAND = Path(__file__).parents[3] / ".claude" / "commands" / "coherence-plan.md"


@pytest.fixture(scope="module")
def text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def test_frontmatter_declares_the_argument(text: str) -> None:
    assert text.startswith("---\n")
    assert "argument-hint:" in text


def test_every_stage_uses_an_adapter_module(text: str) -> None:
    for module in ("artifact_navigator", "guided_entrypoint", "guided_pipeline",
                   "legal_actions_adapter"):
        assert f"coherence.planning.{module}" in text


def test_command_never_calls_the_backend_directly(text: str) -> None:
    assert "uv run coherence plan" not in text


def test_human_decisions_are_marked_as_never_the_models(text: str) -> None:
    lowered = text.lower()
    assert "never choose" in lowered
    assert "resolve/revise/defer/accept" in lowered
    assert "provisional" in lowered and "cancelled" in lowered and "needs_user" in lowered


def test_authoring_stages_are_present_with_reviews(text: str) -> None:
    lowered = text.lower()
    assert "author the spec" in lowered
    assert "author the plan" in lowered
    assert lowered.count("subagent") >= 2


def test_decomposition_and_parity_gate_are_present(text: str) -> None:
    assert "--decompose" in text
    assert "PLAN_TASK_PARITY" in text


def test_non_executing_boundary_is_stated(text: str) -> None:
    lowered = text.lower()
    assert "starts_automatically" in lowered
    assert "downstream" in lowered


def test_run_id_grammar_and_usage_message_are_present(text: str) -> None:
    assert "^[A-Za-z0-9][A-Za-z0-9._-]*$" in text
    assert "usage: /coherence-plan <run-id-or-FEAT-NNN>" in text
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_coherence_plan_command_contract.py -q -o addopts=''`
Expected: FAIL

- [ ] **Step 3: Replace `.claude/commands/coherence-plan.md` with this exact content**

````markdown
---
description: Run a Coherence planning workflow for a feature, from intent capture to executable tasks
argument-hint: <run-id-or-FEAT-NNN> [initial planning request]
---

You are driving one Coherence planning run from drafted artifacts to executable
tasks. Coherence owns planning state, hashes, gates, DecisionFiles, consent,
adoption, and the handoff. You supply the semantic work — questions, spec, plan,
reviews — and transport the human's decisions. You never originate a planning
decision and never grant consent.

**Division of authority, which you must not blur:**

- The backend decides *structure*: durability, ordering, hashes, parity,
  decomposition, whether a required record exists.
- You decide *semantics*: what to ask, what the spec says, what the plan says.
- The human decides *every* challenge resolution and terminal status.
- Hooks will block you if you skip a required record. That is expected. Read the
  reason and satisfy it — never work around it.

Only `capture`, `intent_provisional`, and `blocked` exist as backend states.
Never narrate progress into any other state.

All commands run from the repository root with the Bash tool, each value passed
as its own argument. Never build a shell string.

## 1. Resolve the argument

The first token is the run id; anything after it is the initial request.

Require the run id to match `^[A-Za-z0-9][A-Za-z0-9._-]*$`. If it is missing or
malformed, reply exactly this and stop:

```
usage: /coherence-plan <run-id-or-FEAT-NNN>
```

If it looks like `FEAT-NNN`, load what is already drafted:

```
uv run python -m coherence.planning.artifact_navigator <run-id> --project-root .
```

Show the human, verbatim: the feature title/description, each requirement's
statement and status note, and which artifacts are listed under `missing`. Use
this throughout — never ask about something a drafted SR already settles.

## 2. Start or resume

```
uv run python -m coherence.planning.guided_entrypoint status --run-id <run-id> --project-root .
```

Exit 0 means the JSON is trustworthy — read `ok`. Exit 1 means stop and show the
error.

- `ok: true` → run `resume`, report the returned `state` verbatim.
- `ok: false` → the run does not exist. Compose the seed prompt from the feature
  document's own title and description (verbatim, no paraphrase), or ask the
  human for the request if there is no feature document. Confirm the seed with
  them, then:

```
uv run python -m coherence.planning.guided_entrypoint start --run-id <run-id> --project-root . --prompt <seed>
```

## 3. Capture loop

Coherence does not generate questions. Its `detect_challenges` is a keyword
tripwire (`always`, `never`, `only`, `must use`, and a few more) — it catches
some sloppy phrasing and misses most real gaps. **Treat it as a hint, never as
coverage.** Deciding what is still unclear is your job.

Repeat until the human says capture is complete:

1. Ask **one** clarifying question. Wait. Never answer for them.
2. Record it, using `a<next_sequence>` from the most recent payload:

```
uv run python -m coherence.planning.guided_entrypoint append --run-id <run-id> --project-root . --answer-id a<next_sequence> --question <question> --text <their answer> --source user
```

3. A hook will inject any unresolved challenges. Handle each per step 4 before
   asking anything else.

Chaining `append` needs no permission — the human consented by answering.

## 4. Resolve a challenge — never choose

Show the challenge exactly as returned: `kind`, `claim`, `rationale`,
`evidence_needed`. Do not soften or summarize it.

Ask the human for the resolution — `resolve`, `revise`, `defer`, or `accept` —
and their response text. Wait. **Never choose the resolution yourself** and never
infer it from earlier conversation.

```
uv run python -m coherence.planning.guided_entrypoint resolve --run-id <run-id> --project-root . --challenge-id <id> --resolution <their choice> --response <their text> --provenance user
```

## 5. Finalize — never choose

When the human says capture is complete, ask which terminal status applies:
`provisional`, `needs_user`, or `cancelled`. **Never choose it yourself.**

```
uv run python -m coherence.planning.guided_entrypoint finalize --run-id <run-id> --project-root . --status <their choice>
```

A hook runs an intent-review agent here and blocks finalize until the review is
recorded and every challenge is dispositioned. If it denies, satisfy the stated
reason and retry.

## 6. Author the spec

No backend command writes a spec — this is your work. Write
`docs/superpowers/specs/<date>-<slug>-design.md` from the captured intent
(`.intent/intent.json`) plus the drafted artifacts from step 1. Cover the
requirement it serves, the boundary, the contract, and the failure modes.

Then dispatch a **subagent** to review the spec against the captured intent:
does it cover every captured answer, contradict any of them, or invent scope
nobody asked for? Apply valid findings and re-review until clean. Show the human
the findings; do not hide a disagreement.

## 7. Author the plan

Write `docs/superpowers/plans/<date>-<slug>-plan.md` with **decomposable task
sections** — `bootstrap --decompose` raises `NoTasksFoundError` if the plan has
none, and each generated task must carry its affected SRs (SR-054).

Then dispatch a second **subagent** to review the plan against the spec:
unimplementable steps, missing verification, tasks that cannot be independently
checked. Apply valid findings and re-review until clean.

## 8. Decompose and validate

```
uv run python -m coherence.planning.guided_pipeline bootstrap --run-id <run-id> --project-root . --intent .intent/intent.json --spec <spec path> --plan <plan path> --decompose
```

This requires `.factory/factory.yaml`. It generates `tasks/T-NNN.md` from the
plan and writes `report.json`. Then:

```
uv run python -m coherence.planning.guided_pipeline check --run-id <run-id> --project-root . --intent .intent/intent.json --spec <spec path> --plan <plan path>
```

Findings such as `PLAN_TASK_PARITY` mean the plan and generated tasks disagree.
Fix the **plan** and re-run — never hand-edit a generated task to silence the
gate; that defeats the only structural guarantee this stage provides.

## 9. Review and hand off

```
uv run python -m coherence.planning.guided_pipeline review --run-id <run-id> --project-root .
uv run python -m coherence.planning.guided_pipeline handoff --run-id <run-id> --project-root . --workflow standard-development
uv run python -m coherence.planning.legal_actions_adapter <run-id>
```

Print the projection verbatim. `Starts automatically: no` is a hard invariant,
and the action list is display-only — seeing an action never authorizes running
it.

## 10. Stop

Report what exists now: the captured intent, the spec, the plan, the generated
task ids, and the handoff. Then stop.

Do not begin implementation, run any generated task, adopt or author an
SR/FEAT/bundle, grant consent, run implementation gates, or start a downstream
workflow. A human starts execution as a separate, explicitly authorized step.
````

- [ ] **Step 4: Run the contract test**

Run: `rtk proxy uv run pytest tests/unit/coherence/test_coherence_plan_command_contract.py -q -o addopts=''`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/coherence-plan.md tests/unit/coherence/test_coherence_plan_command_contract.py
git commit -m "feat(claude-code): drive the full planning workflow from /coherence-plan

SR: SR-065"
```

---

### Task 8: Live end-to-end verification

**Files:**
- Modify: `src/coherence/planning/legal_actions_adapter.py` (module docstring only)

This task exists because every preceding test mocks `subprocess`. None of them prove the real backend behaves as assumed.

- [ ] **Step 1: Falsify the reactive-challenge assumption**

```bash
mkdir -p /tmp/guided-check && cd /tmp/guided-check && git init -q && cd C:/coding/pi-agent-factory
uv run python -m coherence.planning.guided_entrypoint start --run-id verify-001 --project-root /tmp/guided-check --prompt "Verify the guided entrypoint end to end"
uv run python -m coherence.planning.guided_entrypoint append --run-id verify-001 --project-root /tmp/guided-check --answer-id a2 --question "What is the constraint?" --text "This always works and everyone agrees" --source user
```

Expected: the second call returns a challenge with `kind: "unsupported_claim"`, `status: "unresolved"`.

**If it does not fire, stop and report.** The design assumes `detect_challenges` is a working (if shallow) tripwire; if it does not fire on its own trigger words, that assumption is wrong and the plan needs revisiting rather than patching.

- [ ] **Step 2: Confirm provenance round-trips**

```bash
uv run python -m coherence.planning.guided_entrypoint append --run-id verify-001 --project-root /tmp/guided-check --answer-id a3 --question "Intent review finding" --text "No findings" --source intent-review-agent
```

Expected: exit 0. Confirm the journal at `/tmp/guided-check/.factory/planning/verify-001/capture/events.jsonl` contains an `answer_captured` event whose `payload.source` is `intent-review-agent` — the finalize gate depends on exactly this.

- [ ] **Step 3: Prove the finalize gate blocks and then releases**

Call `.claude/hooks/coherence_finalize_gate.py`'s `decide()` against `/tmp/guided-check` with the finalize command, before and after resolving the challenge from step 1.

Expected: before → a deny reason naming the outstanding challenge; after `resolve --resolution defer` → `None`.

- [ ] **Step 4: Finalize and read the projection**

```bash
uv run python -m coherence.planning.guided_entrypoint finalize --run-id verify-001 --project-root /tmp/guided-check --status provisional
uv run python -m coherence.planning.legal_actions_adapter verify-001
```

Expected: `state: "intent_provisional"`; the projection renders with `Starts automatically: no`.

- [ ] **Step 5: Confirm the fail-closed paths against the real backend**

```bash
uv run python -m coherence.planning.guided_entrypoint resume --run-id never-started-999 --project-root /tmp/guided-check; echo "exit=$?"
uv run python -m coherence.planning.guided_entrypoint status --run-id "../escape" --project-root /tmp/guided-check; echo "exit=$?"
```

Expected: first → `ok: false` with a real backend error at `exit=0`; second → `ok: false` about the run-id grammar at `exit=1`, with no subprocess run.

- [ ] **Step 6: Correct the sibling docstring**

`legal_actions_adapter.py`'s docstring describes Claude Code's command as read-only. Replace that clause to name the split accurately: `legal_actions_adapter` renders the read-only projection (used by the Hermes plugin and by step 9 of the command); `guided_entrypoint` and `guided_pipeline` drive the workflow. Change no code in that module.

- [ ] **Step 7: Full affected suites**

```bash
rtk proxy uv run pytest tests/unit/coherence tests/unit/hermes -q -o addopts=''
rtk proxy uv run ruff check src/coherence/planning .claude/hooks tests/unit/coherence
```

Expected: all pass, **including the untouched Hermes plugin tests**.

- [ ] **Step 8: Commit**

```bash
git add src/coherence/planning/legal_actions_adapter.py
git commit -m "docs(planning): correct the read-only claim in the adapter docstring

SR: SR-065"
```

---

## What this plan deliberately does not do

- **It does not adopt SR-065.** The record stays `proposed`. Per SR-044 consent is a human act with an explicit phrase; an agent recording it would be the exact bypass that requirement forbids. Passing these tests is evidence toward adoption, not adoption.
- **It does not let a hook judge content.** Every hook decision is a procedural fact read from disk. `detect_challenges` informs; it never gates. Gating on a keyword matcher would manufacture false assurance, which is worse than no gate.
- **It does not touch Hermes or Codex.** Hermes's `/coherence-plan` stays the read-only card it is, still green. Codex's adapter remains its owner's to build.
- **It does not add backend planning stages.** `_SESSION_STATES` makes it impossible for the adapter to express a state `session.py` cannot produce, so the day those stages land this fails closed rather than mis-rendering them.
- **It does not hand-write task records.** Tasks are generated from the plan by `decompose_plan`; `PLAN_TASK_PARITY` is what keeps them honest. Editing a generated task to satisfy the gate would destroy the only structural guarantee the stage offers.
