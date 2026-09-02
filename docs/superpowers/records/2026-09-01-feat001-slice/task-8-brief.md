### T-8 — `human_review` and close

FEAT-001 is `high_assurance`, so `human_review` compiles as `blocking`. Real human entries; an
agent cannot produce them.

**Verify:** re-run `coherence navigate health --json`; FEAT-001's dimensions move.
**Acceptance:** the slice's exit condition (§2) holds, evidenced by command output rather than
by prose.

