### T-1 — Add the `acceptance:` schema field

Extend the SR schema (and its validator) with an optional `acceptance:` array. Each entry:

```yaml
acceptance:
  - id: AC-1
    criterion: "A spec carrying duplicate ids with differing content fails deterministically."
    verification:
      kind: test_marker          # test_marker | harness | manual
      ref: "tests/unit/coherence/trace/test_spec_frontmatter.py"
```

`kind: manual` carries `reason:` and satisfies only via a `human_review` decision.

**Verify:** an SR with a malformed `acceptance` entry is rejected at load, not silently ignored.
**Acceptance:** schema round-trips; existing 55 SRs without `acceptance:` still load unchanged
(the field is optional, so this is additive — D3 backward-compatibility).

