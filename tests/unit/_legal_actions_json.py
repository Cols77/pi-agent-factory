"""Shared JSON-subprocess-result fixtures for coherence-plan adapter tests.

Both the Hermes plugin tests (tests/unit/hermes/test_coherence_plan_plugin.py)
and the shared-adapter tests (tests/unit/coherence/test_legal_actions_adapter.py)
exercise the same backend `legal-actions --json` contract; this module is the
single place that builds the fake `subprocess.CompletedProcess` results and
the payload dict shape so the two test files can't quietly drift from each
other. Not a test module itself (no `pytestmark`).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any


def completed_json(
    payload: dict[str, Any], returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Build a fake `subprocess.run` result carrying `payload` as JSON stdout."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(payload), stderr=stderr
    )


def valid_payload(**overrides: Any) -> dict[str, Any]:
    """Build a schema-1 legal-actions payload, valid unless overridden."""
    payload: dict[str, Any] = {
        "schema": 1,
        "run_id": "run-001",
        "blocked": False,
        "reason": None,
        "legal_next_actions": ["inspect-handoff"],
        "starts_automatically": False,
    }
    payload.update(overrides)
    return payload
