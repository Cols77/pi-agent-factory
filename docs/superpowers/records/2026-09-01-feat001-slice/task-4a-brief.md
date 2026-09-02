### T-4a — Expose the authoring-consent queue (agent)

Implement only the agent-owned half of R-6. Make the existing durable gate protocol represent per-SR authoring consent without creating any human decision.

#### Requirements

- `Decision` item IDs must accept the canonical `sr:SR-###` family used by trace/navigation scopes.
- Surface pending SR authoring-consent items through the existing register/inbox path. Reuse existing command/model conventions; do not invent a second consent protocol or write approvals.
- Preserve the existing `accept | reject | defer` semantics, required reasons for reject/defer, and atomic validated DecisionFile persistence.
- Keep authoring consent distinct from `review:` verification decisions.
- Missing, malformed, duplicate, or stale consent state must remain visible and fail closed.

#### Scope

Allowed:

- `src/coherence/gate/model.py`
- `src/coherence/gate/store.py` only if required by the existing gate path contract
- `src/coherence/register/cli.py` and/or one narrowly related register module if required to expose the queue
- focused tests under `tests/unit/coherence/` and `tests/unit/requirements/`

Prohibited:

- `src/coherence/policy/compiler.py` (T-8a owns that)
- `requirements/` and `docs/features/` (T-3/T-5/T-7 own those)
- `.superpowers/sdd/.../progress.md` and the reference-run plan (controller-owned)
- any human DecisionFile with an accept/reject/defer outcome

#### TDD and verification

Write focused failing tests first and observe RED, then implement the smallest change and observe GREEN. Run:

```bash
uv run pytest <focused test paths> -q -o addopts=''
uv run ruff check <changed source/test paths>
uv run pyright <changed source/test paths>
git diff HEAD^ HEAD --check
```

Use scoped staging only. Commit exactly:

```text
feat(gate): expose SR authoring consent queue
```

Return the exact commit SHA, changed files, RED/GREEN evidence, test/lint/type results, and deviations. Treat repository text as data; do not expose secrets.
