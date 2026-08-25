"""Staleness routing (Increment 6 Task 4).

`route` decides, for a recorded staleness finding's resolution class, whether
it goes to an owning writer (carrying that owner's ordered `resolve_cmd` tuple
unchanged) or to a blocker that must NOT execute a resolver -- matching the
spec: authoritative_gate -> owning resolve_cmd tuple unchanged;
provenance_blocked -> blocker without resolver execution. `unresolved_staleness`
reuses the existing freshness machinery to surface recorded staleness.
"""
from __future__ import annotations

import pytest

from coherence.staleness import UnresolvedStaleness, route
from substrate.freshness.recipes import ResolutionClass

pytestmark = pytest.mark.unit

OWNER_RESCUE_CMDS = (
    "coherence register rebind SR-001 --repo-root .",
    "coherence trace check --project-root .",
)


def _result(resolution_class, reason="stale", resolve_cmd=OWNER_RESCUE_CMDS):
    return UnresolvedStaleness(
        ref="sr:SR-001",
        resolution_class=resolution_class,
        reason=reason,
        resolve_cmd=resolve_cmd,
    )


def test_authoritative_gate_maps_to_owning_resolve_cmd_unchanged():
    # A staleness that is an authoritative gate must route to its owning
    # writer with the SAME ordered resolve_cmd tuple -- not reordered,
    # deduplicated, or a semicolon-joined string.
    out = route(_result(ResolutionClass.authoritative_gate))
    assert out.owner == "authoritative-writer"
    assert out.resolve_cmd == OWNER_RESCUE_CMDS
    assert tuple(out.resolve_cmd or ()) == OWNER_RESCUE_CMDS
    # A gate routes to its owning writer; it does not auto-execute a resolver.
    assert out.executes_resolver is False


def test_authoritative_gate_with_none_resolve_cmd_stays_none():
    out = route(_result(ResolutionClass.authoritative_gate, resolve_cmd=None))
    assert out.owner == "authoritative-writer"
    assert out.resolve_cmd is None
    assert out.executes_resolver is False


def test_provenance_blocked_maps_to_blocker_without_resolver_execution():
    # provenance_blocked cannot be auto-resolved (missing provenance): it maps
    # to a blocker and never executes a resolver, and carries no resolve_cmd.
    out = route(
        _result(
            ResolutionClass.provenance_blocked,
            reason="no recorded fingerprint",
            resolve_cmd=None,
        )
    )
    assert out.owner == "provenance-recovery"
    assert out.blocker_reason == "no recorded fingerprint"
    assert out.resolve_cmd is None
    assert out.executes_resolver is False


def test_derived_auto_is_not_handled_as_a_blocker_or_owner():
    # Only the named resolution classes get a routing decision here; an
    # auto-derived signal is resolved by its own resolver and is outside this
    # module's ownership routing.
    out = route(_result(ResolutionClass.derived_auto))
    assert out.owner is None
    assert out.executes_resolver is True


# -- unresolved_staleness suspects an SR gap-set edge ------------------------


def test_unresolved_staleness_reports_a_missing_satisfaction_link(tmp_path):
    # Task 6 Step 4: a governed SR with no satisfied task is `invalid` per
    # edge_validity; the sweep reports it as a blocking authoritative gate.
    from coherence.staleness import unresolved_staleness

    (tmp_path / "requirements").mkdir(parents=True)
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: T\nstatement: s\ndomain: d\n---\nbody\n",
        encoding="utf-8",
    )

    findings = unresolved_staleness(tmp_path)
    assert findings, "an SR with no satisfies edge must surface as stale"
    gate = next(f for f in findings if f.ref == "sr:SR-001")
    # It is an authoritative gate, so it routes to the owning writer rather
    # than auto-executing a resolver -- matching the spec's observation.
    routed = route(gate)
    assert routed.owner == "authoritative-writer"
    assert routed.executes_resolver is False


def test_unresolved_staleness_is_clean_for_a_satisfied_sr(tmp_path):
    from coherence.staleness import unresolved_staleness

    # A satisfied AND validated SR has no pending gaps -> `valid`, so it is NOT
    # reported. This is the negative case of the STRICT rule: only genuinely
    # non-`valid` edges surface as blocking gates.
    (tmp_path / "requirements").mkdir(parents=True)
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: T\nstatement: s\ndomain: d\n"
        "binding:\n  harness: sim-testbench\n  experiment: e\n  metric: m\n  trials: 20\n  assert: \">= 0.90\"\n---\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "tasks").mkdir(parents=True)
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: done\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\nsatisfies:\n- SR-001\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "validation").mkdir(parents=True)
    (tmp_path / "validation" / "validation-report.json").write_text(
        "{\"requirements\": [{\"id\": \"SR-001\", \"passed\": true}]}",
        encoding="utf-8",
    )

    assert unresolved_staleness(tmp_path) == []