// /factory-init command wiring.
//
// This layer owns the two commands /factory-init and /factory-doctor, the
// interactive-diff preview, and the reload-after-change contract. All of the
// deterministic discovery/synthesis/write logic lives in factory-init.ts (pure,
// Pi-free, unit-testable); everything here is glue that touches Pi APIs.

import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import {
  BLOCK_END,
  BLOCK_START,
  DEFAULT_CONFIG_DIR,
  readAgentsMd,
  resolveProjectRoot,
  runFactoryCheck,
  runFactoryInit,
  type CheckResult,
  type InitResult,
} from "./factory-init.js";
import { subagentTool } from "./subagent-tool.js";
import {
  ALL_FEEDS,
  hasContext,
  readContext,
  seedContext,
  writeContext,
  type FeedName,
} from "./session-policy.js";

function parseArgs(args: string): { refresh: boolean; check: boolean } {
  const refresh = /(^|\s)--refresh(\s|$)/.test(args);
  const check = /(^|\s)--check(\s|$)/.test(args);
  return { refresh, check };
}

function renderBlockPreview(root: string): string {
  const current = readAgentsMd(root);
  if (!current.present) {
    return "(AGENTS.md does not exist yet; a heading + managed block will be created)";
  }
  if (current.block === null) {
    return "(no managed block present; it will be inserted, surroundings preserved byte-for-byte)";
  }
  return (
    "CURRENT managed block:\n" +
    BLOCK_START +
    "\n" +
    current.block +
    "\n" +
    BLOCK_END +
    "\n---\nAny change applies only inside the managed markers; text outside them is preserved byte-for-byte."
  );
}

// A tiny report adapter keeping command output consistent.

// Pick which context feeds ("streams") deterministically inject into every
// future session. Mirrors /factory-context interactivity and writes the very
// first session-context.json during /factory-init bootstrap.
async function seedContextFeeds(ctx: ExtCommandCtx, root: string): Promise<void> {
  const cctx = readContext(root); // absent file -> deterministic defaults
  let feeds = cctx.enabledFeeds;
  if (ctx.hasUI) {
    // Interactive multi-select: flip each stream, then "done".
    for (;;) {
      const selection = await ctx.ui.select(
        "Bootstrap: which context streams inject into future sessions? (choose one to flip, then done)",
        [
          ...ALL_FEEDS.map((f) => `${f} (${feeds.includes(f) ? "ON" : "off"})`),
          ALL_FEEDS.join(","),
          "done",
        ],
      );
      if (selection === undefined || selection === "done") break;
      const name = selection.split(" ")[0] as FeedName;
      feeds = feeds.includes(name) ? feeds.filter((f) => f !== name) : [...feeds, name];
    }
  }
  writeContext(root, seedContext(feeds));
  ctx.ui.notify(`factory-init: seeded session-context feeds: ${feeds.join(", ") || "(none)"}`, "info");
  ctx.ui.notify("  later change any stream with /factory-context", "info");
}

function reportLines(result: InitResult): string[] {
  const lines = result.report.split("\n");
  return lines.length <= 24 ? lines : [...lines.slice(0, 22), `... (${lines.length - 22} more lines)`];
}

export function registerFactoryInit(pi: PiApi): void {
  pi.registerCommand("factory-init", {
    description:
      "Initialise (or validate) the deterministic project bootstrap: /factory-init [--refresh] [--check]",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const { refresh, check } = parseArgs(args);
      const { root } = resolveProjectRoot(ctx.cwd);

      // Steps 1-2: resolve root. Project trust is Pi's own gate: project-local
      // extensions (including this one when vendored) load only after the
      // project is trusted, so honoring project-local config here is already
      // trust-gated by the host. The installed Pi API (0.74.x) does not export
      // isProjectTrusted(), so no second manual gate is layered on top.

      const mode = check ? "check" : refresh ? "refresh" : "init";
      const result = runFactoryInit({ root, mode, configDir: DEFAULT_CONFIG_DIR });

      // Seed the session-context policy (which streams inject into every future
      // session) on the plain-init path when none exists yet. Kept entirely in
      // session-context.json so /factory-init --refresh (which regenerates
      // project-profile.json) never wipes it. Interactive pick via ctrl-t;
      // non-interactive falls back to the deterministic default feed set.
      if (mode === "init" && !hasContext(root)) {
        await seedContextFeeds(ctx, root);
      }

      if (mode === "check") {
        for (const line of reportLines(result)) ctx.ui.notify(line, "info");
        ctx.ui.notify(
          result.fresh ? "factory-init: bootstrap is healthy" : "factory-init: STALE",
          result.fresh ? "info" : "warning",
        );
        return;
      }

      // Step 6: interactive preview before replacing an existing managed block,
      // with a useful noninteractive fallback (no terminal dialogs required).
      if (!result.fresh && ctx.hasUI) {
        const ok = await ctx.ui.confirm("Update project bootstrap", renderBlockPreview(root));
        if (!ok) {
          ctx.ui.notify("factory-init: cancelled, nothing written", "info");
          return;
        }
      } else if (!result.fresh) {
        ctx.ui.notify(renderBlockPreview(root), "warning");
      }

      if (!result.fresh) {
        for (const line of reportLines(result)) ctx.ui.notify(line, "info");
        // Step 9: reload only after an actual change, then return per pi's contract.
        await ctx.reload();
        return;
      }

      for (const line of reportLines(result)) ctx.ui.notify(line, "info");
    },
  });

  pi.registerCommand("factory-doctor", {
    description:
      "Diagnose the project bootstrap: root, profile, AGENTS.md block, essential tools, subagent metadata",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const { root } = resolveProjectRoot(ctx.cwd);
      const check = runFactoryCheck(root);
      for (const line of renderDoctor(check)) ctx.ui.notify(line, "info");
    },
  });

  // Register the subagent tool so its prompt metadata reaches the parent model.
  registerFactoryInitTools(pi);
}

export function registerFactoryInitTools(pi: Pick<PiApi, "registerTool">): void {
  pi.registerTool(subagentTool);
}

function renderDoctor(check: CheckResult): string[] {
  const lines: string[] = [`factory-doctor on ${check.root}`];
  lines.push(`  root resolution:      ${check.rootResolution}`);
  lines.push(`  profile present:      ${check.profilePresent ? "yes" : "no -- run /factory-init"}`);
  lines.push(
    `  profile fresh:        ${check.profileFresh ? "yes" : "STALE -- run /factory-init --refresh"}`,
  );
  lines.push(
    `  AGENTS.md block:      ${check.blockPresent ? "valid" : "missing/invalid -- run /factory-init"}`,
  );
  lines.push(`  subagent metadata:    ${subagentMetadataPresent() ? "present" : "MISSING"}`);
  lines.push(
    `  context file:         AGENTS.md ${check.blockPresent ? "present on disk" : "absent on disk"}; Pi loads it natively so no duplicate injection is performed`,
  );
  lines.push(check.ok ? "  summary: OK" : "  summary: STALE or missing artifacts");
  return lines;
}

function subagentMetadataPresent(): boolean {
  return (
    typeof subagentTool.promptSnippet === "string" &&
    Array.isArray(subagentTool.promptGuidelines) &&
    subagentTool.promptGuidelines.length > 0
  );
}
