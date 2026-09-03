from __future__ import annotations

import pytest

from coherence.register.fidelity import FidelityJudgeUnavailable
from coherence.register.fidelity_packet import (
    FidelityPacket,
    IndexSignatureView,
    ResolvedProductionRef,
    ResolvedValidationRef,
)

pytestmark = pytest.mark.unit

# SR-050/AC-4 (T5.3, open design question #4): default_judge, the real
# PiAgentBackend-dispatch implementation. PiAgentBackend itself is
# monkeypatched -- these tests never spawn a real subprocess or contact a
# real model.

_IMPL = ResolvedProductionRef(
    path="src/widgets/feature.py",
    symbol="widgets.feature:feature_context",
    signature=IndexSignatureView(kind="function", name="feature_context", signature="def feature_context()", summary=""),
    source_excerpt="def feature_context(): return 1",
)
_VER = ResolvedValidationRef(
    path="tests/unit/test_feature.py",
    test="tests/unit/test_feature.py::test_feature_context",
    signature=IndexSignatureView(kind="function", name="test_feature_context", signature="def test_feature_context()", summary=""),
    source_excerpt="def test_feature_context(): assert True",
    outcome=None,
)


def _packet() -> FidelityPacket:
    return FidelityPacket(
        sr_id="SR-900",
        statement="the system shall provide feature context",
        acceptance=(),
        design_source=None,
        profile="prototype",
        implemented=(_IMPL,),
        verified=(_VER,),
        import_overlap=(),
        unresolved=(),
    )


def _relation() -> dict:
    return {"field": "implemented_by", "path": _IMPL.path, "identity": _IMPL.symbol}


@pytest.mark.sr("SR-050")
def test_default_judge_raises_unavailable_when_dispatch_fails(tmp_path, monkeypatch):
    import factory.orchestrator.pi_backend as pi_backend_module
    from coherence.audit.fidelity_dispatch import default_judge
    from substrate.agents.model import AgentResult

    class _FakeBackend:
        def __init__(self, *a, **kw):
            pass

        def run(self, role, prompt, **kw):
            return AgentResult(ok=False, output={}, raw="subprocess spawn failed")

    monkeypatch.setattr(pi_backend_module, "PiAgentBackend", _FakeBackend)
    with pytest.raises(FidelityJudgeUnavailable):
        default_judge(_packet(), root=tmp_path, ext=tmp_path / "ext.ts")


@pytest.mark.sr("SR-050")
def test_default_judge_parses_a_valid_findings_verdict(tmp_path, monkeypatch):
    import factory.orchestrator.pi_backend as pi_backend_module
    from coherence.audit.fidelity_dispatch import default_judge
    from substrate.agents.model import AgentResult

    class _FakeBackend:
        def __init__(self, *a, **kw):
            pass

        def run(self, role, prompt, **kw):
            return AgentResult(ok=True, output={"findings": [dict(kind="overstated_link", relation=_relation())]}, raw="")

    monkeypatch.setattr(pi_backend_module, "PiAgentBackend", _FakeBackend)
    candidates = default_judge(_packet(), root=tmp_path, ext=tmp_path / "ext.ts")
    assert candidates == [dict(kind="overstated_link", relation=_relation())]


@pytest.mark.sr("SR-050")
def test_default_judge_falls_back_to_parsing_a_fenced_json_block_in_raw_output(tmp_path, monkeypatch):
    import factory.orchestrator.pi_backend as pi_backend_module
    from coherence.audit.fidelity_dispatch import default_judge
    from substrate.agents.model import AgentResult

    class _FakeBackend:
        def __init__(self, *a, **kw):
            pass

        def run(self, role, prompt, **kw):
            raw = 'preamble\n```json\n{"findings": [{"kind": "different_behavior"}]}\n```\ntrailer'
            return AgentResult(ok=True, output={}, raw=raw)

    monkeypatch.setattr(pi_backend_module, "PiAgentBackend", _FakeBackend)
    candidates = default_judge(_packet(), root=tmp_path, ext=tmp_path / "ext.ts")
    assert candidates == [{"kind": "different_behavior"}]


@pytest.mark.sr("SR-050")
def test_default_judge_raises_unavailable_on_unparseable_output(tmp_path, monkeypatch):
    import factory.orchestrator.pi_backend as pi_backend_module
    from coherence.audit.fidelity_dispatch import default_judge
    from substrate.agents.model import AgentResult

    class _FakeBackend:
        def __init__(self, *a, **kw):
            pass

        def run(self, role, prompt, **kw):
            return AgentResult(ok=True, output={}, raw="not json at all")

    monkeypatch.setattr(pi_backend_module, "PiAgentBackend", _FakeBackend)
    with pytest.raises(FidelityJudgeUnavailable):
        default_judge(_packet(), root=tmp_path, ext=tmp_path / "ext.ts")
