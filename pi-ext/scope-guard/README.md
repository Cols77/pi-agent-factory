# scope-guard — Pi extension

Deterministic write-scope enforcement for factory agents. Blocks `write`/`edit`
outside an allowlist and blocks `bash` unless permitted. This is the *sole*
scope guard (no orchestrator backstop, by design) — treat its tests as
safety-critical.

## Env contract (set per agent node by the orchestrator)
- `PI_SCOPE_ALLOW` — comma-separated repo-relative globs of writable paths.
  Unset/empty ⇒ no writes allowed (read-only role).
- `PI_SCOPE_BASH` — `allow` | `deny`. Unset ⇒ `deny` (fail-closed).

## Load into Pi
```
pi --extension pi-ext/scope-guard/src/index.ts -p "<prompt>" --mode json
```

## Test
```
npm --prefix pi-ext/scope-guard run typecheck
npm --prefix pi-ext/scope-guard test
```
