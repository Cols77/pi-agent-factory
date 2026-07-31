---
id: kb-0004
title: "Windows 'nul' reserved device name breaks git add -A in factory pipeline"
status: active
severity: high
created: "2026-07-28"
last_seen: "2026-07-28"
occurrences: 1
tags: [windows, git, pipeline, commit, gates]
scope:
  files: ["src/factory/orchestrator/git_ops.py", "sessions/.factory-run.log"]
  error_signatures:
    - "error: invalid path 'nul'"
    - "fatal: adding files failed"
    - "CalledProcessError: Command '\\['git', 'add', '-A'\\]' returned non-zero exit status 128"
detection: "A dev or review node fails to commit because `git add -A` crashes with `invalid path 'nul'` even though `nul` is listed in `.gitignore`."
---

## Symptom

`git add -A` fails on Windows with:

```
error: invalid path 'nul'
error: unable to add 'nul' to index
fatal: adding files failed
```

This causes the factory's `git_ops.commit_all()` to raise a `CalledProcessError`, which aborts the pipeline node. The dev agent then exhausts retries and escalates, even though the actual code changes were correct.

## Root cause

On Windows, `nul` is a reserved device name (analogous to `/dev/null` on Unix). The repository root contains a file or path reference named `nul` (0 bytes). Despite being listed in `.gitignore`, `git add -A` on some Windows git versions still attempts to access the path and fails because the OS intercepts `nul` as a device handle rather than a filename.

The `.gitignore` entry (`nul`) is insufficient to prevent the failure because git's `add -A` code path hits the invalid path before the ignore filter is applied, or the ignore filter is bypassed when using `-A` (which also adds deleted/renamed files).

## Rule / fix

1. **Immediate workaround in `git_ops.py`**: Replace `git add -A` with `git add --ignore-errors .` (or `git add <specific paths>`) so that the `nul` path error is non-fatal.

2. **Remove the `nul` file from the working directory**: Run `git rm --cached nul` (if tracked) or simply delete the physical `nul` file. If it's a Windows device reference that can't be deleted, use `git config core.protectNTFS false` temporarily to allow git to handle it.

3. **Add a pre-commit hook** that sanitizes the index before `git add -A` is invoked, or use `git add --renormalize` instead.

4. **Long-term**: Add a `pre-commit` or `pre-add` check in the factory's `git_ops.py` that explicitly excludes paths matching Windows reserved names (`nul`, `CON`, `PRN`, `AUX`, etc.) when running on Windows.