# Codex Intent Handoff — FEAT-003 planning workflow alignment

This file records the intent and design discussion from a Codex thread for a
later Claude or other coding-agent session. It is conversational context, not
Coherence authority. The coding agent must validate it against the backend
state, journals, projections, and tests. Do not treat this file as permission to
mutate planning state or begin implementation.

## Context

Run: `FEAT-003`

Feature: **NONCONFORMANCE-CLOSURE** — “Nonconformance closure records,
reviews, and resolves traceability and assurance failures.”

Requirements in scope:

- `SR-012`: record `NC-*` nonconformance records with schema/loader; malformed
  records become `scope_errors` without hiding the rest, and never become trace
  nodes.
- `SR-013`: mark governed edges suspect when endpoint fingerprints change;
  restore validity only through policy-authorized acceptance, never
  automatically.
- `SR-014`: surface open versus closed nonconformance closure in health, and
  expose a corrective task plus external issue reference from one `NC-*`
  record.

## Observed run state

The existing `.factory/planning/FEAT-003/` session contains a capture journal
whose first prompt is `Plan the feature FEAT-003`, with no captured answers or
challenges. Its derived state is `capture`.

- A requested `start` was rejected with `planning session already exists`.
- A requested `resume` succeeded, but only rehydrated the existing capture
  snapshot; it did not advance the workflow or generate a question.
- The authoritative legal-actions projection returned:

  ```json
  {
    "blocked": true,
    "reason": "SESSION_NOT_READY",
    "legal_next_actions": [],
    "state": "capture",
    "starts_automatically": false
  }
  ```

- The immediate backend condition is that
  `.factory/planning/FEAT-003/handoff.json` does not exist.
- The current backend test explicitly codifies blocking a capture session until
  a handoff is persisted: `tests/unit/coherence/test_planning_session.py`.

Relevant implementation evidence:

- `src/coherence/planning/session.py` rejects `start` when the journal exists.
- `resume_session` reconstructs the session from the journal.
- `legal_actions_session` returns `SESSION_NOT_READY` when `handoff.json` is
  absent.
- The backend action registry currently contains only
  `inspect-handoff`, `revalidate-handoff`,
  `select-downstream-workflow`, `create-downstream-session`, and
  `resolve-blocking-input`.
- The project-local Coherence skill instead names
  `author-spec`, `author-plan`, `review-spec`, and `review-plan` as the only
  actions allowed into its author/review loop.

## Agreed ownership boundary

The backend owns the authoritative planning state machine, legal transitions,
gates, hashes, structural validation, persistence, and blocking reasons.

The skill is a thin host adapter. It owns semantic interaction with the human:
choosing the next clarifying question, writing the spec and plan, dispatching
reviews, and transporting explicit human decisions. It must not invent legal
actions, infer completion, choose challenge dispositions, choose terminal
capture status, grant consent, or start downstream execution.

## Agreed capture behavior

An initial capture state with no answers and no challenges is normal. It must
not deadlock behind `SESSION_NOT_READY`; the workflow should move to its next
guided capture step.

The exact action identifier and transition contract remain to be designed. The
intended behavior is that the host can ask one semantic question, append the
human's answer, handle any backend-raised challenge, and only finalize capture
when the human explicitly says capture is complete and chooses the terminal
status. “No answers and no challenges” must not be treated as evidence that
capture is complete, and must not trigger automatic downstream work.

## Decisions confirmed during the ongoing grill

- The legal-action projection uses semantic IDs—such as `capture-answer`,
  `resolve-challenge`, and `finalize-capture`—while the existing CLI verbs
  (`append`, `resolve`, and `finalize`) remain the transport operations.
- `author-spec` becomes legal only after explicit `finalize(provisional)`, valid
  intent, and no unresolved challenges. An empty initial capture moves to the
  next capture step; it does not silently become spec authoring.
- One lifecycle-wide legal-actions projection should be authoritative for
  capture, author/review, and post-handoff routing. The guided CLI remains the
  mutation interface, but it must reject actions not currently declared legal.
- The human should be asked to choose the direction at every lifecycle
  transition, including capture → spec, spec → review, review → plan, and plan
  → handoff. The skill must not silently select a legal action.
- Legal actions should include backend-provided descriptors: ID, label, purpose,
  prerequisites, and required inputs. The skill renders these descriptors and
  collects the human's choice; it does not rename or invent them.
- Author/review route and completion transitions should be recorded in the
  run-local journal, including relevant artifact/review hashes, rather than
  inferred only from file presence.
- For semantic author/review work, use a two-phase select → perform →
  attest-completion handshake: the human selects the action; the backend
  journals the selection and returns the artifact contract; a coding agent
  performs the work; then the agent submits completion with the resulting hash
  for backend validation before the next action becomes legal.
- The completion producer is the coding agent, not necessarily Claude. A
  separate review agent then checks the artifact for completeness against the
  captured intent, feature context, and preceding artifact, and attests the
  review outcome before the workflow exposes the next transition.
- A non-clean review is a failed attestation with structured findings. It
  exposes a revision action (`revise-spec` or `revise-plan`) and keeps the next
  stage unavailable until the revised artifact receives a clean re-review.
  Human routing or disagreement adjudication may direct the loop, but cannot
  turn a failed completeness review into a pass by assertion.
- Any content-hash change to an artifact invalidates its review attestation and
  downstream attestations derived from it. The backend must require a fresh
  review rather than reusing a stale pass for the same path.
- Reviewer independence is enforced at the session/role level: the review
  session must be distinct from the author session, although the model or
  provider need not differ. Producer and reviewer provenance are both recorded.
- A clean review only unlocks the next legal action; it does not advance the
  workflow automatically. The host must ask for and receive the user's
  explicit authorization before proceeding.
- Every authorization checkpoint must also allow free-text user feedback. The
  feedback is durable context attached to the authorization decision; feedback
  requesting changes routes to revision, while feedback alone never silently
  advances the workflow.

## Current diagnosis: what is missing

### Missing from the skill

The skill needs an explicit lifecycle/action contract, not only a list of
author/review actions. In particular it should state:

1. Which backend-declared actions are legal during `capture`, including the
   initial no-answer state, answer append, challenge resolution, and capture
   finalization.
2. Which projection fields distinguish “normal next capture step” from a true
   block, and how the host obtains the next sequence number.
3. The exact transition after a human-selected `provisional` finalization:
   when `author-spec` becomes legal, then `review-spec`, `author-plan`, and
   `review-plan`.
4. Whether the legal-actions helper is a projection of the complete lifecycle
   or only a post-handoff projection. The skill currently assumes the former
   while the backend implements the latter.
5. How an existing capture session is resumed without treating a successful
   `resume` as workflow progress.

### Missing from the backend workflow

The backend needs a coherent, persisted state/action model for the full guided
planning lifecycle. At minimum it must define and test:

1. Capture-stage legal actions when the session has no answers or challenges.
2. Conditional challenge-resolution actions when unresolved challenges exist.
3. Human-controlled capture finalization and its prerequisites.
4. The transition into spec authoring, spec review, plan authoring, and plan
   review, with artifact hashes and review evidence bound to the run.
5. A legal-action registry whose identifiers match the actions the skill is
   permitted to perform, while keeping display-only downstream actions
   separate from executable planning transitions.
6. Fail-closed behavior for stale, contradictory, missing, or malformed state,
   without using the absence of a post-handoff file to block an ordinary
   capture question.
7. Durable route/completion events for every author/review transition, with
   hashes sufficient to validate that the referenced artifact or review is the
   one the run actually processed.

The backend currently has capture verbs (`start`, `resume`, `append`,
`resolve`, `finalize`) but its legal-actions projection does not model them.
Conversely, the skill names author/review actions that are not in the backend
registry. That is the central contract mismatch.

## Recommended direction to evaluate

Keep one backend-owned finite state machine and make `legal-actions` a
context-sensitive, read-only projection of that machine. Use separate action
classes or metadata for:

- capture progression (`append-answer`, conditional `resolve-challenge`, and
  human-selected `finalize-capture`);
- author/review progression (`author-spec`, `review-spec`, `author-plan`, and
  `review-plan`); and
- post-handoff display-only actions (`inspect-handoff`,
  `revalidate-handoff`, downstream workflow selection/session creation).

Each descriptor should identify its semantic action ID, preserve the existing
CLI operation used to carry it out, explain prerequisites, and identify which
inputs must come from the human or host. The skill should render the available
descriptors and pause for an explicit human route choice at every transition.
The backend should remain responsible for validating prerequisites and
rejecting stale or out-of-order requests. Journal route/completion events and
bind them to artifact/review hashes. No state should imply automatic
downstream execution; `starts_automatically` remains `false`.

Do not silently collapse the capture stage into `author-spec`: an empty initial
capture is not proof that the human has completed intent capture. If the
product deliberately wants an empty capture to advance directly, that must be
made an explicit backend transition and human decision, with tests and a clear
meaning for the resulting intent.

## Questions for Claude to grill next

Continue one question at a time and provide a recommended answer before each
question. Do not assume unresolved decisions are settled. The performer may be
Claude or another coding agent; the routing and attestation contract must not
depend on a particular host model.

1. Should capture actions use the existing verb names (`append`, `resolve`,
   `finalize`) or a distinct projection vocabulary (`append-answer`, etc.)?
2. What exact persisted state follows `finalize(provisional)` and which
   artifact/review records are prerequisites for each author/review action?
3. Should the legal-actions projection be the sole authority for both capture
   and author/review, or should capture have a separate legal-input projection
   with a shared backend registry?
4. How should multiple concurrent run IDs interact with the global
   `.intent/intent.json` materialization path? This is an additional risk to
   verify, not an agreed design decision.
5. Which tests prove that every skill action is backend-declared and that a
   fresh capture can progress without a handoff file?

## Boundaries

This handoff does not authorize implementation, requirement adoption, consent,
task execution, merging, or pushing. The next Claude session should first
finish the design interrogation, then obtain human approval before changing
the skill or backend.
