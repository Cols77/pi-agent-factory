import { parseAllow } from "./allow.js";
import { parseBashPolicy, decide } from "./policy.js";
import type { PiApi } from "./pi-types.js";

// Pi loads this via: pi --extension pi-ext/scope-guard/src/index.ts
// The orchestrator sets PI_SCOPE_ALLOW / PI_SCOPE_BASH per agent node.
export default function scopeGuard(pi: PiApi): void {
  pi.on("tool_call", (event, ctx) => {
    const allowGlobs = parseAllow(process.env.PI_SCOPE_ALLOW);
    const bash = parseBashPolicy(process.env.PI_SCOPE_BASH);
    return decide(event, ctx, allowGlobs, bash);
  });
}
