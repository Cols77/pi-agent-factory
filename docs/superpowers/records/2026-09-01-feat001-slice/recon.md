# Recon — FEAT-001 first vertical slice (verified 2026-09-01, read-only)

> **STALENESS WARNING.** This snapshot was taken *before* any slice task ran. Tasks T-1, T-2 and
> T-4a have since changed the code it describes. It has already misled one implementer (see §4).
> Treat every fact here as "true at slice start", and verify against the working tree before
> acting on it.

## 1. SR schema, loader, validator

Canonical: `src/coherence/register/register.py`.
`src/factory/requirements/register.py` and `.../cli.py` are deprecated `sys.modules` shims
redirecting to `coherence.register.*` (see `src/factory/requirements/register.py:1-23`).

- `Requirement` frozen dataclass — `register.py:28-39`:
  `id, title, statement, domain, upstream: list[str], binding: Binding|None, body, path,
  checksum: str|None = None, source: str|None = None`
- `Binding` frozen dataclass — `register.py:15-26`:
  `experiment, metric, assert_expr, harness: str|None, trials=1, window: dict|None,
  cadence="every_iteration"`
- Required frontmatter: `_REQUIRED = ("id", "title", "statement", "domain")` — `register.py:12`.
  `binding` is intentionally optional; its absence means "proposed".
- `parse_requirement(path) -> Requirement` — `register.py:55-77`. On missing required keys raises
  a plain `ValueError(f"{path.name}: missing required field(s): {missing}")` (`register.py:59-60`).
  Not a typed exception, not a finding record.
- `load_register(requirements_dir) -> list[Requirement]` — `register.py:109-115`; globs
  `SR-*.md`, sorted by id.
- `content_checksum(req)` `register.py:80-98`; `is_checksum_current(req)` `register.py:101-106`.
- Closure/validation layer: `src/coherence/register/closure.py`
  - `RequirementState` enum `closure.py:13-23`
  - `ClosureFinding` frozen dataclass `closure.py:25-38`: `req_id, state, severity: str|None, detail`
  - `classify(req, *, validation, linked_task_status, deferred_reason)` `closure.py:40-99`
  - `verify_sr_marker(...)` `closure.py:129-231`
  - `_test_marker_requiredness` `closure.py:116-126`
- Writers: `src/coherence/register/write.py` — `write_proposed_requirement`, `stamp_checksum`,
  `write_binding`, `reaffirm`, `write_deferral`. Typed errors `ReasonRequiredError`,
  `UnboundRequirementError` (`write.py:12-17`).
- `requirements/index.json` produced by `cmd_index` — `src/coherence/register/cli.py:67-84`.
  Currently 55 entries, all `{"id", "checksum": null, "proposed": true}`.
- Register CLI, all in `src/coherence/register/cli.py`, `main()` at `cli.py:314-383`:
  `new` 59-64, `index` 67-84, `status` 87-98, `show` 101-120, `bind` 123-170,
  `defer` 173-183, `check` 262-297, `next` 300-311. There is no `list` verb.
- Tests: `tests/unit/requirements/test_register.py`, `test_closure.py`, `test_write.py`,
  `test_cli.py`, `test_coherence_parity.py`; `tests/unit/coherence/test_register_markers.py`.

## 2. health.py — `compile_health_dimensions` (`health.py:627-817`)

`requirement_quality` block, `health.py:671-681`, ends with:

    req_quality_ok = len(sr_nodes)

Reported at `health.py:793`:
`DimensionCount("requirement_quality", req_quality_ok, len(sr_nodes), 0)` — a tautology.
The comment above it describes itself as "a deliberately honest placeholder".

`verification_strategy` block, `health.py:694-710` — **out of scope this slice (FEAT-002)**:
builds `verification_candidates` from `compile_obligations(...)` where
`o.kind == "verification_result"` and `o.requiredness in ("required","blocking")`, then
`verification_strategy_ok = sum(1 for o in ... if any(command.strip() for command in (o.resolve_cmd or ())))`.
Reported at `health.py:798-800`.

`DimensionCount` — `health.py:66-76`: frozen dataclass `name, satisfied, expected, exempt`.
`_DIMENSION_ORDER` (all 11 names) — `health.py:617-622`.
Tests: `tests/unit/coherence/test_health_dimensions.py` (8 tests); also
`tests/unit/system/test_health.py`, `test_vcycle_health.py`, `test_freshness_health.py`,
`tests/unit/trace/test_health.py`.

## 3. pytest SR marker system

- `collect_markers(path: Path) -> set[str]` — `src/coherence/register/markers.py:37-70`.
  AST-based, never imports the module.
- `_decorator_dotted` — `markers.py:12-25`; handles both bare `pytest.mark.sr` and the call form.
  Match rule at `markers.py:65`: `dotted == "mark.sr" or dotted.endswith(".mark.sr")`.
  Collects every string-constant positional arg (`markers.py:67-69`).
- `MarkerCollectionError` — `markers.py:28-34`, raised at `markers.py:54-57` on
  unreadable/unparsable files (never a raw OSError/SyntaxError).
- Consumers: `closure.verify_sr_marker` calls it at `closure.py:183`;
  `policy/compiler._test_marker_obligation` calls it at `compiler.py:281`.
- Tests: `tests/unit/coherence/test_register_markers.py` (27 tests).
- **Zero real decorators exist.** A regex for an actual decorator line matches 0 lines anywhere
  under `tests/`. All 14 textual matches are fixture strings or docstrings inside
  `tests/unit/coherence/policy/test_compiler.py:303`,
  `tests/unit/coherence/runs/test_service.py:4,22,29`,
  `tests/unit/coherence/test_register_markers.py:86,87,91,92,105,106,121,248`,
  `tests/unit/requirements/test_cli.py:622,639`.
  The marker IS registered in `pyproject.toml:36-40`.

## 4. Gate `DecisionFile`

`src/coherence/gate/model.py`:

- `Decision` `model.py:62-75`: `item_id: str`, `action: str = "accept"`, `reason: str = ""`,
  `review_after: str|None = None`, `decided_by: str|None = None`.
- `DecisionFile` `model.py:78-134`: `schema: int = 1`, `gate_id`, `artifact_ref`,
  `decisions: tuple[Decision, ...]`, `decided_at`, `decided_by`.
  `__post_init__` calls `validate_decisions` (`model.py:94-95`) — construction itself raises.
- Rules (`model.py:137-165`): `reject`/`defer` require non-blank `reason`; `defer` additionally
  requires an ISO-8601 `review_after`; the decision set must be non-empty; item ids unique.
- **`ITEM_ID_PREFIXES` — `model.py:41-48`. SUPERSEDED as of commit `c02d87f` (task T-4a):
  `sr:` IS now a valid prefix**, and the module docstring documents `sr:SR-###` as per-SR
  authoring consent. The line below records the state before T-4a and is kept only so the
  reasoning that motivated T-4a stays legible:
  *was* `("coverage:", "doctor:", "trace:", "review:", "suspect:")` with no `sr:`, so an SR
  authoring-consent item id was rejected by validation.
  **Do not cite the pre-T-4a state as current.** This file is a snapshot taken before any task
  ran; verify any fact against the working tree before relying on it.
- Errors: `DecisionValidationError(ValueError)` `model.py:49-51`;
  `CorruptDecisionFile(ValueError)` `model.py:53-59`.
- Store: `src/coherence/gate/store.py` — `decision_path(run_dir, gate_id)` resolves to
  `<run_dir>/gate-decisions/<filename-safe gate_id>.json` (`store.py:24-32`; `_filename_safe`
  `store.py:35-44` rewrites path-unsafe chars in the filename only, the canonical `gate_id`
  string is preserved verbatim inside the JSON).
  `write_decision(run_dir, file) -> Path` `store.py:47-71` (validates, then atomic temp+replace).
  `load_decision(path)` `store.py:74-91`.
- No CLI verb authors a DecisionFile. `src/coherence/audit/runner.py:449-492` resolves gates and,
  when the file is absent, instructs the human to "author a DecisionFile at {target}"
  (`audit/runner.py:466`).
- `resolve_gate(run_dir, gate_id, *, unattended)` `service.py:29-46`; action precedence
  reject > defer > accept at `service.py:49-59`.
- Tests: `tests/unit/coherence/test_gate.py` (path, round-trip, atomicity at 217-280) plus many
  consumer suites.

## 5. Obligation compiler — `src/coherence/policy/compiler.py`

- `compile_obligations(root, scope_ref="project", *, nodes=None, edges=None)` `compiler.py:85-120`.
  For `sr:*` scopes it compiles `verification_result`, `human_review` and `test_marker`
  (`compiler.py:112-119`), plus a universal `ci_verification`.
- `resolve_profile(root, scope_ref, ...)` `compiler.py:27-82`; precedence
  artifact/requirement > feature/bundle > path/component > project default.
  Raises `UncompiledPresetError` for a preset outside `COMPILED_PRESETS`.
- `_test_marker_obligation` `compiler.py:257-287`. `resolve_cmd` set at `compiler.py:287` to
  `(f'add @pytest.mark.sr("{sr_id}") to {experiment_path.name}',)`.
  Requiredness: `blocking` under `high_assurance`, `required` under `prototype`
  (`compiler.py:269`); `not_applicable` when unbound or the experiment is not a resolvable
  `.py` file (`compiler.py:270-280`).
- `_verification_result_obligation` `compiler.py:187-224`; `resolve_cmd` `compiler.py:219-223`
  (mentions `coherence register bind ...`); `blocking` under `high_assurance`, else `required`
  (`compiler.py:206`).
- `_human_review_obligation` `compiler.py:227-254`; `blocking` under `high_assurance`,
  `not_applicable` otherwise (`compiler.py:236`).
  **`reviewed = False` is hard-coded at `compiler.py:235`** — the field contract is undecided, so
  `human_review` can never currently reach satisfied.
- `Obligation` dataclass `src/substrate/policy/obligation.py:12-21`:
  `id, scope_ref, kind, requiredness: Literal["not_applicable","advisory","required","blocking"],
  reason, source_policy, state, resolve_cmd: tuple[str, ...]|None`.
- Profiles: `src/substrate/policy/vocabulary.py:25-28` —
  `KNOWN_PRESETS = ("exploration","prototype","product","high_assurance")`,
  `COMPILED_PRESETS = ("prototype","high_assurance")`, `DEFAULT_PRESET = "prototype"`.
  Override resolution at `vocabulary.py:59-116`.
- Tests: `tests/unit/coherence/policy/test_compiler.py` (22),
  `tests/unit/substrate/policy/test_obligation.py`,
  `tests/unit/coherence/test_navigate_obligations.py`, `tests/unit/coherence/policy/test_ci.py`.

## 6. Existence check — all nine T-3 test paths EXIST

`tests/unit/requirements/test_register.py`, `tests/unit/coherence/test_artifact_families.py`,
`tests/unit/substrate/test_codemap_imports.py`, `tests/unit/substrate/test_codemap_resolver.py`,
`tests/unit/coherence/test_course.py`, `tests/unit/coherence/test_register_markers.py`,
`tests/unit/substrate/test_kb_signatures.py`, `tests/unit/test_kb_index.py`,
`tests/unit/coherence/test_snapshot_navigation.py`.

## 7. Artifacts

`requirements/SR-001.md` frontmatter: `id: SR-001`, `title: "Explicit lifecycle traceability"`,
`domain: behavioral`, `upstream: []`,
`source: "docs/superpowers/plans/engineering-context/00-high-level-requirements.md#HLR-02"`.
Statement: navigation across system requirement, feature/design decision, production
implementation symbols, validation test nodes, experiment/simulation run, metric, evidence and
current validation state, through explicit declared relations maintained by implementation work
and mirrored as Obsidian wikilinks.

`requirements/SR-050.md` frontmatter: `id: SR-050`,
`title: "Per-requirement implementation traceability review"`, `domain: behavioral`,
`upstream: []`,
`source: "docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design.md#canonical-relations"`.
Statement: each implementation slice maintains canonical SR relations to the production symbols
and validation test nodes that implement and verify the changed behaviour, mirrors them as
Obsidian wikilinks, and runs a read-only per-SR review reporting structural coverage, evidence
integrity and semantic fidelity findings separately (missing, dangling, weak, overstated links),
without treating an agent verdict as authoritative until the required gate validates it.

Neither SR-001 nor SR-050 carries a `binding:` block; both are proposed.

`docs/features/FEAT-001.md` frontmatter lists `requirements:` SR-002..SR-007, SR-001, SR-050,
followed by a hand-written `## Related requirements` wikilink block — the T-7 target.
