"""CLI entry point: ``python -m sim <scenario.yaml>``

Loads a scenario YAML and launches the interactive simulation testbench.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sim.testbench import SimTestbench


def main() -> int:
    """Parse CLI args and run the testbench.

    Returns 0 on success, 1 on error.
    """
    if len(sys.argv) < 2:
        print("Usage: python -m sim <scenario.yaml>", file=sys.stderr)
        return 1

    scenario_path = Path(sys.argv[1])
    if not scenario_path.exists():
        print(f"Scenario file not found: {scenario_path}", file=sys.stderr)
        return 1

    tb = SimTestbench(scenario_path)
    tb.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())