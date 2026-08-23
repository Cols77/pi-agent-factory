---
id: NC-0001
title: Catchup tab has no orientation metadata
external_ref: gh-issue:1
detected_by: gate-flake-investigation
status: corrected
corrected_by: T-031
---

## Symptom

The watch-extension gate intermittently failed with `no orientation for tab Catchup`. The static
shell declares `#tabCatchup`, but `PANELS_DATA.panels` had entries through `Diagram` only. The
bundle-scope test also inspected every `[role=tab]` without filtering hidden tabs, even though
`configureTabs('bundle')` hides Catchup — so the failure surfaced only under some tab-visibility
orderings, reading as vitest flakiness rather than a missing-data bug.

Filed as GitHub issue #1 ("pi-ext factory-watch vitest suite is flaky under full parallel run"),
discovered while finishing `feat/coherence-increment-1c`.

## Correction

`T-031` adds a `Catchup` entry to `PANELS_DATA.panels` (label, `what_it_shows`, `how_to_read`) and
fixes the bundle-scope orientation test to respect the tab-visibility contract: hidden tabs are
not asserted as rendered for a scope that hides them, while the Catchup scope's own orientation
line is explicitly covered.
