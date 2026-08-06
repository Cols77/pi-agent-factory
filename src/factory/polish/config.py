from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from factory.config import FactoryConfig, GateStep, UnknownTypeError, load_config
from factory.polish.devserver import DevServerPlayground
from factory.polish.playground import Playground
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.harness import Harness
from factory.validation.playwright_harness import PlaywrightE2EHarness
from factory.validation.sim_harness import SimTestbenchHarness

PLAYGROUND_TYPES: dict[str, Callable[[dict, Path], Playground]] = {
    "dev-server": DevServerPlayground.from_config,
    "scenario-replay": ScenarioReplayPlayground.from_config,
}
HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]] = {
    "sim-testbench": SimTestbenchHarness.from_config,
    "playwright-e2e": PlaywrightE2EHarness.from_config,
}

# Re-exported so existing importers (factory.validation.pipeline,
# factory.polish.cli, tests) keep working unchanged.
__all__ = ["FactoryConfig", "GateStep", "PLAYGROUND_TYPES", "HARNESS_TYPES",
           "UnknownTypeError", "load_config"]
