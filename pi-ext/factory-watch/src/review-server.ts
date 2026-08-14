import {
  computeFileDiffText,
  computeImplementingFileDiffText,
} from "./review-diff.js";
import type { FileStat } from "./review-diff.js";
import { mapDiffRows } from "./review-model.js";
import type { DiffRowMeta } from "./review-model.js";
import type { ReviewGuide } from "./review-guide.js";
import { grillReviewWarning } from "./review-guide.js";
import { walkIntentChain } from "./review-intent.js";
import type { ReviewChainNode } from "./review-intent.js";
import { buildSystemContext } from "./system-context.js";
import { unknownSource } from "./system-context.js";
import { loadSystemStory, loadSystemReverse } from "./system-cli.js";
import { readLayoutPref, writeLayoutPref } from "./review-surface.js";
import { DEFAULT_LAYOUT, normalizeLayout } from "./review-layout.js";
import type { LayoutState } from "./review-layout.js";
import { loadTraceGraph } from "./trace-cli.js";
import { loadTaskEvidence, runPreflight } from "./evidence-client.js";
import type { SystemContextDeps } from "./system-context.js";

export interface ReviewTaskContext {
  id: string;
  path: string;
  title: string;
  status: string;
  dod: string[];
  html: string;
}

export interface ReviewIntent {
  chain: ReviewChainNode[];
  stopsAt: string | null;
  planSection: { planPath: string; heading: string; html: string } | null;
  // status and dod are duplicated with ReviewTaskContext on purpose: these come
  // from query_story through the ledger, those come from reading the task file
  // directly. The pane prefers these and falls back to those, which is what
  // keeps the panel useful when the navigator is unavailable. A divergence
  // between them is worth seeing, so they are not merged.
  dod: string[];
  status: string;
  requirements: string[];
}

export interface ReviewPageDeps {
  story: typeof loadSystemStory;
  context: typeof buildSystemContext;
  layout: typeof readLayoutPref;
}

export interface ReviewPageData {
  taskId: string;
  task: ReviewTaskContext | null;
  banner: string;
  implementing: boolean;
  guide: ReviewGuide | null;
  files: FileStat[];
  diffs: Record<string, { lines: string[]; meta: DiffRowMeta[] }>;
  intent: ReviewIntent | null;
  layout: LayoutState;
}

const defaultSystemContextDeps: SystemContextDeps = {
  graph: loadTraceGraph,
  taskEvidence: loadTaskEvidence,
  preflight: runPreflight,
};

function buildIntent(cwd: string, taskId: string, deps: ReviewPageDeps): ReviewIntent | null {
  const story = deps.story(cwd, `task:${taskId}`);
  if (!story.ok) return null; // navigator unavailable -- the task file panel still renders

  const graph = deps.context(cwd, taskId, defaultSystemContextDeps).graph;
  const walked = graph === null ? { chain: [], stopsAt: null } : walkIntentChain(graph, taskId);
  const section = story.value.plan_section;
  return {
    chain: walked.chain,
    stopsAt: walked.stopsAt,
    planSection: section === null ? null : {
      planPath: section.plan_path,
      heading: section.heading,
      // renderMarkdown escapes its source before emitting markup -- the same
      // trusted renderer the task panel and /review-plans already use.
      html: renderMarkdown(section.body).html,
    },
    dod: story.value.task.dod,
    status: story.value.task.status,
    requirements: story.value.requirements,
  };
}

// The review handoff gives us an id, while task filenames deliberately carry a
// human-readable suffix.  Resolve by the parsed, authoritative frontmatter id
// instead of recreating a filename convention in a second surface.
function readTaskContext(cwd: string, taskId: string): ReviewTaskContext | null {
  let names: string[];
  try {
    names = readdirSync(join(cwd, "tasks"));
  } catch {
    return null;
  }
  for (const name of names) {
    if (!name.endsWith(".md")) continue;
    try {
      const raw = readFileSync(join(cwd, "tasks", name), "utf-8");
      const task = parseTaskFrontmatter(raw);
      if (task?.id !== taskId) continue;
      return {
        id: task.id,
        path: `tasks/${name}`,
        title: task.title,
        status: task.status,
        dod: task.dod,
        // renderMarkdown escapes source before producing markup.  Passing this
        // rendered result, rather than raw task text, keeps the browser review
        // readable and matches the existing /review-plans reader.
        html: renderMarkdown(raw).html,
      };
    } catch {
      // A malformed or concurrently removed sibling must not prevent the human
      // from reviewing the diff.  Continue looking for the requested task.
    }
  }
  return null;
}

export function buildReviewPageData(
  cwd: string,
  startCommit: string,
  files: FileStat[],
  opts: {
    implementing?: boolean;
    banner?: string;
    guide?: ReviewGuide | null;
    taskId: string;
    deps?: Partial<ReviewPageDeps>;
  },
): ReviewPageData {
  const implementing = opts.implementing ?? false;
  const diffs: ReviewPageData["diffs"] = {};
  for (const f of files) {
    const text = implementing
      ? computeImplementingFileDiffText(cwd, f.path)
      : computeFileDiffText(cwd, startCommit, f.path);
    const lines = text.split("\n");
    diffs[f.path] = { lines, meta: mapDiffRows(lines) };
  }
  const resolved: ReviewPageDeps = {
    story: opts.deps?.story ?? loadSystemStory,
    context: opts.deps?.context ?? buildSystemContext,
    layout: opts.deps?.layout ?? readLayoutPref,
  };
  return {
    taskId: opts.taskId,
    task: readTaskContext(cwd, opts.taskId),
    banner: [opts.banner ?? "", grillReviewWarning(opts.guide ?? null)]
      .filter((s) => s.length > 0)
      .join("\n\n"),
    implementing,
    guide: opts.guide ?? null,
    files,
    diffs,
    intent: buildIntent(cwd, opts.taskId, resolved),
    layout: resolved.layout(cwd),
  };
}

import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { readdirSync, readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { join } from "node:path";
import { renderMarkdown } from "./md-render.js";
import { parseTaskFrontmatter } from "./task-header.js";
import type { ReviewDecisionPayload } from "./review-model.js";
import { renderReviewHtml } from "./review-html.js"; // Task 3

export interface RunningReviewServer {
  url: string;
  port: number;
  decision: Promise<ReviewDecisionPayload | null>;
  close(): void;
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => resolve(raw));
    req.on("error", () => resolve(raw));
  });
}

export function startReviewServer(
  data: ReviewPageData,
  opts: { cwd: string; reverse?: typeof loadSystemReverse; writeLayout?: typeof writeLayoutPref },
): Promise<RunningReviewServer> {
  return new Promise((resolveStart) => {
    let resolveDecision!: (d: ReviewDecisionPayload | null) => void;
    const decision = new Promise<ReviewDecisionPayload | null>((r) => (resolveDecision = r));
    let settled = false;

    const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
      const url = req.url ?? "/";
      if (req.method === "GET" && url === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(renderReviewHtml());
        return;
      }
      if (req.method === "GET" && url === "/api/review") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(data));
        return;
      }
      if (req.method === "POST" && url === "/api/decision") {
        let payload: ReviewDecisionPayload;
        try {
          payload = JSON.parse(await readBody(req)) as ReviewDecisionPayload;
        } catch {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: "invalid json" }));
          return;
        }
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        if (!settled) { settled = true; resolveDecision(payload); }
        server.close();
        return;
      }
      if (req.method === "GET" && url.startsWith("/api/why")) {
        const file = new URL(url, "http://127.0.0.1").searchParams.get("file") ?? "";
        const reverse = (opts.reverse ?? loadSystemReverse)(opts.cwd, `file:${file}`);
        res.writeHead(200, { "content-type": "application/json" });
        // A file with no recorded evidence is the normal case for a new file.
        // It is reported as unknown, never as a failed pane.
        res.end(JSON.stringify(reverse.ok ? reverse.value : unknownSource("reverse", reverse.error)));
        return;
      }
      if (req.method === "POST" && url === "/api/layout") {
        let state: LayoutState = DEFAULT_LAYOUT;
        try {
          state = normalizeLayout(JSON.parse(await readBody(req)));
        } catch {
          state = DEFAULT_LAYOUT;
        }
        (opts.writeLayout ?? writeLayoutPref)(opts.cwd, state);
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        return;
      }
      res.writeHead(404);
      res.end();
    });

    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolveStart({
        url: `http://127.0.0.1:${port}`,
        port,
        decision,
        close() {
          if (!settled) { settled = true; resolveDecision(null); }
          server.close();
        },
      });
    });
  });
}
