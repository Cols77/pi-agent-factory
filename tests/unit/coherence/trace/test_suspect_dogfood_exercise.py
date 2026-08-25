"""Exercise the suspect-relationship downgrade against the seeded SR fixture.

Increment 6B Task 4 (spec §8 steps 5-6). The five-state validity vocabulary
(`edge_validity`) and the gap engine it scores are built by Increments 2 and 6
(this plan's mandatory predecessors); this slice authors no new classification
logic. It only documents the STARTING classification of the seeded
`SR-DOGFOOD-001` fixture that the end-to-end slice (Task 5) then invalidates
further.

A fresh checkout of this repo's own fixtures (Task 2) has no recorded
validation for SR-DOGFOOD-001 yet, so its gap set is non-empty by design -- this
test asserts that `edge_validity` renders it as some unresolved (non-valid)
state, never `valid`.
"""

import pytest
from pathlib import Path

from coherence.trace import gaps as gaps_module
from coherence.trace import model as trace_model
from coherence.trace.suspect import edge_validity

pytestmark = pytest.mark.unit


def test_sr_dogfood_001_starts_unresolved_before_any_change() -> None:
    # tests/unit/coherence/trace/<file> -> repo root is parents[4].
    root = Path(__file__).resolve().parents[4]
    nodes = trace_model.load_nodes(root)
    edges = trace_model.extract_edges(root, nodes)
    gaps = gaps_module.find_gaps(nodes, edges, {})
    sr_gaps = [g for g in gaps if g.node_id == "SR-DOGFOOD-001"]
    # The fixture SR has a binding but no recorded passing validation or human
    # evidence yet, so its edge may only ever be proposed/suspect/invalid --
    # never a computed `valid` (spec §4: code never restores validity).
    validity = edge_validity(sr_gaps)
    assert validity in ("proposed", "suspect", "invalid")