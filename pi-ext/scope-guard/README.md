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

## Constraint for whoever loads this extension (Plan 3 / the orchestrator)

Pi's `tool_call` event `input` is mutable across handlers: if another extension
registers a `tool_call` handler and runs *after* scope-guard, it can rewrite
`input.path` post-approval, and Pi does not re-validate after mutation. Since
this extension is meant to be the sole write-scope guard with no other
backstop, the orchestrator must load scope-guard as the only `tool_call`
handler (or, if others are ever added, guarantee scope-guard runs last and
nothing after it can still mutate `input`). This is not something scope-guard
can enforce from inside itself — it's a load-order invariant the caller owns.
