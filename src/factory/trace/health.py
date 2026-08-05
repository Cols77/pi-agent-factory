from __future__ import annotations

from dataclasses import dataclass

from factory.trace.gaps import Gap
from factory.trace.model import Node

# Which gap kind consumes which slot class. dangling_upstream and
# task_plan_missing are defects, not unfilled slots, so they are counted
# separately and never folded into the percentage. Spec section 4.5.
_SLOT_OF_GAP: dict[str, str] = {
    "task_no_sr": "task->SR",
    "task_no_plan": "task->plan",
    "plan_no_spec": "plan->spec",
    "sr_unsatisfied": "SR satisfied",
    "sr_unvalidated": "SR validated",
}

_CLASS_ORDER = ["task->plan", "task->SR", "plan->spec", "SR satisfied", "SR validated"]

_SLOTS_PER_NODE: dict[str, list[str]] = {
    "task": ["task->plan", "task->SR"],
    "plan": ["plan->spec"],
    "sr": ["SR satisfied", "SR validated"],
}


@dataclass(frozen=True)
class ClassHealth:
    name: str
    satisfied: int
    expected: int
    exempt: int


@dataclass(frozen=True)
class Health:
    classes: list[ClassHealth]
    satisfied: int
    expected: int
    dangling: int
    deferred: int

    @property
    def percent(self) -> int:
        if self.expected == 0:
            return 100
        return round(100 * self.satisfied / self.expected)


def compute_health(nodes: list[Node], gaps: list[Gap]) -> Health:
    expected = {name: 0 for name in _CLASS_ORDER}
    unfilled = {name: 0 for name in _CLASS_ORDER}
    exempt = {name: 0 for name in _CLASS_ORDER}

    for node in nodes:
        for slot in _SLOTS_PER_NODE.get(node.kind, []):
            expected[slot] += 1

    dangling = 0
    deferred = 0
    for gap in gaps:
        if gap.kind in ("dangling_upstream", "task_plan_missing"):
            dangling += 1
            continue
        if gap.disposition == "deferred":
            deferred += 1
        slot = _SLOT_OF_GAP.get(gap.kind)
        if slot is None:
            continue
        if gap.disposition == "exempt":
            expected[slot] -= 1
            exempt[slot] += 1
        else:
            unfilled[slot] += 1

    # sr_stale has no slot of its own: an SR is only counted once for validation,
    # and a stale result already fails to satisfy the "SR validated" slot.
    for gap in gaps:
        if gap.kind == "sr_stale" and gap.disposition != "exempt":
            unfilled["SR validated"] += 1

    classes = [
        ClassHealth(name, max(0, expected[name] - unfilled[name]), expected[name], exempt[name])
        for name in _CLASS_ORDER
    ]
    return Health(
        classes=classes,
        satisfied=sum(c.satisfied for c in classes),
        expected=sum(c.expected for c in classes),
        dangling=dangling,
        deferred=deferred,
    )
