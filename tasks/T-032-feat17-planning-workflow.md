---
dod:
- "The deterministic planning checker validates schema-versioned intent, authority spec, plan/task parity, answer coverage, and current artifact hashes."
- "Planning runs persist canonical reports and require an exact external human review decision before downstream suggestion."
- "The plan CLI exposes check, bootstrap, and suggestion-only commands without starting governed development or writing approval."
- "The factory-watch plan seed routes authoring through the backend gate and preserves the deferred human-review/consent seam."
- "Focused tests, lint, type checks, register, health, and trace gates pass; no push or merge occurs."
id: T-032
justification:
- satisfies: SR-043
- satisfies: SR-044
- satisfies: SR-050
- satisfies: SR-051
- satisfies: SR-052
- satisfies: SR-053
- satisfies: SR-054
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 1
status: todo
title: "Deliver FEAT-017 deterministic planning bootstrap workflow"
---

## Scope

- Add: `src/coherence/planning/model.py`, `check.py`, `run.py`, `bootstrap.py`, and `cli.py`.
- Modify: `src/coherence/cli.py`.
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`.
- Add focused planning checker, run, CLI, bootstrap, and trace-contract tests.
- Register FEAT-017 SR-043/SR-044/SR-050–SR-054 in the feature dossier and bundle.

## Contract

The backend owns persistence, path validation, parsing, hashes, findings, review-decision validation, and downstream gates. The host prompt may author intent/spec/plan text and render canonical JSON, but it must not reimplement the checker, fabricate human approval, write review decisions, launch FEAT-13, or start governed development automatically.

The planning bootstrap may explicitly decompose a plan using the existing `substrate.ledger.plans.run` machinery. It emits delegated requirement-consent and health-resolution registration next actions; it does not create SRs, feature dossiers, bundles, or approval decisions.

## Verification

Run the focused planning suite with `uv run pytest ... -o addopts=''`, `uv run ruff check src tests`, `uv run pyright`, and the available `coherence register check`, `coherence navigate health --json`, and `coherence trace check` gates. Record pre-existing unrelated gaps rather than weakening or hiding them.
