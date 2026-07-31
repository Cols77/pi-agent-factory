---
id: kb-0001
title: "Example: flaky retry needs a longer backoff"
status: active
severity: medium
created: "2026-07-16"
last_seen: "2026-07-16"
occurrences: 1
tags: [example, retry]
scope:
  files: ["src/example/retry_client.py", "src/example/scenarios/**"]
  error_signatures:
    - "ConnectionResetError"
    - "timeout after"
detection: ""
---

## Symptom
Retry logic flakes under load when the backoff is too short to let the
downstream service recover from a transient outage.

## Root cause
`retry_with_backoff` needs enough delay between attempts to avoid
overwhelming the target while it is recovering.

## Rule / fix
Use exponential backoff starting at 200ms with at least 5 attempts before
giving up.
