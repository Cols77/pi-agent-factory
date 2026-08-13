# Session-Continuity Memory — Design

**Status:** proposed · **Prototype:** landed in `pi-ext/factory-watch/src/session-memory.ts` (pure) + `session-memory-command.ts` (wiring) + `test/session-memory.test.ts`

## 1. Problem

The bootstrap (`/factory-init`) persists **stable** project facts (purpose, components, canonical docs, commands) into the `AGENTS.md` managed block, and long-lived **lessons learned** live in `kb/`. Neither layer carries the **short-lived, stateful** sense of *"where we were / what changed this session / what's next"*. Because pi loads `AGENTS.md` natively each session, a fresh session knows *what the repo is* but has no memory of *what a prior session just did*, unless a human re-states it.

We want: after a session does something a later session should be aware of, that is **persisted**, and on the next session it is **injected** into the system prompt — then **retired** once it is old/superseded enough that a new session should no longer be told about it.

## 2. Non-goals / boundaries

- **Not** a replacement for `kb/`. `kb/*.md` entries are long-lived, cross-session lessons learned (root causes, recurring gotchas), written by the session-review role, surfaced by retrieval, no TTL. This design is the short-lived *continuity* layer and must not duplicate or absorb `kb/`.
- **Not** raw-transcript persistence. Logging transcripts is bloat and a stale-continuity hazard (the crux of "a later session is told the wrong thing"). What happened is logged **explicitly** (a `/remember` command), never dumped automatically.
- **Not** a change to the stable `AGENTS.md` managed block. Volatile state stays out of it (existing ruling: *"Do not put active task state into the managed block — it is volatile and would churn the prompt cache"*).

## 3. Three-layer knowledge model (how this slots in)

| layer | home | volatility | mechanism |
|---|---|---|---|
| Project bootstrap | `AGENTS.md` managed block | low | native pi load, every session |
| **Session continuity** *(this design)* | `.pi/factory/session-memory.json` | **high; TTL** | injected by `before_agent_start`; written/pruned by `/remember` + `session_shutdown` |
| Durable lessons | `kb/*.md`, evidence store, specs/plans | low | retrieved/queried on demand |

## 4. The two hooks (pi API)

- **Write + prune — `session_shutdown`** fires when a session ends with `reason` (`quit | reload | new | resume | fork`). This is the *after-session* point: tend the store (prune expired, supersede handled at write, enforce cap).
- **Read + inject — `before_agent_start`** fires once per user prompt, hands the extension the fully assembled `systemPrompt` and lets it return a modified one. This is the *next-session* point: read the pruned store and inject a bounded rollup.

Both hooks are already in the real `@earendil-works/pi-coding-agent` extension API. The factory extension currently registers **no** hooks; this design adds the first two, extending the minimal `PiApi` structural subset (`pi-types.ts`) with a `session_shutdown` overload (the `before_agent_start` overload already exists, currently unused).

## 5. The store: `.pi/factory/session-memory.json`

Schema-versioned, machine-readable, alongside `project-profile.json`:

```json
{ "schema": 1, "entries": [
  { "id": "sm-0001", "kind": "log", "topic": "task:T-042",
    "created": "2026-08-09T10:00:00.000Z", "expires": "2026-08-10T10:00:00.000Z",
    "actor": "session:abc", "text": "unit green after audit-log fix; next: validation gate",
    "supersedes": null }
] }
```

- `topic` — grouping key for supersede (e.g. `task:T-042`, `decision:<slot>`).
- `expires` — never null for `kind:"log"` (always short-lived).
- `supersedes` — id of the live entry this one retired, kept for audit.
- `actor` — who logged it (session id, `manual`).

### The three retention controls ("stop telling new sessions about deprecated/unrelevant stuff")

1. **TTL** — each entry carries `expires`; entries with `expires < now` are dropped and never injected. This is the age-based pruning the requirement asks for.
2. **Supersede by topic** — writing a note with the same `topic` retires the older **live** entry first. Without this, age alone leaves two contradicting "latest" claims (`T-042 on dev` + `T-042 validation failed`) both injected. With it, a new session sees only the newest state for a subject. This is the correctness mechanism a pure TTL lacks.
3. **Hard cap** — `maxEntries` and a `maxTokens` injection budget; oldest dropped first past the cap; per-note token cap so one long note can't blow the rollup.

Composed **at write time** (and re-run on `session_shutdown`), deterministically, in the pure module. No model involved in pruning — it is a mechanical filter.

## 6. Injection surface

On `before_agent_start`, if the pruned store is non-empty, append a bounded, as-of-dated block of fresh notes (oldest first) to the system prompt:

```markdown
# Session continuity (from session-memory.json — volatile, as-of-dated)
Fresh notes a prior session deliberately left for this one. Verify before acting on them; detailed state is on disk / on-demand.
- [task:T-042] (session:def, until 2026-08-10 11:30) validation FAILED (flaky sim); retrying with -x
- [decision:audit-log] (session:abc, until 2026-08-10 11:00) keep session_shutdown prune silent
```

Design rules for the injected content:
- **Every line is as-of/expiry-dated and marked volatile**, so the reader treats it as a pointer to verify, not ground truth (hallucinated-continuity guard).
- **Bounded** by `maxTokens` (default 400) and per-note cap (160), oldest first.
- **Empty store ⇒ no injection**: an unbootstrapped repo or a repo with no notes is untouched.
- Heavy detail (the whole ledger, git log, trace matrix) stays **on-demand** (`/system`, `/trace-fix`, `/factory`, trace tools) — never inlined.

## 7. Command surface

- `/remember [--ttl <hours>] <topic>: <text>` — explicit write path. Defaults TTL to policy (24 h).
- `session_shutdown` — implicit; persists and prunes the store (never takes the host down on a prune failure).
- `before_agent_start` — implicit; injects the rollup.

## 8. Policy / configurability (not yet wired — follow-up)

Decisions belong in `/factory-init`, once, persisted as a `session_context` block in `project-profile.json`:

```json
"session_context": {
  "feeds": ["ledger", "memory", "head", "trace_health"],
  "memory": { "ttl_hours": 24, "max_entries": 50, "max_tokens": 400, "auto_summary": true }
}
```

The hook **must stay deterministic, fast and non-interactive** (it runs every turn); interactivity lives in `/factory-init`, which writes the policy this hook reads. Omitted feeds mean "not injected — query on demand". This is out of scope for the prototype but is the intended production shape.

## 9. Open design decision

Whether `session_shutdown` **deletes** pruned entries outright, or keeps a capped append-only audit file while pruning only the *injectable* view. Recommendation: prune the injectable view; treat a compact audit trail as optional and out of the inject path. Prototype deletes (simplest); revisit if replayability is wanted.

## 10. Risks

- **Double-log on mid-session replacement** (`reload`/`new`/`fork` also fire `session_shutdown`). Mitigation: notes are written only explicitly (`/remember`), and the shutdown hook only *prunes*; a no-op prune produces no duplicate. An automatic per-session summary (future) must dedupe by `actor`+topic.
- **Stale-injection harm** — mitigated by as-of-dating + "verify first" framing + TTL/supersede/cap.
- **API drift** — new hooks guarded by the existing `type-compat-check.ts` pin (minimal `PiApi` ⊇ assigned to real `ExtensionFactory`).

## 11. Prototype evidence

Landed and green: `session-memory.ts` (pure), `session-memory-command.ts` (wiring), `test/session-memory.test.ts` (16 tests), `pi-types.ts` extended with `session_shutdown`, wired from `index.ts`. Full extension suite: **61 files / 720 tests pass**, `tsc --noEmit` clean. Demonstrated: supersede retires the older `task:T-042` note; expired notes never reach a new session's rollup; rollup is bounded and as-of-dated.
