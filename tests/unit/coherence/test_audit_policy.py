# tests/unit/coherence/test_audit_policy.py
"""``coherence.audit.policy.audit_max_workers`` -- the config-reading half of
Task 3's ``--max-workers``/``audit.max_workers`` binding.

``runner.run()`` only calls into this module when its own ``max_workers``
argument is ``None`` (see ``if max_workers is None: max_workers =
audit_max_workers(root)`` in ``runner.py``). Every other test in this
package passes ``max_workers=`` explicitly, so without these tests the
policy reader -- and that ``None``-defaulting branch itself -- has zero
coverage. Covers: no file, file without an ``audit:`` section, a real
configured value, and every documented fallback path (malformed YAML,
non-dict root, non-dict ``audit:`` section, non-positive/non-int
``max_workers``) exactly as ``policy.py`` documents falling back for each.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from coherence.audit.policy import DEFAULT_MAX_WORKERS, audit_max_workers
from coherence.audit.runner import run
from factory.orchestrator.types import AgentResult

from tests.unit.coherence.test_audit_parallel import _feat_scope, _verdict

pytestmark = pytest.mark.unit


def _write_factory_yaml(root: Path, body: str) -> None:
    (root / ".factory").mkdir(parents=True, exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(body, encoding="utf-8")


def test_default_when_no_factory_yaml(tmp_path: Path) -> None:
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS == 4


def test_default_when_file_exists_but_no_audit_section(tmp_path: Path) -> None:
    _write_factory_yaml(tmp_path, "playgrounds: {}\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_reads_configured_max_workers(tmp_path: Path) -> None:
    _write_factory_yaml(tmp_path, "audit:\n  max_workers: 9\n")
    assert audit_max_workers(tmp_path) == 9


def test_default_when_yaml_is_malformed(tmp_path: Path) -> None:
    # Unbalanced flow mapping -- yaml.safe_load raises yaml.YAMLError.
    _write_factory_yaml(tmp_path, "audit: [unclosed\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_default_when_root_is_not_a_mapping(tmp_path: Path) -> None:
    _write_factory_yaml(tmp_path, "- just\n- a\n- list\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_default_when_audit_section_is_not_a_mapping(tmp_path: Path) -> None:
    _write_factory_yaml(tmp_path, "audit: just a string\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


@pytest.mark.parametrize("bad_value", ["0", "-1", "-5"])
def test_default_when_max_workers_is_nonpositive(tmp_path: Path, bad_value: str) -> None:
    """The YAML policy reader must reject nonpositive values exactly like
    the CLI's own ``--max-workers`` validation does (``_positive_int`` /
    ``run()``'s own ``ValueError`` guard) -- a negative or zero value
    sitting in ``factory.yaml`` must fall back to the default, never be
    silently accepted and handed to ``ThreadPoolExecutor`` un-vetted."""
    _write_factory_yaml(tmp_path, f"audit:\n  max_workers: {bad_value}\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_default_when_max_workers_is_not_an_integer(tmp_path: Path) -> None:
    _write_factory_yaml(tmp_path, "audit:\n  max_workers: not-a-number\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_default_when_max_workers_is_a_bool(tmp_path: Path) -> None:
    # bool is a subclass of int in Python -- policy.py explicitly excludes
    # it (`isinstance(value, bool)` check) so `max_workers: true` can't be
    # silently accepted as `1`.
    _write_factory_yaml(tmp_path, "audit:\n  max_workers: true\n")
    assert audit_max_workers(tmp_path) == DEFAULT_MAX_WORKERS


def test_run_without_explicit_max_workers_reads_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration-level: confirm runner.run()'s ``if max_workers is None:
    max_workers = audit_max_workers(root)`` branch is actually exercised,
    not just ``policy.py`` in isolation. A configured ``audit.max_workers:
    1`` must serialise the two SRs' worker dispatch (never let both run
    concurrently), proving the value read from ``factory.yaml`` really
    reached the executor."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    _write_factory_yaml(tmp_path, "audit:\n  max_workers: 1\n")

    lock = threading.Lock()
    active = 0
    max_active = 0

    class _SerialTrackingBackend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            sr_id = "SR-001" if "auditing SR-SR-001" in prompt else "SR-002"
            with lock:
                active -= 1
            return AgentResult(ok=True, output=_verdict(sr_id), raw="", session_id="fake")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _SerialTrackingBackend)

    rc = run(tmp_path, "FEAT-001", run_id="rpolicy", no_gates=True)

    assert rc == 0
    assert max_active == 1
