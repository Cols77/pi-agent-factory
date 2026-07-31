---
id: kb-0007
title: "context-completeness-audit skill example manifest format contradicts schema — all context-gather attempts fail"
status: active
severity: high
created: "2026-07-31"
last_seen: "2026-07-31"
occurrences: 1
tags: [context-gather, schema, skill, manifest, validation]
scope:
  files: [".pi/skills/context-completeness-audit/SKILL.md", "src/factory/schemas/context_manifest.schema.json", "src/factory/validation/manifest_validator.py"]
  error_signatures:
    - "Additional properties are not allowed ('proven' was unexpected)"
    - "coherence/checks/\\d+: 'kind' is a required property"
    - "coherence/checks/\\d+: 'args' is a required property"
    - "coherence/checks/\\d+: Additional properties are not allowed ('evidence', 'pass' were unexpected)"
detection: "Every context-gather node fails schema validation. The session JSON shows 'outcome': 'rejected' with 'attempts': 2, and the node 'extra.errors' contain the schema violations above. The agent output contains 'proven', 'pass', and 'evidence' fields that the schema rejects."
---

## Symptom

Every context-gather node in the pipeline runs to completion but its manifest is rejected by the gate. The session record shows:

```
"errors": [
  "coherence: Additional properties are not allowed ('proven' was unexpected)",
  "coherence/checks/0: 'kind' is a required property",
  "coherence/checks/0: 'args' is a required property",
  "coherence/checks/0: Additional properties are not allowed ('evidence', 'pass' were unexpected)",
  ...
]
```

The agent outputs a valid-looking JSON manifest with `proven: true`, `pass: true`, and `evidence` strings, but the schema rejects it. The task is abandoned after exhausting the 2-attempt retry limit without ever reaching Dev.

## Root cause

The skill file `.pi/skills/context-completeness-audit/SKILL.md` contains an example manifest in the **"Your Output Contract"** section that uses the **old format**:

```json
{
  "coherence": {
    "proven": true,
    "checks": [
      {"name": "task-exists-in-plan", "pass": true, "evidence": "tasks/T-012-....md"},
      ...
    ]
  }
}
```

However, the actual schema at `src/factory/schemas/context_manifest.schema.json` defines:

1. **`coherence`** has `"additionalProperties": false` — so `"proven"` is rejected.
2. **Check items** require `name`, `kind`, `args` — NOT `pass`/`evidence`.
3. **Check items** also have `"additionalProperties": false` — so `"pass"` and `"evidence"` are rejected.

The role prompt (in the context-gatherer template) IS correct — it says "Do NOT set any 'proven' or 'pass' field; the factory derives the verdict" and "Populate coherence.checks with entries of the form {\"name\": <str>, \"kind\": <str>, \"args\": {...}}". But the agent is told to load the `context-completeness-audit` skill, which contains a prominent example that contradicts the role prompt. The agent follows the skill's example instead of the role prompt's instructions.

The `manifest_validator.py` confirms this design: "Agent-supplied `proven`/`pass` are schema-rejected."

## Rule / fix

1. **Update `.pi/skills/context-completeness-audit/SKILL.md`** — replace the example manifest in "Your Output Contract" to match the current schema format:
   - Remove `proven` from `coherence` (it's derived by the gate, not supplied by the agent)
   - Change checks from `{"name": ..., "pass": ..., "evidence": ...}` to `{"name": ..., "kind": ..., "args": {...}}`
   - Remove the "The Gate That Actually Checks This" section's points #2 and #3 which reference `proven` and `pass` — those are no longer in the schema
   - Update the reject example to remove `proven` from the `coherence` object (since `additionalProperties: false`)

2. **Update the reject example** in the "When You Cannot Prove Coherence" section — the reject example shows `"coherence": {"proven": false}` but `proven` is no longer a valid property. For rejection, the manifest should have `"coherence": {"checks": []}` and `"reject": {...}`.

3. **Verify the update** by running a context-gather test against the schema:
   ```bash
   uv run python -c "
   import json
   from factory.validation.schema_validator import validate
   from pathlib import Path
   manifest = {
     'task_id': 'T-999',
     'generated_by': 'context-gatherer',
     'generated_at': '2026-07-31T00:00:00Z',
     'coherence': {'checks': [{'name': 'test', 'kind': 'files_exist', 'args': {'paths': ['tasks/T-043.md']}}]},
     'context': {'task': 'tasks/T-043.md', 'source_files': [], 'skills': []},
     'reject': None
   }
   errors = validate(manifest, Path('src/factory/schemas/context_manifest.schema.json'))
   print(errors or 'OK')
   "
   ```