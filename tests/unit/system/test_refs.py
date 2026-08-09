import pytest
from factory.system.refs import sr_ref_from_trace_id, task_ref_from_trace_id

pytestmark = pytest.mark.unit


def test_bare_sr_id_from_a_satisfies_edge_becomes_a_scope_ref():
    assert sr_ref_from_trace_id("SR-146") == "sr:SR-146"


def test_an_already_prefixed_sr_ref_is_returned_unchanged():
    assert sr_ref_from_trace_id("sr:SR-146") == "sr:SR-146"


def test_an_unmappable_value_is_none_never_guessed():
    assert sr_ref_from_trace_id("") is None
    assert sr_ref_from_trace_id("not-an-sr") is None
    assert sr_ref_from_trace_id("SR-") is None


def test_task_trace_ids_map_both_directions():
    assert task_ref_from_trace_id("task:T-059") == "task:T-059"
    assert task_ref_from_trace_id("T-059") == "task:T-059"


def test_mapping_is_case_sensitive():
    assert sr_ref_from_trace_id("sr-146") is None
