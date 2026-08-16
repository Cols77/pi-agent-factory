# System Navigator Legibility (Increment 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/system` legible to someone who has never used this tool, never used a coding agent, and knows nothing about the system being built — without ever explaining something wrongly.

**Architecture:** Unchanged from Increment 1. Python computes; the browser renders. The browser never parses a ref, never synthesises a description, never executes a command. All new wording lives in Python; all new structure lives in the stringified page assembled by `clientSource()`.

**Tech Stack:** Python 3 (`uv run python -m factory.system`), vanilla TypeScript + DOM, vitest + jsdom, Playwright behind `BROWSER_GATE=1`.

**Specs:** `docs/superpowers/specs/2026-08-16-system-navigator-legibility-increment-2-design.md` (revision 2) is binding. Read its "design principle: the newcomer test" section before Task 1 — it is the acceptance bar for every task.

## Global Constraints

- **The newcomer test governs.** A reader who knows nothing must be able to answer, from the page alone: what is this project made of; what is this page showing me; what does this word mean; what does this identifier refer to; what should I look at first; something is missing, what do I do. Increment 1 answered 3, 4 and 6.
- **Being welcoming never costs being truthful.** A confidently wrong explanation is worse than none — the reader cannot detect it. Every orientation sentence must be fact-checked against the renderer it describes.
- **Contract words are never renamed.** `recorded` stays `recorded`. Only the sentences *around* them change. The browser and the CLI stay one language.
- **The browser never parses a ref.** Resolution is `ALIASES` then `LABELS`, both Python-computed.
- **Descriptions stay verbatim from ONE named field, or null.** No composition, no invented prose.
- **No new dependency.** No framework, build step, remote font, image, or icon package.
- **The surface may bound a list, never a sentence.** Five rows plus `+ N more` is fine; a clipped statement is not.
- A standing test rejects any `font`/`font-size` declaration at 10 or 11 px page-wide.
- Functions used in the page MUST be in `clientSource()`'s renderer array (`system-shell.ts`) or they do not exist at runtime while looking correct in source.
- Commit after every task with **explicit file paths** — never `git add <directory>`.

### Codebase facts, verified 2026-08-16

1. `pyproject.toml:31` sets `addopts = "-m unit"`. Every new Python test module needs `pytestmark = pytest.mark.unit` or pytest deselects it and exits 5.
2. Import fixtures relatively: `from . import _fixtures`. The dotted path fails under pytest.
3. `src/factory/system/cli.py` has NO `_emit`. Dispatch is a flat `if/elif` on **`args.cmd`** that assigns `result`/`rendered` and falls through to a shared print. Every subcommand has a `cmd_*` wrapper.
4. The adr `AssertionError` is at **`queries.py:1037`**, not `:1011`.
5. `TABS_BY_KIND` (`system-bootstrap.ts:548`) holds **thirteen** ids: `Brief, Matrix, Timeline, Guide, Trace, Vcycle, Validation, Feature, Story, Reverse, Goal, Sim, Diagram`.
6. `renderTraversal` (`system-bootstrap.ts:1130`) is an INNER function of `systemBootstrap` — not exported, not importable. Test it through `loadPage(opts)` in `test/system-page-dom.test.ts`, which already accepts `opts.traversal`.
7. A delegated SPA handler for `a.scope-open` + `data-scope` already exists at `system-bootstrap.ts:623`. Reuse it; do not write new navigation.
8. `system-bootstrap.ts:451` wraps `refChip(ref)` inside its own `<a>` — this becomes nested anchors once chips are anchors.
9. `ensureCardController`'s document click handler (`system-comprehension.ts:585`) neither `preventDefault`s nor `stopPropagation`s.
10. `_OPENABLE_KINDS` (`labels.py:84`) is exactly `{bundle, sr, task, file}`.

---

## Task 1: Nothing is truncated

**Files:**
- Modify: `pi-ext/factory-watch/src/system-shell.ts` (`.info-card-description`, `.chip-title`)
- Modify: `src/factory/schemas/system_bundle.schema.json`
- Test: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`, `tests/unit/system/test_bundles.py`

**Interfaces:** Produces no new API. Removes the 3-line clamp and the 280-char cap.

- [ ] **Step 1: Write the failing tests**

```ts
// test/system-page-visual-identity.test.ts
test("a description is never clipped to a fixed line count", () => {
  const html = renderSystemPageHtml();
  const rule = html.match(/\.info-card-description\s*\{[^}]*\}/)?.[0] ?? "";
  expect(rule).not.toContain("-webkit-line-clamp");
  expect(rule).toContain("overflow-y: auto");
  expect(rule).toMatch(/max-height/);
});
```

```python
# tests/unit/system/test_bundles.py — a long description must now LOAD, not error
def test_bundle_description_over_280_chars_is_accepted(tmp_path):
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    _fixtures.write_bundle(
        bundles_dir, "planner", "Reactive planner core", ["sr:SR-001"],
        description="x" * 400,
    )
    assert list_bundle_errors(bundles_dir) == []
    assert len(list_bundles(bundles_dir)[0].description) == 400
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-page-visual-identity.test.ts` and `uv run pytest tests/unit/system/test_bundles.py -k 280 -v`
Expected: FAIL — the clamp is present; the 400-char description is rejected.

Note there is an EXISTING test asserting >280 chars becomes a load error. **Invert it, do not delete it** — the behaviour genuinely changed, and the inverted test is what proves it.

- [ ] **Step 3: Implement**

`system-shell.ts` — replace the `.info-card-description` rule:

```css
  .info-card-description { margin-top: 6px; color: var(--text-muted); font-size: 13px; line-height: 1.5; max-height: min(60vh, 520px); overflow-y: auto; overscroll-behavior: contain; }
```

`.chip-title` stops clipping by default; keep ellipsis ONLY in the matrix subject column:

```css
  .ref-chip .chip-title { overflow-wrap: anywhere; }
  .matrix-subject .chip-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

`system_bundle.schema.json` — delete `"maxLength": 280,` and rewrite the annotation so it states guidance without claiming enforcement:

```json
      "description": "One or two sentences stating WHAT the feature is -- an expansion of `label`. Rationale for why artifacts were grouped this way belongs in an ADR, not here. There is no length cap: a truncated description is worse than a long one, because the reader cannot tell what was cut."
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd pi-ext/factory-watch && npm test` and `uv run pytest tests/unit/system -q`
Expected: PASS. Baselines: extension 1001 passed / 1 skipped; python system 421 passed / 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-shell.ts src/factory/schemas/system_bundle.schema.json pi-ext/factory-watch/test/system-page-visual-identity.test.ts tests/unit/system/test_bundles.py
git commit -m "fix(system): stop truncating descriptions and titles"
```

---

## Task 2: Chips navigate

**Files:**
- Modify: `pi-ext/factory-watch/src/system-comprehension.ts` (`refChip`, `ensureCardController`)
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts:445-458` (stop wrapping the chip)
- Test: `pi-ext/factory-watch/test/system-comprehension.test.ts`, `test/system-page-dom.test.ts`

**Interfaces:**
- Consumes: `LABELS[ref].scope_href`, and the existing `a.scope-open` delegated handler.
- Produces: `refChip` returns `HTMLAnchorElement` for openable kinds, `HTMLSpanElement` otherwise.

- [ ] **Step 1: Write the failing tests**

```ts
test("an openable ref renders as a link carrying the SPA contract", () => {
  const el = refChip("task:T-060");
  expect(el.tagName).toBe("A");
  expect(el.getAttribute("href")).toBe("/system?scope=task%3AT-060");
  expect(el.getAttribute("data-scope")).toBe("task:T-060");
  expect(el.className).toContain("scope-open");
  expect(el.hasAttribute("role")).toBe(false);       // an anchor is already actionable
});

test("a non-openable ref stays a span with button semantics", () => {
  // seed LABELS with a spec: entry whose scope_href is null
  const el = refChip("spec:docs/superpowers/specs/foo.md");
  expect(el.tagName).toBe("SPAN");
  expect(el.getAttribute("role")).toBe("button");
  expect(el.getAttribute("aria-expanded")).toBe("false");
});

test("clicking an anchor chip navigates and does not toggle the card", () => {
  // dispatch a click on an anchor chip; assert no .info-card is created
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-comprehension.test.ts`
Expected: FAIL — `refChip` returns a SPAN for every kind today.

- [ ] **Step 3: Implement**

In `refChip`, when the resolved entry has a non-null `scope_href`:

```ts
  const el = document.createElement('a') as HTMLAnchorElement;
  el.className = 'ref-chip scope-open';
  el.setAttribute('href', entry.scope_href);
  // The existing delegated handler at system-bootstrap.ts:623 reads data-scope,
  // preventDefaults, and calls loadScope -- reuse it rather than adding a second
  // navigation path. Without it the href would hard-reload and discard page state.
  el.setAttribute('data-scope', entry.ref);
  el.setAttribute('aria-describedby', 'system-info-card');
```

Otherwise build the `<span role="button" aria-expanded="false">` exactly as today.

In `ensureCardController`'s click handler, exclude anchor chips from the toggle path:

```ts
    // An anchor chip navigates on click; only span chips toggle the card.
    if (trigger && trigger.tagName === 'A') return;
```

Hover and keyboard focus must still open the card for BOTH forms — do not gate those on tag name.

`system-bootstrap.ts:445-458` — the Unbundled list must stop wrapping:

```ts
        // refChip is itself the link now; wrapping it in another <a> would nest
        // interactive elements and race two click handlers.
        row.appendChild(refChip(ref));
```

Delete that site's own `href`/`preventDefault`/`loadScope` handler — the delegated one covers it.

- [ ] **Step 4: Run to verify they pass**

Run: `cd pi-ext/factory-watch && npx tsc --noEmit && npm test`
Expected: PASS. Existing tests asserting `.scope-item` structure in the sidebar will need updating to the chip structure — update, do not weaken.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-comprehension.ts pi-ext/factory-watch/src/system-bootstrap.ts pi-ext/factory-watch/test/system-comprehension.test.ts pi-ext/factory-watch/test/system-page-dom.test.ts
git commit -m "feat(system): artifact chips are real links with SPA navigation"
```

---

## Task 3: The evidence ladder

**Files:**
- Modify: `pi-ext/factory-watch/src/system-shell.ts` (`.traversal-path` and friends; the narrow-viewport block at `:452`)
- Modify: `pi-ext/factory-watch/src/system-bootstrap.ts:1130` (`renderTraversal`)
- Test: `pi-ext/factory-watch/test/system-page-dom.test.ts`

**Interfaces:** Consumes `boundedList`, `nextStepBlock`. Produces the ladder DOM: one `.trace-spine-step` per step, each with `.trace-spine-label`, a `.trace-spine-count`, and `.trace-spine-value`.

- [ ] **Step 1: Write the failing tests**

```ts
test("the ladder is one full-width row per step with its count on the rule", async () => {
  const dom = await loadPage({
    scope: "bundle:b1",
    traversal: {
      requirement: ["sr:SR-030","sr:SR-033","sr:SR-038","sr:SR-086","sr:SR-087","sr:SR-088","sr:SR-089"],
      tasks: [], design: [], files: [],
    },
  });
  const doc = dom.window.document;
  const steps = doc.querySelectorAll(".trace-spine-step");
  expect(steps.length).toBe(4);
  expect(steps[0].querySelector(".trace-spine-count")?.textContent).toBe("7");
  expect(steps[0].querySelectorAll(".bounded-list > .ref-chip").length).toBe(5);
  expect(steps[0].querySelector("details summary")?.textContent).toBe("+ 2 more");
});

test("an empty step reads Not recorded and carries its next step inline", async () => {
  const dom = await loadPage({ scope: "bundle:b1",
    traversal: { requirement: ["sr:SR-030"], tasks: [], design: [], files: [] } });
  const step = dom.window.document.querySelectorAll(".trace-spine-step")[2];
  expect(step.textContent).toContain("Not recorded");
  expect(step.querySelector(".next-step")).not.toBeNull();
  expect(step.querySelector(".trace-spine-count")?.textContent).toBe("0");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npx vitest run test/system-page-dom.test.ts -t ladder`
Expected: FAIL — no `.trace-spine-count` exists.

- [ ] **Step 3: Implement**

`addStep` inside `renderTraversal` gains the count and keeps everything else:

```ts
    function addStep(label: string, values: string[]): void {
      const step = document.createElement('div');
      step.className = 'trace-spine-step';
      const head = document.createElement('div');
      head.className = 'trace-spine-head';
      const stepLabel = document.createElement('div');
      stepLabel.className = 'trace-spine-label';
      stepLabel.appendChild(document.createTextNode(label));
      const count = document.createElement('span');
      count.className = 'trace-spine-count';
      count.appendChild(document.createTextNode(String((values || []).length)));
      head.appendChild(stepLabel);
      head.appendChild(count);
      step.appendChild(head);
      // ... existing value/Not-recorded/nextStepBlock body unchanged ...
    }
```

CSS — the ladder replaces the four-column grid:

```css
  .traversal-path { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0; margin: 6px 0 20px; counter-reset: trace-step; border: 1px solid var(--line); border-radius: var(--radius-sm); }
  .trace-spine-step { position: relative; min-width: 0; padding: 12px 16px 14px 40px; counter-increment: trace-step; }
  .trace-spine-step + .trace-spine-step { border-top: 1px solid var(--line); }
  .trace-spine-head { display: flex; align-items: baseline; gap: 12px; }
  .trace-spine-label { flex: none; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .trace-spine-head::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--line); }
  .trace-spine-count { flex: none; color: var(--text-muted); font: 12px/1.3 var(--font-mono); }
  .trace-spine-value { min-width: 0; margin-top: 6px; color: var(--text); font: 13px/1.6 var(--font-body); }
```

DELETE the `.trace-spine-step:not(:last-child)::after` chevron rule entirely, and delete the now-orphaned narrow-viewport block at `system-shell.ts:452` that collapsed the grid and re-rotated that chevron — the ladder IS that layout now. Verify nothing else references those selectors before deleting.

Note the value font moves from `--font-mono` 12px to `--font-body` 13px: these are titles and sentences now, not identifiers. Ids inside chips keep the mono face via `.chip-id`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd pi-ext/factory-watch && npm test && npx vitest run test/system-page-visual-identity.test.ts`
Expected: PASS. The 12px floor test must stay green — every new declaration is ≥12px.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/system-shell.ts pi-ext/factory-watch/src/system-bootstrap.ts pi-ext/factory-watch/test/system-page-dom.test.ts
git commit -m "feat(system): the traversal spine becomes a full-width evidence ladder"
```

---

## Task 4: Panel orientation

**Files:**
- Modify: `src/factory/system/vocabulary.py` (add `PANELS`, `build_panels`)
- Modify: `src/factory/system/cli.py` (a `panels` subcommand)
- Modify: `pi-ext/factory-watch/src/system-vocabulary-data.ts` (mirror), `system-shell.ts` (markup + the orientation line), `system-bootstrap.ts` (`showTab` sets it)
- Test: `tests/unit/system/test_vocabulary.py`, `tests/unit/system/test_table_drift.py`, `pi-ext/factory-watch/test/system-page-dom.test.ts`

**Interfaces:** Produces `PANELS: dict[str, dict]` keyed by tab id, each with `label`, `what_it_shows`, `how_to_read`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/system/test_vocabulary.py
def test_every_panel_entry_has_both_sentences():
    from factory.system.vocabulary import PANELS
    for tab, e in PANELS.items():
        assert e["what_it_shows"].strip(), tab
        assert e["how_to_read"].strip(), tab
        assert e["what_it_shows"].endswith("."), tab
```

```ts
// test/system-page-dom.test.ts — the completeness test lives HERE, not in Python:
// TABS_BY_KIND exists only in TypeScript, and mirroring it in Python would
// reintroduce exactly the drift this guards.
test("every rendered tab has an orientation line", async () => {
  const dom = await loadPage({ scope: "bundle:b1" });
  const doc = dom.window.document;
  doc.querySelectorAll('[role="tab"]').forEach((tab) => {
    const id = tab.getAttribute("aria-label")!;
    expect(PANELS_DATA[id], `no orientation for tab ${id}`).toBeTruthy();
  });
});

test("the orientation line follows the active tab", async () => {
  const dom = await loadPage({ scope: "bundle:b1" });
  const doc = dom.window.document;
  const line = doc.getElementById("panelOrientation")!;
  expect(line.textContent).toContain("Every claim this scope makes");
  (doc.getElementById("tabMatrix") as HTMLElement).click();
  expect(line.textContent).toContain("validation has run");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/system/test_vocabulary.py -k panel -v`
Expected: FAIL — `PANELS` does not exist.

- [ ] **Step 3: Implement**

`vocabulary.py` gains `PANELS` with an entry for **all thirteen** tab ids from `TABS_BY_KIND`: `Brief, Matrix, Timeline, Guide, Trace, Vcycle, Validation, Feature, Story, Reverse, Goal, Sim, Diagram`.

The spec's revision-2 table carries fact-checked wording for the first seven. **The remaining six must be fact-checked against their real renderers before you write them** — open each renderer, see what it actually produces, and describe that. Do not paraphrase the tab's name. If you cannot determine what a panel shows, say so in your report rather than inventing a sentence; a wrong orientation line is worse than none, per the Global Constraints.

Register the CLI subcommand following the `vocabulary` pattern already in `cli.py` (a `cmd_panels` wrapper plus an `elif args.cmd == "panels"` branch that assigns `result`/`rendered` and falls through — no early `return`).

Mirror into `system-vocabulary-data.ts` as `PANELS_DATA`, and extend `test_table_drift.py` to cover it — the existing drift test's shape applies directly.

`system-shell.ts` — add `<p id="panelOrientation" class="panel-orientation"></p>` directly beneath the tab strip, and:

```css
  .panel-orientation { margin: 8px 0 14px; max-width: 78ch; color: var(--text-muted); font-size: 13px; line-height: 1.6; }
  .panel-orientation .how-to-read { display: block; margin-top: 3px; color: var(--text-dim); }
```

`system-bootstrap.ts` — `showTab(name)` sets the line from `PANELS_DATA[name]`, rendering `what_it_shows` and `how_to_read` as two lines. An unknown tab renders nothing rather than a placeholder.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/system -q && cd pi-ext/factory-watch && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/vocabulary.py src/factory/system/cli.py pi-ext/factory-watch/src/system-vocabulary-data.ts pi-ext/factory-watch/src/system-shell.ts pi-ext/factory-watch/src/system-bootstrap.ts tests/unit/system/test_vocabulary.py tests/unit/system/test_table_drift.py pi-ext/factory-watch/test/system-page-dom.test.ts
git commit -m "feat(system): every panel states what it shows and how to read it"
```

---

## Task 5: The landing teaches the ontology

**Files:**
- Modify: `src/factory/system/health.py` (compose the shape sentence)
- Modify: `pi-ext/factory-watch/src/system-cli.ts` (type it), `system-bootstrap.ts` (`renderHealthSummary`), `system-shell.ts` (CSS)
- Test: `tests/unit/system/test_health.py`, `pi-ext/factory-watch/test/system-page-dom.test.ts`

**Interfaces:** `health` payload gains `shape: {sentence: str, parts: {...}}` — a template with counts substituted in Python.

- [ ] **Step 1: Write the failing test**

```python
def test_shape_sentence_states_what_the_project_is_made_of(tmp_path):
    # seed 2 SRs, 1 bundle containing them, 1 task satisfying one
    payload = query_health(tmp_path)
    s = payload["shape"]["sentence"]
    assert "2 requirements" in s
    assert "1 feature" in s
    assert "1 task" in s

def test_shape_sentence_is_honest_with_no_bundles(tmp_path):
    payload = query_health(tmp_path)
    assert "no features yet" in payload["shape"]["sentence"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/system/test_health.py -k shape -v`
Expected: FAIL — `KeyError: 'shape'`.

- [ ] **Step 3: Implement**

In `health.py`, compose from counts the projection already has — requirement total from `coverage`, feature count from `bundles`, task total, and the validated count from the `SR validated` class:

```python
def _shape_sentence(requirements: int, features: int, tasks: int, validated: int) -> str:
    """Plain-words statement of what the project is made of.

    A template with recorded counts substituted -- never model prose. It is
    `derived`, and the browser badges it as such, so its provenance is as
    visible as any other claim's.
    """
    feature_part = f"grouped into {features} features" if features else "grouped into no features yet"
    return (
        f"This project is described by {requirements} requirements, {feature_part}. "
        f"{tasks} tasks implement them, and {validated} of those requirements "
        f"has a passing validation."
    )
```

Handle singular/plural for every count — "1 requirements" would undercut the whole point of the sentence. Write a test per singular case.

`renderHealthSummary` renders the sentence above the metric tiles, with a `derived` badge (reuse `withGloss`) so the reader can see where it came from. Each metric tile gains its denominator rule inline from `VOCABULARY.terms[className].definition`'s first sentence, beneath the ratio.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/system -q && cd pi-ext/factory-watch && npm test`
Expected: PASS. Then eyeball it against real data:
`uv run python -m factory.system health --json --repo-root C:/coding/cool_physical_ai_project` and confirm the sentence reads true.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/health.py pi-ext/factory-watch/src/system-cli.ts pi-ext/factory-watch/src/system-bootstrap.ts pi-ext/factory-watch/src/system-shell.ts tests/unit/system/test_health.py pi-ext/factory-watch/test/system-page-dom.test.ts
git commit -m "feat(system): the landing states what the project is made of"
```

---

## Task 6: The adr crash

**Files:**
- Modify: `src/factory/system/queries.py` around `:1024-1037`
- Test: `tests/unit/system/test_queries.py`

**Interfaces:** `query_brief` resolves `adr:` members instead of raising.

- [ ] **Step 1: Write the failing test**

```python
def test_brief_resolves_an_adr_member_instead_of_raising(tmp_path):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-use-bundles.md").write_text(
        "---\nid: ADR-0001\ntitle: Use bundles\nstatus: accepted\n---\n\n"
        "## Decision\n\nWe group by feature bundle.\n", encoding="utf-8")
    bundles_dir = tmp_path / "bundles"; bundles_dir.mkdir()
    write_bundle(bundles_dir, "b1", "Bundle one", ["adr:ADR-0001"])
    brief = query_brief(tmp_path, parse_scope_ref("bundle:b1"))
    assert any("ADR-0001" in c.text for c in brief.claims)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/system/test_queries.py -k adr_member -v`
Expected: FAIL with `AssertionError: unexpected member kind: 'adr'`.

- [ ] **Step 3: Implement**

`trace_model.load_nodes` never emits `adr` nodes, so `_resolve_trace_member` can never resolve one — a bespoke branch is genuinely required, mirroring how `labels.py:200` already loads ADRs:

```python
            elif member.kind == "adr":
                # load_nodes emits no adr nodes (trace/model.py), so the trace
                # path can never resolve one -- resolve from the ADR loader, as
                # the label index already does.
                resolution = _resolve_adr_member(member, identifier, repo_root)
```

An ADR that does not resolve produces a `missing` claim with the bundle citation — the same shape `bundles.py` already uses for an unresolvable member ref. It must NOT raise.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/system -q`, then against the real repo:
`uv run python -m factory.system brief --scope bundle:event-log-replay-metrics --json --repo-root C:/coding/cool_physical_ai_project | head -c 200`
Expected: PASS, and the real bundle briefs without raising. Repeat for `bundle:governance-traceability-contract-spine`.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/queries.py tests/unit/system/test_queries.py
git commit -m "fix(system): resolve adr bundle members instead of crashing the Brief tab"
```

---

## Task 7: Remaining residuals

**Files:**
- Modify: `src/factory/system/labels.py` (alias collision guard)
- Modify: `pi-ext/factory-watch/src/system-renderers.ts` (wire the absence states), `system-shell.ts` (`.presence-rail.is-failure`)
- Test: `tests/unit/system/test_labels.py`, `pi-ext/factory-watch/test/system-comprehension.test.ts`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_file_path_colliding_with_a_bare_id_is_recorded_not_silently_shadowed(tmp_path):
    # a manifest whose changed_files contains a path exactly equal to a task id
    payload = build_labels(tmp_path)
    assert payload["aliases"]["T-060"] == "task:T-060"      # the artifact wins
    assert any("collision" in d for d in payload["degraded"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/system/test_labels.py -k collision -v`
Expected: FAIL — the file loop overwrites unconditionally and records nothing.

- [ ] **Step 3: Implement**

Guard the file loop in `build_labels` — skip and record rather than overwrite:

```python
        if path in aliases and aliases[path] != ref:
            degraded.append(f"alias collision: {path!r} already resolves to {aliases[path]}")
        else:
            aliases[path] = ref
```

Wire the absence states **per their differing shapes** — this is not a uniform list:
- `no_requirements`, `traversal_not_applicable` — panel-level empties, wired like the existing seven.
- `unbundled_artifact` — per-artifact, like the working `matrix_never_run` per-row pattern.
- `no_changed_files`, `no_commit_range` — per-RUN. `renderChangedFiles` carries a standing comment: *"one Next step per panel, never one per empty child."* Render a SINGLE panel-level block only when EVERY run in the panel lacks the data.
- `no_trace` — `renderTrace`'s empty branch calls `renderNotApplicable`, a plainer path with no `presence-rail` and no `nextStepBlock`. This is a render-path switch.

`.presence-rail.is-failure` (`system-shell.ts:476`) is dead CSS. Decide from the code: if any state you wire is `severity: "failure"`, use it; otherwise delete it. Do not leave it unreachable.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/system -q && cd pi-ext/factory-watch && npm test`

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/labels.py pi-ext/factory-watch/src/system-renderers.ts pi-ext/factory-watch/src/system-shell.ts tests/unit/system/test_labels.py pi-ext/factory-watch/test/system-comprehension.test.ts
git commit -m "fix(system): alias collision guard, remaining absence states, dead CSS"
```

---

## Task 8: Jargon audit

**Files:**
- Modify: `pi-ext/factory-watch/src/system-shell.ts`, `system-renderers.ts`, `system-bootstrap.ts` (literal strings only)
- Test: `pi-ext/factory-watch/test/system-page-visual-identity.test.ts`

- [ ] **Step 1: Produce the audit table FIRST**

Before changing anything, walk every literal user-facing string in those three files and record a decision per string in your report:

| String | Site | Decision | Replacement |
|---|---|---|---|
| "Declared scopes" | shell | Plain | "Features and artifacts" |
| "Start with weak or unbundled features, then follow their evidence spine." | shell | Plain | *(rewrite)* |
| "BUNDLE SCOPE" | bootstrap | Contract + gloss | *(keep, ensure gloss)* |

Three decisions only: **Plain** (rewrite in words a newcomer knows), **Contract word — keep + gloss** (it names a real artifact kind or state and must match the CLI; ensure a gloss or `ⓘ` is present at that site), **Leave** (already plain).

- [ ] **Step 2: Write a test that pins the landing instruction**

```ts
test("the landing's first instruction uses no undefined tool vocabulary", () => {
  const html = renderSystemPageHtml();
  const lead = html.match(/<p class="landing-lead">([^<]*)</)?.[1] ?? "";
  ["evidence spine", "unbundled", "weak"].forEach((jargon) => {
    expect(lead.toLowerCase()).not.toContain(jargon);
  });
});
```

- [ ] **Step 3: Apply the audit**

Rewrite only the strings marked **Plain**. Contract words are never renamed — the browser and the CLI stay one language.

- [ ] **Step 4: Verify**

Run: `cd pi-ext/factory-watch && npm test`

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test/system-page-visual-identity.test.ts
git commit -m "docs(system): plain-language framing text, contract words kept"
```

---

## Task 9: Gates and the newcomer test

**Files:**
- Modify: `pi-ext/factory-watch/test/system-browser-validation.test.ts`

- [ ] **Step 1: Extend the browser gate**

Add steps INSIDE the existing single test, reporting via `record(vp, step, message, element)` — do NOT add new `test()` blocks; that breaks the report contract.

- per-element containment for the ladder: each `.trace-spine-step` has `scrollWidth <= clientWidth + 1`, and every `.ref-chip` right edge is inside its step
- no chip title visually truncated at 1440×900 (compare `scrollWidth` to `clientWidth` on `.chip-title`)
- an orientation line is present and non-empty for every tab
- the shape sentence is present on the landing
- anchor chips carry both `href` and `data-scope`

- [ ] **Step 2: Run both targets to completion**

```bash
BROWSER_GATE=1 npx vitest run test/system-browser-validation.test.ts
BROWSER_GATE=1 BROWSER_GATE_TARGET=C:/coding/pi-agent-factory npx vitest run test/system-browser-validation.test.ts
```

The gate targets `bundle:reactive-planner` deliberately — it is the populated repro scope. Expect ~500s for the three-viewport run. Report the findings list for both.

- [ ] **Step 3: The newcomer acceptance test**

Dispatch an independent agent, told NOTHING about this tool, the coding agent, or the project. Give it only the rendered page against `cool_physical_ai_project`. Ask it to answer, in its own words:

1. What is this project made of?
2. What is this page showing me?
3. What does "RECORDED" mean? What does "fresh" mean?
4. What is SR-030?
5. What should I look at first?
6. Pick something marked "Not recorded" — what would you do about it?
7. **Control:** what is the author's name of the third requirement? *(Not on the page. An agent that answers this is guessing agreeably, and its other answers are suspect.)*

Record the answers verbatim and judge them against the real data. **A confident wrong answer is a failure, not a pass.**

- [ ] **Step 4: Commit**

```bash
git add pi-ext/factory-watch/test/system-browser-validation.test.ts
git commit -m "test(system): gate the ladder, orientation lines and chip links"
```

---

## Self-Review

**Spec coverage:** Component 0 → Task 5. Component 1 → Task 1. Component 2 → Task 3. Component 3 → Task 2. Component 4 → Task 4. Component 5 → Tasks 6, 7. Component 6 → Task 8. Verification → Task 9.

**Ordering rationale:** Task 1 is standalone and unblocks reading. Task 2 changes `refChip`'s return type, so it precedes Task 3, which renders many chips. Task 4 and Task 5 both add Python wording tables and are independent of each other. Tasks 6 and 7 are residuals with no dependents. Task 8 is text-only and last before the gates, so it audits the final strings.

**Type consistency:** `refChip` returns `HTMLAnchorElement | HTMLSpanElement` from Task 2 onward; Tasks 3 and 7 must not assume a span. `PANELS_DATA` is defined in Task 4 and read by Task 9's gate.

**Known gaps carried deliberately:** the 11 `GapKind` remediation states stay CLI-only (they need a gaps projection the browser does not receive); the spec's promise that they render is removed rather than left aspirational.
