### T-9 — Record the reference run (FEAT-017's input spec)

Written *during* T-3..T-8, not reconstructed afterwards. Produce
`docs/superpowers/plans/2026-09-01-feat001-reference-run.md` capturing:

- The ordered steps actually performed, with the command or edit each one was.
- Inputs and outputs per step: which artifact was read, which was written, by whom (agent or
  human), and which step is a human boundary that cannot be automated.
- Every ambiguity encountered and how it was resolved — these are the decisions FEAT-017 would
  otherwise invent.
- Anything that turned out to be wrong in this plan. A plan that survived contact unchanged is
  usually a plan nobody followed.

**Verify:** the record contains a step list an implementer could follow to register FEAT-002 by
hand without reading this plan.
**Acceptance:** FEAT-017's design cites this record as its source, and FEAT-017's acceptance test
is "registering FEAT-002 through bootstrap reproduces the shape FEAT-001 reached manually."

