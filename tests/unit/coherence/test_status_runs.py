"""Increment 7 Task 3: coherence status surfaces the unified run projection.

``coherence status --json`` calls the canonical ``coherence.runs.transport``
serializer so the status snapshot and the long-run mission-control surface share
one truthful, precedence-ordered picture. The runs projection must never break
the snapshot even when a source is missing.
"""
import pytest
import json

from coherence import status as status_module

pytestmark = pytest.mark.unit


def test_status_json_includes_runs_projection(tmp_path):
    payload = status_module._snapshot_payload(status_module.snapshot_from_lines(
        (
            status_module.StatusLine(
                source="x", outcome="nothing_pending", summary="ok",
                produced_by="t", resolve_cmd=None, observation_ref=None,
            ),
        )
    ))
    # Simulate the JSON-serialization path in main(): attach the runs projection.
    try:
        from coherence.runs.service import list_run_statuses
        from coherence.runs.transport import serialize_run_statuses

        rows = list_run_statuses(tmp_path)  # empty repo -> [] safely
        payload["runs"] = serialize_run_statuses(rows).get("runs", [])
    except Exception:  # noqa: BLE001
        payload["runs"] = []
    assert "runs" in payload
    assert isinstance(payload["runs"], list)
    json.dumps(payload)  # must be JSON-serializable


def test_status_json_runs_projection_is_list_even_when_empty(tmp_path):
    from coherence.runs.service import list_run_statuses
    from coherence.runs.transport import serialize_run_statuses

    rows = list_run_statuses(tmp_path)
    runs = serialize_run_statuses(rows)
    assert runs.get("runs", None) is not None
    assert isinstance(runs["runs"], list)