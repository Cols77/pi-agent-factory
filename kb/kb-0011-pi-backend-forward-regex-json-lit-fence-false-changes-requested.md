---
id: kb-0011
title: "pi_backend forward regex for ```json blocks misparses when thinking block contains a literal ```json fragment, yielding false 'changes-requested'"
status: active
severity: high
created: "2026-08-05"
last_seen: "2026-08-05"
occurrences: 2
resolved_at: "2026-08-05"
resolved_by: "c9ecaf8"
tags: [pi-backend, review, parsing, false-positive, iteration-waste]
scope:
  files: ["src/factory/orchestrator/pi_backend.py"]
  error_signatures:
    - "review result 'changes-requested' with findings: 0, gate: 0, verify: []"
    - "parse_pi_json returning {} on valid agent output"
detection: "Session JSON shows a review node with 'result': 'changes-requested', 'extra.findings': 0, 'extra.gate': 0, and 'extra.verify': []. The agent's actual JSON output was correct but was never parsed. Indicates the JSON extraction regex matched a literal ```json fragment in the thinking block instead of the real output block."
---

## Symptom

The review node returns `changes-requested` with **0 findings, 0 gate, and empty verify** even though the agent's JSON output was well-formed and correct. The pipeline restarts the dev→validation→review loop for no reason. `parse_pi_json` returns `{}` because the extraction regex matched the wrong region.

Observed twice in **T-051** (iterations 1 and 3): both review nodes had `findings: 0, gate: 0, verify: []`.

## Root cause

`parse_pi_json` used a forward `re.findall` regex (`r"```json\s*(.*?)```"`). Agents frequently quote the task prompt in their thinking block — and the prompt says *"emit ONLY a fenced ```json block"*. That literal ```` ```json ```` fragment appears **before** the real JSON output. The forward `findall` matched the quoted fragment first and swallowed the real JSON block's closing fence, so the real block was never extracted.

## Rule / fix

Search backward from the end of the stream, not forward:

- Use `full.rfind("```json")` to find the **last** occurrence.
- Then `full.find("```", start + len("```json"))` to find the closing fence after it.
- Parse that substring as JSON.

This is implemented in commit `c9ecaf8` along with a regression test (`test_parse_extracts_json_when_thinking_contains_literal_fence`).

**Caveat:** backward search assumes the real JSON is always the *last* fenced ```json block. If an agent ever emits a ```json block in a text/postscript after the real JSON output, this would pick the wrong one. Consider tightening the protocol so the agent emits exactly one ```json block (e.g., reject output containing more than one).