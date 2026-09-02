### T-3 — Author acceptance criteria for the 8 SRs

Derive criteria from each SR's `source:` anchor, not from the code — otherwise criteria describe
what was built rather than what was required. Where source and code disagree, that is a finding,
not something to reconcile silently.

Expected shape (indicative, to be settled during authoring):

| SR | Criteria | Binds to |
|---|---|---|
| SR-002 | register closure: proposed / measured / accounted | `tests/unit/requirements/test_register.py` |
| SR-003 | frontmatter-authoritative spec node; duplicate ids fail deterministically; missing frontmatter degrades to filename node | `tests/unit/coherence/test_artifact_families.py` |
| SR-004 | one code map merging symbols + import edges; overlap computed from a single parser | `tests/unit/substrate/test_codemap_imports.py`, `test_codemap_resolver.py` |
| SR-005 | every course-note id resolves; unknown id fails; unreached SRs/specs reported | `tests/unit/coherence/test_course.py` |
| SR-006 | markers collected into the register; bound SR whose experiment names an unmarked file fails the gate | `tests/unit/coherence/test_register_markers.py` |
| SR-007 | KB entries selected by error signature and reached symbols | `tests/unit/substrate/test_kb_signatures.py`, `tests/unit/test_kb_index.py` |
| SR-001 | navigation across the declared lifecycle relations; missing links surface as gaps | `tests/unit/coherence/test_snapshot_navigation.py` + new |
| SR-050 | per-SR review reports structural / evidence / semantic findings separately; agent verdict not authoritative until gated | new |

SR-001 and SR-050 are expected to need new tests. **That is the useful signal** — they are the
two SRs whose sources are the engineering-context HLRs and the newest design, and they are the
least covered. Do not paper over it by binding them to loosely-related tests.

