from __future__ import annotations

import pytest

from factory.evidence.types import CheckResult, EvidenceContext
from factory.evidence.registry import Registry

pytestmark = pytest.mark.unit


class _AlwaysConnector:
    kind = "always"
    args_schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}},
                   "additionalProperties": False}
    side_effect_free = True

    def evaluate(self, args, ctx):
        return CheckResult(passed=bool(args["ok"]), evidence=f"ok={args['ok']}")


class _BoomConnector:
    kind = "boom"
    args_schema = {"type": "object"}
    side_effect_free = True

    def evaluate(self, args, ctx):
        raise RuntimeError("kaboom")


def _ctx(tmp_path):
    return EvidenceContext(repo_root=tmp_path)


def test_register_and_evaluate_pass(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    assert r.evaluate_checks([{"name": "c1", "kind": "always", "args": {"ok": True}}], _ctx(tmp_path)) == []


def test_failed_check_reports_error(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "always", "args": {"ok": False}}], _ctx(tmp_path))
    assert errs and "c1" in errs[0] and "ok=False" in errs[0]


def test_unknown_kind_is_error(tmp_path):
    r = Registry()
    errs = r.evaluate_checks([{"name": "c1", "kind": "nope", "args": {}}], _ctx(tmp_path))
    assert errs and "unknown kind" in errs[0] and "nope" in errs[0]


def test_bad_args_is_error(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "always", "args": {}}], _ctx(tmp_path))
    assert errs and "c1" in errs[0]


def test_connector_exception_becomes_failed_check(tmp_path):
    r = Registry()
    r.register(_BoomConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "boom", "args": {}}], _ctx(tmp_path))
    assert errs and "boom errored" in errs[0] and "kaboom" in errs[0]


def test_duplicate_registration_raises():
    r = Registry()
    r.register(_AlwaysConnector())
    with pytest.raises(ValueError):
        r.register(_AlwaysConnector())
