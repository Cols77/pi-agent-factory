// Type-only compile-time guard: never imported, never executed, only
// typechecked by `tsc --noEmit`.
//
// pi-types.ts hand-declares a minimal structural subset of Pi's real
// ExtensionAPI so this extension can be typechecked/tested without
// exercising the full real interface in every fake. That hand-rolled
// surface can silently drift from the real @earendil-works/pi-coding-agent
// package as Pi evolves. This file pins the one load-bearing assumption
// against the real package's published types:
//
//   factory-watch's default export (`(pi: PiApi) => void`) must remain
//   structurally usable as a real Pi `ExtensionFactory` -- this is literally
//   how Pi loads the extension at runtime
//   (`pi --extension pi-ext/factory-watch/src/index.ts`). Because function
//   parameter assignability is checked contravariantly, this single
//   assignment recursively validates every field this extension reads off
//   `pi` and off each command handler's `ctx` (registerCommand,
//   ctx.ui.notify/setStatus/setWidget, ctx.model, ctx.cwd) against the real
//   types.
//
// If this assignment stops compiling, pi-types.ts has drifted from the real
// ExtensionAPI and must be reconciled before merging.

import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import factoryWatch from "./index.js";

const _factoryCompat: ExtensionFactory = factoryWatch;
void _factoryCompat;
