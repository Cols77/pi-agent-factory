from __future__ import annotations

import sys
from collections.abc import Sequence

from coherence.audit.cli import main as audit_main
from coherence.doctor.cli import main as doctor_main
from coherence.explain import main as explain_main
from coherence.focus import main as focus_main
from coherence.goals.cli import main as goals_main
from coherence.measurement.cli import main as measurement_main
from coherence.navigate.cli import main as navigate_main
from coherence.presentation.cli import main as presentation_main
from coherence.register.cli import main as register_main
from coherence.router import main as route_main
from coherence.simulation.cli import main as simulation_main
from coherence.status import main as status_main
from coherence.trace.cli import main as trace_main

GROUPS = {
    "trace": trace_main,
    "register": register_main,
    "doctor": doctor_main,
    "navigate": navigate_main,
    "presentation": presentation_main,
    "goals": goals_main,
    "simulation": simulation_main,
    "audit": audit_main,
    "measurement": measurement_main,
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
