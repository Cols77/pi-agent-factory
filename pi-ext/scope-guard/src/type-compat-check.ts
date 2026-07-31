// Type-only compile-time guard: never imported, never executed, only
// typechecked by `tsc --noEmit`.
//
// pi-types.ts hand-declares a minimal structural subset of Pi's real
// ExtensionAPI so this extension can be typechecked/tested without a heavy
// dependency. That hand-rolled surface can silently drift from the real
// `@earendil-works/pi-coding-agent` package as Pi evolves. This file pins
// two load-bearing assumptions against the real package's published types:
//
//   1. scope-guard's default export (`(pi: PiApi) => void`) must remain
//      structurally usable as a real Pi `ExtensionFactory` — this is
//      literally how Pi loads the extension at runtime
//      (`pi --extension pi-ext/scope-guard/src/index.ts`).
//   2. The `{ block: true, reason }` result objects `decide()` returns must
//      satisfy the real `ToolCallEventResult` shape Pi expects back from a
//      "tool_call" handler.
//
// If either assignment below stops compiling, pi-types.ts has drifted from
// the real ExtensionAPI and must be reconciled before merging.

import type { ExtensionFactory, ToolCallEventResult } from "@earendil-works/pi-coding-agent";
import scopeGuard from "./index.js";
import type { ToolCallResult } from "./pi-types.js";

// 1) scope-guard's entry point is assignable to the real extension-factory type.
const _factoryCompat: ExtensionFactory = scopeGuard;
void _factoryCompat;

// 2) Every concrete (non-undefined) value our ToolCallResult can hold
// satisfies the real ToolCallEventResult shape.
const _blockResultCompat: ToolCallEventResult = { block: true, reason: "scope-guard: example" } satisfies Exclude<
  ToolCallResult,
  undefined
>;
void _blockResultCompat;
