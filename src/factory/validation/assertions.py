from __future__ import annotations

import operator
import re

_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    ">": operator.gt,
    "<": operator.lt,
}
# Longest operators first so ">=" wins over ">".
_PATTERN = re.compile(r"^\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def evaluate_assertion(value: float, expr: str) -> bool:
    m = _PATTERN.match(expr)
    if m is None:
        raise ValueError(f"unparseable assertion: {expr!r}")
    op, threshold = m.group(1), float(m.group(2))
    return bool(_OPS[op](value, threshold))
