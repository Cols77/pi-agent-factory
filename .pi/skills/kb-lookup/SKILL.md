---
name: kb-lookup
description: Use as the Dev role when the prompt lists knowledge-base entry IDs - read the full entry before implementing, since only the id and title are injected automatically
---

# KB Lookup

## Overview

This factory keeps a deterministic, append-first knowledge base under `kb/` — one file per entry, each documenting a symptom, root cause, and fix for a mistake this codebase has made before. Entries are selected for you automatically, but **only their `id` and `title` are injected into your prompt** — you have to go read the actual fix.

## What You Actually See

If your prompt has a `## Known issues (knowledge base)` section, it looks like this:

```
## Known issues (knowledge base)
- kb-0001: PyBullet drone: goto before settle reads stale pose
```

That's it — no symptom, no root cause, no fix. This is intentional (`compose_prompt` in `src/factory/orchestrator/prompts.py` only surfaces `id`/`title`), but it means the id alone is not useful on its own.

## What To Do

**Before implementing, read every listed entry's full file:** `kb/<id>-*.md` (e.g. `kb/kb-0001-pybullet-arming.md`). Each entry has this shape:

```markdown
---
id: kb-0001
title: "..."
status: active            # active | superseded | archived
severity: high            # high | medium | low
tags: [...]
scope:
  files: ["src/flight/**"]
  error_signatures: ["AssertionError: altitude did not increase"]
---

## Symptom
...
## Root cause
...
## Rule / fix
...
```

The `## Rule / fix` section is the actual actionable guidance — apply it, don't just acknowledge the entry exists.

## How Entries Get Selected (so you know what you're NOT seeing)

Selection is deterministic, done by the orchestrator before you're ever invoked (`src/factory/kb/retrieval.py`'s `select_entries`), not by you:

- Only entries with `status: active` are eligible.
- Matching today is **by touched-file glob only** (`scope.files`, matched via `fnmatch` against the manifest's `context.source_files`). The orchestrator currently calls this with an empty error-signature list, so **`scope.error_signatures` substring-matching is not actually wired up yet** — don't assume a KB entry will surface just because your error message matches its `error_signatures`; it won't, unless the files you're touching also match `scope.files`.
- This means: if you're touching a file not covered by any entry's `scope.files` glob, you'll see no KB entries at all, even if a relevant one exists. If you suspect there's a relevant lesson that isn't showing up, it's fine to look at `kb/*.md` directly rather than assuming silence means "nothing relevant exists."

## What NOT To Expect

There is currently no mechanism for you to append a new KB entry or have "lessons learned" during this run automatically written to `kb/` — the KB-Manager role that would do that curation is explicitly not built yet (design spec, Milestone 2). If you discover something worth recording as a new lesson, say so clearly in your response text (not as a fenced JSON block, which would be mistaken for your primary output) so a human can add it — don't silently skip it, and don't invent a mechanism to write it yourself outside your granted write scope (`src/**`, `tests/**`).

## Red Flags

- Treating the bare `id: title` bullet as sufficient context — it isn't; go read the file.
- Assuming an entry with a matching `error_signatures` string will show up in your prompt automatically — it won't unless the file-glob side also matches.
- Writing directly to `kb/` — that's outside Dev's scope (`ROLE_SCOPE[AgentRole.DEV].allow` is `src/**`, `tests/**`).
