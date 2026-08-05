---
id: kb-0012
title: "REVIEW role has bash=deny but its prompt doesn't say so; agent asks human to re-run gates validation already executed"
status: active
severity: medium
created: "2026-08-05"
last_seen: "2026-08-05"
occurrences: 1
resolved_at: "2026-08-05"
resolved_by: "ba6da8a"
tags: [review, roles, prompt, bash, gate]
scope:
  files: ["src/factory/orchestrator/roles.py", "src/factory/orchestrator/runner.py"]
  error_signatures:
    - "review 'verify' items telling the human to run commands that run_validation already executed"
    - "review agent hits bash denial at runtime with no guidance"
    - "SESSION_REVIEW prompt missing bash-disabled notice"
detection: "A review node returns 'pass' or 'changes-requested' but its verify items consist of pytest/git commands the reviewer tells the human to run — commands that run_validation already executed deterministically before run_review was called. Indicates the REVIEW prompt did not tell the agent bash is disabled."
---

## Symptom

The review agent returns a pass with a confidence note that it "could not execute pytest or git because bash is disabled in this review role" and appends verify items telling the human to run the suite and confirm the commit — even though `run_validation` already ran those gates deterministically before `run_review` was called. The agent wastes effort discovering bash is denied at runtime and improvising instructions to the human.

## Root cause

The REVIEW role has `Scope(bash="deny")` configured, but only CONTEXT_GATHERER's prompt stated bash was disabled. The REVIEW prompt gave no guidance, so the agent only discovered the denial when it actually tried to run a command at runtime, and had no fallback instruction to point at the run summary for already-completed validation results.

## Rule / fix

1. **Every bash-denied role must state in its prompt that bash is disabled** and that integration/sim suites already ran, pointing at the run summary for their results.
2. **`run_review` must pass `events` to `compose_prompt`** so the review prompt can render the run summary. Previously only SESSION_REVIEW was given the events.
3. **Add an invariant test** that every role with `bash="deny"` in its scope also declares that in its prompt. This invariant caught SESSION_REVIEW having the same latent gap.

Implemented in commit `ba6da8a`.