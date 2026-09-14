# Coherence plan requirement authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `author-requirements` an executable provisional-authoring stage of the `$coherence-plan` host workflow without allowing automatic consent, adoption, or downstream execution.

**Architecture:** The Coherence backend remains the lifecycle authority and continues to project `author-requirements` from missing requirement evidence. The project-local skill becomes a five-action bounded author/review loop: it may draft and manifest provisional requirement artifacts, then must re-query Coherence and stop at `record-sr-consent`. Contract tests validate the skill text because this behavior is implemented in the host instruction surface rather than a Python runtime dispatcher.

**Tech Stack:** Markdown skill contract, Python/pytest contract tests, Coherence legal-actions helper, SHA-256 artifact-manifest workflow.

---

## Context and file map

- `.agents/skills/coherence-plan/SKILL.md` is the host workflow contract. It must distinguish provisional requirement authoring from human consent and preserve the existing no-merge/no-push/no-downstream rules.
- `tests/unit/codex/test_coherence_plan_contract.py` parses the skill contract and asserts the exact executable action set and safety language.
- `docs/superpowers/specs/2026-09-14-coherence-plan-requirements-authoring-design.md` is the approved design authority.
- `docs/features/FEAT-019.md` is the current dogfood context: requirements are empty and explicitly pending human-approved authoring.
- `.agents/skills/coherence-plan/scripts/coherence_plan.py` is read-only projection infrastructure and must not be modified.

### Task 1: Add failing contract coverage for requirement authoring

**Files:**

- Modify: `tests/unit/codex/test_coherence_plan_contract.py:91-160`

- [ ] **Step 1: Expand the expected executable action set and add provisional-authoring assertions.**

Change `test_safe_loop_preserves_exact_allowlist_and_current_backend_actions` so the expected list begins with `author-requirements`:

    assert _safe_loop_allowlist(body) == [
        "author-requirements",
        "author-spec",
        "author-plan",
        "review-spec",
        "review-plan",
    ]

Add this test directly after it:

    def test_requirement_authoring_is_provisional_and_stops_before_consent() -> None:
        _, body = _frontmatter_and_body(SKILL_PATH)
        section = _section(body, "Safe fix-review-fix loop")
        normalized = " ".join(section.lower().replace(chr(96), "").split())

        assert "author-requirements" in normalized
        assert "provisional" in normalized
        assert "requirement artifacts" in normalized
        assert "complete artifact manifest" in normalized
        assert "fresh sha-256" in normalized
        assert "record-sr-consent" in normalized
        assert "stop before consent" in normalized
        assert "never grant consent" in normalized
        assert "never adopt requirements" in normalized

Keep the existing assertions that backend actions are rendered exactly, display-only actions are not translated or auto-selected, and the loop does not claim completion without evidence.

- [ ] **Step 2: Run the focused contract test to verify the new test fails for the missing behavior.**

Run:

    rtk uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''

Expected result: failure in the exact-allowlist assertion because the current skill exposes only four executable actions, plus failure in the new test because the requirement-stage safeguards are absent.

### Task 2: Make provisional requirement authoring a first-class bounded stage

**Files:**

- Modify: `.agents/skills/coherence-plan/SKILL.md:82-129`

- [ ] **Step 1: Add `author-requirements` to the exact bounded-loop allowlist.**

Replace the current four-item list with this ordered list:

    Only these backend-declared actions may enter the bounded loop:

    - author-requirements
    - author-spec
    - author-plan
    - review-spec
    - review-plan

Update the loop wording from “exact four allowlisted IDs” to “exact five allowlisted IDs” and preserve the rule that every action must come from the latest backend projection.

- [ ] **Step 2: Document the requirement-authoring operation and write boundary.**

Insert this subsection immediately after the allowlist and before the display-only-action paragraph:

    When the projection declares author-requirements, author only provisional
    requirement candidates or explicitly identified revisions within the named
    feature's scope. Inspect the feature dossier and bounded repository context
    before drafting. If the request and context do not support a concrete
    requirement, stop and ask for clarification rather than inventing one.

    Requirement files are candidates, not adopted canonical requirements. Preserve
    unrelated dirty worktree changes and do not modify the feature dossier, spec,
    plan, bundle, intent journal, consent records, gates, handoff, or downstream
    execution state while drafting requirements. Make existing-SR revisions
    visible as revisions.

    After authoring, validate the requirement artifacts and write the complete
    current artifact manifest through the governed producer with fresh SHA-256
    values. Re-run the legal-actions helper after every state-changing operation.
    When the resulting projection declares record-sr-consent, stop and present
    the candidates and hashes for separate human decisions. Never invoke consent
    or adoption automatically.

- [ ] **Step 3: Keep consent and all later actions outside automatic authoring.**

Ensure the same section explicitly states that record-sr-consent,
run-planning-gates, create-handoff, inspect-handoff, and any other
non-allowlisted action remain display-only. Preserve the existing boundaries
that the skill never grants consent, adopts requirements, accepts warnings,
launches downstream work, merges, or pushes.

- [ ] **Step 4: Run the focused contract tests to verify the minimal change passes.**

Run:

    rtk uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''

Expected result: all tests in the contract module pass, including the exact
five-action allowlist and provisional-authoring assertions.

### Task 3: Verify the live FEAT-019 projection and preserve repository state

**Files:**

- Verify: `.factory/planning/FEAT-019/`
- Verify: `docs/features/FEAT-019.md`
- Verify: `.agents/skills/coherence-plan/SKILL.md`
- Verify: `tests/unit/codex/test_coherence_plan_contract.py`

- [ ] **Step 1: Run the related integration surface.**

Run:

    rtk uv run pytest tests/integration/test_codex_coherence_plan_surface.py -q -o addopts=''

Expected result: the existing Coherence plan host-surface tests pass without
creating consent, handoff, or downstream execution evidence.

- [ ] **Step 2: Re-query Coherence's authoritative projection for the named run.**

Run:

    rtk uv run python .agents/skills/coherence-plan/scripts/coherence_plan.py legal-actions --project-root . --run-id FEAT-019

Expected result: schema-2 output remains state: "capture", blocked: false,
legal_next_actions: ["author-requirements"], and starts_automatically: false.
The skill change must not mutate planning state.

- [ ] **Step 3: Inspect the diff and confirm only intended new hunks are present.**

Run:

    rtk git diff -- .agents/skills/coherence-plan/SKILL.md tests/unit/codex/test_coherence_plan_contract.py
    rtk git status --short

Confirm that the pre-existing feature-shorthand hunks and other dirty files
remain intact, no planning state was hand-edited, and no consent or adoption
record was created.

- [ ] **Step 4: Commit only the requirement-authoring contract change when its hunks can be isolated safely.**

Before committing, inspect the staged diff and stage only the new allowlist,
provisional-authoring, and contract-test hunks. Do not include existing
feature-shorthand hunks or unrelated dirty files. Use this focused message:

    git diff --cached --check
    git diff --cached -- .agents/skills/coherence-plan/SKILL.md tests/unit/codex/test_coherence_plan_contract.py
    git commit -m "fix(coherence-plan): enable provisional requirement authoring"

If existing hunks cannot be isolated without risking user changes, leave the
implementation as an uncommitted, fully verified diff and report that
condition instead of staging unrelated work.

## Self-review checklist

- The approved design's problem and decision are covered by Tasks 1 and 2.
- Provisional status, feature-scoped writes, revision visibility, fresh
  manifest hashes, and the post-authoring projection are covered by Task 2.
- Human consent, adoption, warnings, downstream execution, merge, and push
  remain prohibited by Task 2 and are checked by existing contract tests.
- Task 3 verifies that no runtime projector or planning-state mutation is
  introduced.
- The red-green sequence is explicit and the expected failure is the current
  four-action allowlist plus missing safeguard language.
