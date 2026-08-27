# Coherence Execution Runbook — new-session boot & governed execution

_Date: 2026-08-27._ This runbook tells a FRESH Hermes session how to execute the Inc-09
planning docs correctly — with proper Coherence tool execution for traceability. It is the
operational companion to the three plans and the session capture.
Do NOT push/merge to main until the user explicitly says so.

## 0. Free-model + infra status (verified 2026-08-27)

- **Reliable:** `nvidia/nemotron-3-ultra-550b-a55b:free` (the workhorse).
- **DEAD — do not use:** `stealth/ox-alpha` (HTTP 404, retired → `z-ai/glm-5.3-flash`).
- Fallback pool order: nemotron first; glm-5.2:free only as a saturated-fallback slot.
- Worktrees need their OWN `.venv` (`uv sync --all-groups`); a fresh `git worktree add` has none.
- Windows: pass native `C:/...` paths to git/uv (never `/c/...`).

## 1. Session boot (self-orient, then verify the seed)

1. **Anchor the project:** `project_switch` / `project_create` to `C:/coding/pi-agent-factory`.
2. **Load the governing skills** (skill_view): `pi-agent-factory`, `subagent-increment-workflow`,
   `free-worker-dev-gate-pipeline`, `coherence-health-resolution`, `plan`.
3. **Read, in order:** the session capture
   `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md`, then the three
   plans (health-resolution, console, dossier), then this runbook.
4. **Verify the seed yourself** — do not trust this doc's numbers blindly. Run:
   `coherence navigate health --json` and `coherence register check` and record the current baseline
   (it may have drifted — that's the health-resolution T-1 job). If it disagrees with the plan's
   recorded baseline, use the LIVE numbers, not the stale ones.

## 2. Execution order (locked)

`health-resolution (T-1..T-6) → 11 → 9 → 12 → 10`, then the dossier surface. Concretely:
1. **Health-resolution first** — the register + features + obligations + link-closure MUST exist
   before any new surface reads them, or consoles render hollow.
2. **Console slice** (C-1..C-4) — scaffolds the shared page + HEALTH tab.
3. **Dossier slice** (D-1..D-5) — mounts on the console page, depends on C-2 scaffold + on
   health-resolution having registered features.
(Teach is deferred — do not start it this session.)

## 3. Per-task loop — the governed execution driver

Run **every** task in the plan as a small deterministic loop. Do NOT improvise or chain tasks
without the gate. This loop operationalises **FEAT-13 GOVERNED-EXECUTION-DRIVER**
(design: `docs/superpowers/specs/2026-08-27-feat13-governed-execution-driver-design.md`) — the
host driver that plugs free/Hermes subagents + worktrees into the existing factory node pipeline
as worker nodes, with a reviewer swarm + fixer-until-silent, MCP + backend-gated.

```
for each task:
  1. Create/enter a WORKTREE off main (fresh .venv, uv sync --all-groups).
  2. DEV: dispatch a free worker (nemotron) on a razor-sharp brief (scope, files,
     verify command, acceptance). --query-file via `hermes chat ... -Q`.
  3. REVIEW (PARALLEL, two angles): spec-compliance reviewer + code-quality/security reviewer,
     dispatched together on the worktree. Write report files to disk — never trust the exit code.
  4. FIXER (fresh context) if either reviewer has findings: fix ONLY those + add regression tests.
  5. RE-REVIEW the combined commits until BOTH reviewers have no further comments (fixers-until-silent).
  6. COHERENCE GATE — the traceability step:
       coherence register check        # no "no account" pending for touched SRs
       coherence navigate health --json  # touched dims move, not regress
       verify codemap edges: grep -rn "satisfies.*SR-" <touched files>   (D-D)
  7. Commit ONLY after the gate passes (scoped git add; exact message from the plan).
  8. Independent re-verify the acceptance command yourself (exit 0 = real pass). Never trust a
     subagent's "N passed"/"report written" claim — check the file/exit code yourself.
```

- **Two reviewers, different focuses, fail-closed** — never skip the code-quality angle.
- **Subagents self-report; verify.** A "completed" flag without an on-disk report = not done
  (happened twice this session — re-dispatch with write-early mandat, or do it yourself).

## 4. Coherence tool execution & traceability (the point)

- Every produced artifact carries codemap `satisfies`/`implements` edges to its SR.
- The register/obligation/test-marker gates (not prose) validate those edges.
- `human_review` (dim is 0/0) can ONLY go green with a real human review entry — the user must do
  it; an agent cannot self-cert. Surface approval requests, don't fake them.
- Progress = streamed (FEAT-12) when available; otherwise log node transitions to the transcript.

## 5. Commit & handoff discipline

- Commit per task on a feature branch (never `git add -A`; scoped adds per worktree).
- **Never push or merge to main until the user explicitly says so** ("yes push" / "merge").
- Keep a status table: task → dev SHA → review verdicts → gate → status, so progress is visible
  while subagents run async.

## 6. If a reviewer finding contradicts a VERIFIED SEED / real source

Re-read the source / re-run the command yourself first. Reject findings that contradict
ground truth (record in a REJECTED section). Only then fix.

## 7. Definition of done for the session

health-resolution leaves `coherence navigate health` green (evidence-backed, human-reviewed),
and the console + dossier slices ship a working, trace-linked shared page both Pi and Hermes
mount — all committed to the feature branch, none pushed. Every gate was run, every edge present.