from __future__ import annotations

import sys
from collections.abc import Sequence

from coherence.doctor.cli import main as doctor_main
from coherence.register.cli import main as register_main
from coherence.trace.cli import main as trace_main

GROUPS = {"trace": trace_main, "register": register_main, "doctor": doctor_main}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in GROUPS:
        print("usage: coherence <group> [args...]")
        print(f"valid groups: {', '.join(GROUPS)}")
        return 2
    return GROUPS[args[0]](args[1:])


__all__ = ["GROUPS", "main"]
