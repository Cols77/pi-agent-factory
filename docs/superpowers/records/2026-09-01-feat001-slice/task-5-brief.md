### T-5 — Bind the markers

Add real `@pytest.mark.sr("SR-###")` decorators to the tests named in T-3. **First production
use of the marker system.** Expect to find defects in `collect_markers` — it has only ever run
against fixtures.

**Verify:** `coherence register check` surfaces the marker findings; the `test_marker`
obligation compiles as `blocking` for FEAT-001's SRs under `high_assurance`.
**Acceptance:** every bound SR's experiment resolves to a file carrying a matching marker.

