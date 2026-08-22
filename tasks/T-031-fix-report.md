# T-031 fix report — Catchup tab orientation metadata

## Root cause

`PANELS_DATA.panels` (`pi-ext/factory-watch/src/system-vocabulary-data.ts`) had
13 entries, one per tab kind, but `system-bootstrap.ts`'s `TAB_ORDER` lists 14
(the 13 plus `Catchup`). `showTab()` looks up `PANELS_DATA.panels[name]` to
render the one-line orientation text under the tab strip; for `Catchup` this
lookup was `undefined`, so real users opening the "Catch me up" tab saw a
blank orientation line.

## The `PANELS_DATA.panels.Catchup` entry

```ts
"Catchup": {
  "label": "Catch me up",
  "what_it_shows": "The deterministic delta for this feature since your last recorded review: PRs merged, requirements and ADRs changed, goals reached or regressed, metric changes, and new open items.",
  "how_to_read": "Every field is computed, never an LLM summary -- a feature with no recorded review states that plainly, and a delta with no changes says so instead of rendering empty."
}
```

Phrasing rationale: `system-catchup-view.ts`'s header comment describes the
feature as a deterministic "since your last review" delta widget (spec
§31/§9.4) that renders only computed `ContextDelta` fields, never an
LLM-generated summary; a feature with no recorded review renders an honest
"no review recorded" state, and a delta with no changes renders "no changes".
I mirrored that description directly: `what_it_shows` names the concrete
fields the delta actually carries (mirroring the shape of `Sim`'s and
`Feature`'s entries, which enumerate what the panel displays), and
`how_to_read` states the "computed, never an LLM summary" guarantee plus the
two honest-empty-state behaviors, in the same terse, one-to-two-sentence
register as the other 13 entries (e.g. `Diagram`'s "The panel never generates
or re-derives a diagram -- when ... it states that explicitly instead."
pattern).

### Python source of truth also updated

`system-vocabulary-data.ts`'s header comment states it is "Generated from the
Python source of truth -- copied verbatim" from `src/factory/system/vocabulary.py`'s
`build_panels()`/`PANELS` dict, and `tests/unit/system/test_table_drift.py`
(`test_panels_mirror_matches_python`) asserts byte-for-byte JSON equality
between the two. This wasn't called out in the task's Scope section, but
leaving Python's `PANELS` dict without a `Catchup` entry would have broken
that drift test (previously passing, would regress to failing) and left the
two source-of-truth copies diverged. I added the identical `Catchup` entry
(same label, same `what_it_shows`/`how_to_read` text, reassembled from
Python's multi-line string literals to the same exact string) to
`src/factory/system/vocabulary.py`'s `PANELS` dict, immediately after
`"Diagram"`, matching the TS file's ordering. Verified with
`tests/unit/system/test_table_drift.py` (all 3 tests, including
`test_panels_mirror_matches_python`) — passes.

Also updated a now-stale comment in `system-bootstrap.ts`'s `showTab()`
("PANELS has all thirteen TABS_BY_KIND ids" -> "fourteen") since the count
changed.

## Tests added/changed

File: `pi-ext/factory-watch/test/system-page-dom.test.ts`

1. **No code change needed for the existing `"every rendered tab has an
   orientation line"` test** beyond adding the `Catchup` entry (see step 4
   below for reasoning) — but I updated its adjacent comment block from
   "thirteen" to "fourteen" tabs and added a note explaining why a hidden tab
   (Catchup, for a bundle scope) still needs its own `PANELS_DATA` entry, and
   pointing at the new test below for the visible/selected case.

2. **New test: `"a Catchup scope selects Catch me up and renders its
   orientation line"`** — the explicit Catchup-scope coverage the task's DoD
   requires (proving a *real page render* surfaces non-empty orientation
   text for Catchup, not just that a `PANELS_DATA` entry exists in the
   abstract). Modeled on `"the orientation line follows the active tab"`
   (same `loadPage`/DOM-query pattern) and on `system-catchup-view.test.ts`'s
   `CATCHUP` fixture shape for constructing a `catchup:`-prefixed scope
   payload (`system-page-dom.test.ts` itself had no prior `catchup:` scope
   usage, so I built the fixture from that sibling test's `query_catchup`
   payload shape: `feature`, `reviewed`, `since_commit`, `reviewed_at`,
   `delta`). It:
   - loads the page with `scope: "catchup:FEAT-001"`
   - asserts `#tabCatchup` is unhidden and `aria-selected="true"` (Catchup is
     the default tab for a `catchup:` scope kind, selected automatically by
     `loadScope()`/`selectInitialTab()`, no click needed)
   - asserts `#panelOrientation`'s text is non-empty and contains the exact
     `PANELS_DATA.panels.Catchup.what_it_shows` text

   Supporting fixture/plumbing added: a `CATCHUP` payload constant (empty
   delta arrays — only the orientation line was under test, not
   `renderCatchup`'s own rendering, which `system-catchup-view.test.ts`
   already covers thoroughly), a `/api/system/catchup` branch in `mockFetch`,
   and a `catchup` field threaded through `mockFetch`'s params and
   `loadPage`'s `opts`, following the same opt-in-with-default pattern
   already used for `health`/`traversal`/`labels`.

## Step 4: hidden-tab-filtering conclusion

**No test change was needed for the hidden-tab-filtering half of the DoD
line beyond what's described above.** Reasoning:

`"every rendered tab has an orientation line"` calls
`doc.querySelectorAll('[role="tab"]')` against the *static shell* HTML
(`system-shell.ts`), which always renders all 14 `<button role="tab">`
elements regardless of scope kind — `configureTabs()` only toggles `hidden`/
`aria-hidden` on them, it never removes them from the DOM. So this test was
never scope-kind-aware and never claimed a hidden tab was "rendered" in the
visual/active sense; it only checks a scope-independent invariant: every
static tab id in the shell has backing `PANELS_DATA` orientation text,
because `showTab()` can be invoked (via keyboard nav, URL hash, or a click on
an unhidden tab in a *different* scope) for any of the 14 names, and the
data model is per-tab-kind, not per-visibility. That invariant was already
correctly stated by the test — it was simply failing because `Catchup`'s
data didn't exist yet. Adding the `Catchup` entry alone fully satisfies it;
no filtering logic needed adding or fixing.

The DoD's actual two-part concern — (a) don't require every *scope* to
render every tab, and (b) do explicitly cover the Catchup-scope path — is
satisfied by: (a) this test already only exercises one scope (`bundle:b1`)
and only asserts on the *static* tab set, never on which tabs are visible
for that scope, so it makes no incorrect claim about other scopes' hidden
tabs; and (b) the new test in point 2 above, which is the "Catchup scope
actually renders it when visible and selected" proof the DoD asks for.

I did not make a speculative change here — I concluded the existing test's
assertion was already correct and scope-independent by design, and confirmed
that conclusion by reading `configureTabs()`/`showTab()` and the static
`system-shell.ts` markup before deciding no change was warranted.

## Verification output

### 1. `npm test --prefix pi-ext/factory-watch` (full suite)

```
 Test Files  90 passed | 2 skipped (92)
      Tests  1137 passed | 2 skipped (1139)
   Start at  12:58:11
   Duration  130.37s (transform 8.00s, setup 0ms, collect 145.54s, tests 118.98s, environment 66ms, prepare 40.73s)

[exited with code 0]
```

Focused run of the changed file alone (`system-page-dom.test.ts`), showing
the new/updated tests passing individually:

```
✓ test/system-page-dom.test.ts (33 tests) 8018ms
  ✓ every rendered tab has an orientation line 566ms
  ✓ the orientation line follows the active tab 468ms
  ✓ a Catchup scope selects Catch me up and renders its orientation line 301ms

 Test Files  1 passed (1)
      Tests  33 passed (33)
```

### 2. `npm run typecheck --prefix pi-ext/factory-watch`

```
> @factory/factory-watch@0.0.1 typecheck
> tsc --noEmit
```

(No output = no errors, exit code 0.)

### 3. `rtk proxy uv run python -m pytest tests/gates/test_watch_ext_gate.py -q` (from worktree root)

```
.                                                                        [100%]
1 passed in 212.07s (0:03:32)

[exited with code 0]
```

This gate test shells out to `npm --prefix pi-ext/factory-watch run typecheck`
then `npm --prefix pi-ext/factory-watch test`, so it's a genuine end-to-end
re-confirmation of commands 1 and 2 above from a clean subprocess.

### Bonus: Python drift test (not one of the 3 required commands, but load-bearing for the Python-source-of-truth change above)

```
uv run python -m pytest tests/unit/system/test_table_drift.py -q
...                                                                      [100%]
3 passed in 0.45s
```

## Concerns

- **Scope beyond the task file's stated file list**: the task's Scope
  section names only `system-vocabulary-data.ts` and
  `system-page-dom.test.ts` as files to modify, but I also touched
  `src/factory/system/vocabulary.py` (to keep the drift-tested Python source
  of truth in sync — see above) and made a one-line stale-comment fix in
  `system-bootstrap.ts` ("thirteen" -> "fourteen"). Both are small, low-risk,
  and necessary for correctness (the Python change specifically prevents a
  regression in `test_table_drift.py`), but flagging since they weren't
  explicitly listed.
- Three `pif-pulse-*` scratch directories appeared under
  `pi-ext/factory-watch/` as an untracked side effect of running the
  integration test suite (test files that spawn the real CLI, e.g.
  `eng-context-tools.integration.test.ts`, `system-cli.integration.test.ts`).
  These are a known pre-existing leak (see recent commit
  `17b8f75 feat(factory-watch): ... stop pif-pulse scratch leak`, which
  apparently didn't close every code path). I deleted them before committing
  so they wouldn't get swept into this change; not otherwise addressed here
  since it's out of scope for T-031.
- The task file `tasks/T-031-catchup-tab-orientation-metadata.md` was
  untracked in git (not previously committed) when I started; it's included
  in this commit as a new file (now with `status: done`) alongside the fix.
