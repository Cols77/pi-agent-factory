### T-2 — Give `requirement_quality` a real criterion (closes NC-B, first half)

`compile_health_dimensions` currently sets `req_quality_ok = len(sr_nodes)` — structurally
incapable of failing. Replace with: **an SR counts only when it carries at least one acceptance
criterion with a resolvable verification binding.**

**Verify:** on the current register the dimension drops from 55/55 to ~0/55 and rises as this
slice lands. A dimension that moves is a dimension that measures something.
**Acceptance:** a unit test asserts an SR with no `acceptance:` does not count.

> Do **not** fix `verification_strategy` (NC-B second half) in this slice. It belongs with
> FEAT-002, which owns the obligation compiler. Record it, leave it.

