---
dod:
- 'PANELS_DATA includes a Catchup entry with label, what_it_shows, and
  how_to_read text, so selecting the Catch me up tab renders a non-empty
  orientation line.'
- 'The orientation test matches the tab visibility contract: hidden tabs are
  not asserted as rendered for another scope, while the Catchup scope is
  explicitly covered.'
- 'A Catchup scope selects the Catch me up tab and renders its orientation
  line without a blank panel-orientation element.'
- 'The factory-watch Vitest suite and watch extension gate pass.'
id: T-031
justification:
  - corrects: NC-0001
source_plan: null
status: done
title: 'Add Catchup tab orientation metadata and coverage'
---

## Scope

- Modify: `pi-ext/factory-watch/src/system-vocabulary-data.ts`
- Modify: `pi-ext/factory-watch/test/system-page-dom.test.ts`
- Add or modify focused Catchup navigation coverage if needed.

## Background

The watch-extension gate currently fails with `no orientation for tab Catchup`.
The static shell declares `#tabCatchup`, but `PANELS_DATA.panels` has entries
through `Diagram` only. The bundle-scope test also inspects every `[role=tab]`
without filtering hidden tabs, even though `configureTabs('bundle')` hides
Catchup. A Catchup scope must still receive its own orientation text when the
tab is visible and selected.

This predates Coherence Increment 2: the Increment 2 diff does not touch the
factory-watch source or tests.

## Acceptance

- Selecting Catch me up on a Catchup scope produces non-empty text in
  `#panelOrientation`.
- The bundle-scope orientation test does not fail merely because a hidden
  Catchup tab exists in the static shell.
- The test suite covers both the hidden-tab filtering contract and the visible
  Catchup orientation contract.
- `npm test --prefix pi-ext/factory-watch` passes.
- `tests/gates/test_watch_ext_gate.py` passes.
