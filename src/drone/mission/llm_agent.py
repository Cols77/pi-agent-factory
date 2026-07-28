"""LlmAgent — real LLM-backed MissionPlanner with configurable model chain."""
from __future__ import annotations

import json
import logging

from drone.interfaces import ModelConfig, Directive
from drone.mission.state import MissionState
from drone.navigation.registry import NavRegistry

logger = logging.getLogger(__name__)

VALID_DIRECTIVE_KINDS = {"update_nav", "override", "continue", "land", "return_base"}

SYSTEM_PROMPT = """You are a drone mission controller. You receive a mission status summary
and decide what to do next. You have tools to plan and update navigation,
investigate targets, check mission status, and mark objectives.

Rules:
- Always ensure a navigation plan is active. If none exists, create one.
- High-priority detections (distress, danger) override the current plan.
  Investigate first, then resume or replan navigation.
- If a detection has low confidence, you may request the drone to approach
  for a better view before classifying.
- Land immediately if battery is critically low (the system will enforce this).
- Output a Directive as your final response: {"kind": "...", "args": {...}}
  Valid kinds: update_nav, override, continue, land, return_base."""

# Tool schemas for LLM function calling
TOOL_DEFINITIONS = [
    {
        "name": "plan_navigation",
        "description": "Generate waypoints for a named navigation algorithm",
        "parameters": {
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "description": "Algorithm name (e.g. perimeter_sweep)",
                },
            },
            "required": ["algorithm"],
        },
    },
    {
        "name": "investigate_target",
        "description": "Build a single-waypoint plan to fly to a detection",
        "parameters": {
            "type": "object",
            "properties": {
                "detection_label": {"type": "string"},
                "detection_x": {"type": "number"},
                "detection_y": {"type": "number"},
                "detection_z": {"type": "number"},
            },
            "required": ["detection_label", "detection_x", "detection_y", "detection_z"],
        },
    },
    {
        "name": "mark_objective",
        "description": "Update objective tracking",
        "parameters": {
            "type": "object",
            "properties": {
                "objective_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "complete", "failed"],
                },
            },
            "required": ["objective_id", "status"],
        },
    },
    {
        "name": "get_mission_status",
        "description": "Read current state (no side effect)",
        "parameters": {"type": "object", "properties": {}},
    },
]


class LlmAgent:
    """Real LLM-backed MissionPlanner. Configurable model chain with automatic fallback."""

    def __init__(
        self,
        model_chain: list[ModelConfig],
        registry: NavRegistry,
    ) -> None:
        self._model_chain = model_chain
        self._registry = registry

    def decide(self, state: MissionState) -> Directive:
        """Call LLM with state summary, return parsed Directive."""
        summary = state.summary()

        for config in self._model_chain:
            try:
                response = self._call_provider(config, summary)
                directive = self._parse_directive(response)
                if directive.kind in VALID_DIRECTIVE_KINDS:
                    return directive
            except Exception as e:
                logger.warning(f"Model {config.model} failed: {e}")
                continue

        # All models failed or returned invalid directives
        return Directive(kind="continue")

    def _call_provider(self, config: ModelConfig, summary: str) -> str:
        """Call a provider API. Override in subclasses or mock for testing."""
        raise NotImplementedError(f"Provider {config.provider} not yet implemented")

    def _parse_directive(self, raw: str) -> Directive:
        """Parse LLM response text into a Directive."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "kind" in data:
                kind = data["kind"]
                args = data.get("args", {})
                if kind in VALID_DIRECTIVE_KINDS:
                    return Directive(kind=kind, args=args)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return Directive(kind="continue")
