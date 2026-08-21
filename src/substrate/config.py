from __future__ import annotations

from dataclasses import dataclass


class GateConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GateStep:
    cmd: str
    cwd: str | None = None


# A plain alias rather than a PEP 695 `type` statement: this repo targets
# Python 3.11+ (pyproject: requires-python = ">=3.11,<3.13"), and `type X = ...`
# is 3.12-only.
GateDeclarations = dict[str, list[GateStep]]


def load_gate_declarations(data: dict) -> GateDeclarations:
    """Parse the 'gates:' section of an already-YAML-parsed config dict into
    GateStep declarations. Validates declaration shape only -- it does not
    know or care how a gate's steps get run.

    Absent 'gates:' is {} -- NOT an error. Callers that require gates say so
    themselves (see require_gates); this is used by callers that accept a
    project declaring only playgrounds/harnesses and no gates at all.
    """
    gates: GateDeclarations = {}
    for name, steps in (data.get("gates") or {}).items():
        if not isinstance(steps, list):
            raise GateConfigError(
                f"gate {name!r}: expected a list of steps, got {type(steps).__name__}"
            )
        parsed: list[GateStep] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "cmd" not in step:
                raise GateConfigError(f"gate {name!r} step {i}: each step needs a 'cmd'")
            parsed.append(GateStep(cmd=str(step["cmd"]), cwd=step.get("cwd")))
        gates[name] = parsed
    return gates


def require_gates(gates: GateDeclarations, context: str) -> GateDeclarations:
    """Gates for a project that must have them, else raise.

    'This project has no sim' and 'this project never said what to check' are
    different statements. An individual gate may be omitted -- it skips -- but a
    project with no gates at all would validate nothing while reporting green.

    `context` names what's missing gates in the error message (e.g. a
    '.factory/factory.yaml' path) -- callers own what that string looks like.
    """
    if not gates:
        raise GateConfigError(
            f"{context} declares no gates. "
            "Add a 'gates:' section naming what to run for unit/sim/integration/full; "
            "an individual gate may be omitted and will be skipped."
        )
    return gates
