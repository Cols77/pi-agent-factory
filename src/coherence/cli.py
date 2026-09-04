from __future__ import annotations

import functools
import sys
from collections.abc import Sequence
from pathlib import Path

from coherence.audit.cli import main as audit_main
from coherence.course.cli import main as course_main
from coherence.doctor.cli import main as doctor_main
from coherence.explain import main as explain_main
from coherence.focus import main as focus_main
from coherence.goals.cli import main as goals_main
from coherence.measurement.cli import main as measurement_main
from coherence.mirrors.cli import main as mirrors_main
from coherence.navigate.cli import main as navigate_main
from coherence.presentation.cli import main as presentation_main
from coherence.register.cli import main as register_cli_main
from coherence.router import main as route_main
from coherence.simulation.cli import main as simulation_main
from coherence.status import main as status_main
from coherence.trace.cli import main as trace_main


def _register_judge_factory(project_root: Path):
    """SR-050/AC-4: wires `coherence.audit.fidelity_dispatch`'s real,
    `PiAgentBackend`-dispatch judge into `coherence register review
    --fidelity`/`--check`. This is the one integration point allowed to
    depend on both `coherence.register` (via `coherence.register.cli.main`'s
    own `judge_factory` parameter) and `factory.orchestrator` (transitively,
    through `coherence.audit.fidelity_dispatch`) -- `coherence.register`
    itself never imports `factory.*`; see
    `coherence/register/fidelity.py`'s "Layering" docstring section for why.
    """
    from coherence.audit.fidelity_dispatch import default_judge
    from substrate.paths import scope_guard_extension

    return functools.partial(default_judge, root=project_root, ext=scope_guard_extension())


def _register_overlap_judge_factory(project_root: Path):
    """SR-058/AC-2: wires `coherence.audit.overlap_dispatch`'s real,
    `PiAgentBackend`-dispatch judge into `coherence register overlap-check`
    -- the overlap-detection analogue of `_register_judge_factory` above,
    for the identical layering reason (`coherence.register` never imports
    `factory.*`; see `coherence/register/overlap.py`'s "Layering" section).
    """
    from coherence.audit.overlap_dispatch import default_judge
    from substrate.paths import scope_guard_extension

    return functools.partial(default_judge, root=project_root, ext=scope_guard_extension())


def _register_main(argv: Sequence[str]) -> int:
    return register_cli_main(
        list(argv),
        judge_factory=_register_judge_factory,
        overlap_judge_factory=_register_overlap_judge_factory,
    )


GROUPS = {
    "course": course_main,
    "trace": trace_main,
    "register": _register_main,
    "doctor": doctor_main,
    "navigate": navigate_main,
    "presentation": presentation_main,
    "goals": goals_main,
    "simulation": simulation_main,
    "audit": audit_main,
    "measurement": measurement_main,
    "mirrors": mirrors_main,
    "status": status_main,
    "route": route_main,
    "focus": focus_main,
    "explain": explain_main,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in GROUPS:
        print("usage: coherence <group> [args...]")
        print(f"valid groups: {', '.join(GROUPS)}")
        return 2
    return GROUPS[args[0]](args[1:])


__all__ = ["GROUPS", "main"]
