# Labelled clean-consumer planning fixture

All files in this directory are deterministic test data for FEAT-017 Task 14. They model a
small initialized consumer project and its planning lifecycle; they are not human approval,
executed evidence, or authorization to start downstream work.

Assumptions: the fixture uses two tasks, two candidate SRs, and one warning. `reviews/` is
backend seam input, while `consent.json` and `warning-decision.json` are explicit fixture
records consumed only by tests. Hashes are intentionally omitted from source templates because
harnesses compute them after copying files.
