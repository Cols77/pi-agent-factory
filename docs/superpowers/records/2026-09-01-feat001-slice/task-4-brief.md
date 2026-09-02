### T-4 — Human authoring consent

Route all 8 through the gate `DecisionFile` (`accept | reject | defer`, reason required on
reject/defer). Not chat narration, not a bulk approval.

**Verify:** a decision file exists per SR under the gate store; `register check` reflects the
outcome.
**Acceptance:** every SR has an explicit accept or decline. An agent cannot self-certify this
step (SR-044, I-01).

