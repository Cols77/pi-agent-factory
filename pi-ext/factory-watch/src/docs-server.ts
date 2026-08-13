import { createHash } from "node:crypto";
import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import { readdirSync, readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { isAbsolute, join, resolve, sep } from "node:path";
import {
  loadCurrentRun,
  loadTaskEvidence,
  requestRunAction,
  runPreflight,
  runReconcile,
} from "./evidence-client.js";
import { renderMarkdown } from "./md-render.js";
import { layoutGraph, neighbourhood } from "./graph-layout.js";
import { loadTraceGraph } from "./trace-cli.js";
import { renderDocsHtml } from "./docs-html.js";
import {
  loadSystemBriefing,
  loadSystemGuide,
  loadSystemHealth,
  loadSystemMatrix,
  loadSystemReverse,
  loadSystemScopes,
  loadSystemStory,
  loadSystemTimeline,
} from "./system-cli.js";
import { renderSystemPageHtml } from "./system-page.js";

export interface RunningDocsServer {
  url: string;
  port: number;
  close(): void;
}

let running: { server: Server; handle: RunningDocsServer; cwd: string } | null = null;

// Loopback binding is not on its own an authorization boundary -- any process on
// the machine can reach the port -- so every served path is confined to the repo.
export function resolveDocPath(root: string, relative: string): string | null {
  if (isAbsolute(relative)) return null;
  const rootResolved = resolve(root);
  const target = resolve(rootResolved, relative);
  if (target !== rootResolved && !target.startsWith(rootResolved + sep)) return null;
  return target;
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

export interface ArchivedReviewAnnotation {
  file: string;
  body: string;
  line: number | null;
  side: string | null;
  severity: string | null;
}

export interface ArchivedReview {
  reviewed_at: string;
  task_id: string;
  start_commit: string;
  decision: string;
  annotations: ArchivedReviewAnnotation[];
  reviewed_files: string[];
  diff: string;
  diff_error: string | null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function parseArchivedReview(value: unknown, taskId: string): ArchivedReview | null {
  if (typeof value !== "object" || value === null) return null;
  const raw = value as Record<string, unknown>;
  if (raw.task_id !== taskId || typeof raw.decision !== "string") return null;
  const annotations = Array.isArray(raw.annotations)
    ? raw.annotations.flatMap((item): ArchivedReviewAnnotation[] => {
        if (typeof item !== "object" || item === null) return [];
        const annotation = item as Record<string, unknown>;
        if (typeof annotation.file !== "string" || typeof annotation.body !== "string") return [];
        return [{
          file: annotation.file,
          body: annotation.body,
          line: typeof annotation.line === "number" ? annotation.line : null,
          side: typeof annotation.side === "string" ? annotation.side : null,
          severity: typeof annotation.severity === "string" ? annotation.severity : null,
        }];
      })
    : [];
  return {
    reviewed_at: asString(raw.reviewed_at),
    task_id: taskId,
    start_commit: asString(raw.start_commit),
    decision: raw.decision,
    annotations,
    reviewed_files: Array.isArray(raw.reviewed_files)
      ? raw.reviewed_files.filter((file): file is string => typeof file === "string")
      : [],
    diff: asString(raw.diff),
    diff_error: typeof raw.diff_error === "string" ? raw.diff_error : null,
  };
}

// Archives are emitted by FileHumanReviewGate under their session transcript
// directory.  They are append-only review evidence, not inferred from current
// git state, so later task work cannot rewrite the review a human actually saw.
function containsArtifact(value: unknown, digest: string): boolean {
  if (Array.isArray(value)) return value.some((item) => containsArtifact(item, digest));
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  if (record["sha256"] === digest) return true;
  return Object.values(record).some((item) => containsArtifact(item, digest));
}

function artifactIsReferenced(cwd: string, digest: string): boolean {
  let files: string[];
  const runs = resolve(cwd, "evidence", "runs");
  try {
    files = readdirSync(runs);
  } catch {
    return false;
  }
  return files.some((file) => {
    if (!file.endsWith(".json")) return false;
    try {
      return containsArtifact(
        JSON.parse(readFileSync(join(runs, file), "utf-8")) as unknown,
        digest,
      );
    } catch {
      return false;
    }
  });
}

export function loadTaskReviews(cwd: string, taskId: string): ArchivedReview[] {
  const transcripts = resolve(cwd, "sessions", ".factory-transcripts");
  let sessions: string[];
  try {
    sessions = readdirSync(transcripts);
  } catch {
    return [];
  }
  const reviews: ArchivedReview[] = [];
  for (const session of sessions) {
    let files: string[];
    try {
      files = readdirSync(join(transcripts, session, "reviews"));
    } catch {
      continue;
    }
    for (const file of files) {
      if (!file.endsWith(".json")) continue;
      try {
        const parsed = parseArchivedReview(
          JSON.parse(readFileSync(join(transcripts, session, "reviews", file), "utf-8")) as unknown,
          taskId,
        );
        if (parsed !== null) reviews.push(parsed);
      } catch {
        // A partial/corrupt historical artifact is not a reason to hide other
        // review rounds or fail the documentation workspace.
      }
    }
  }
  return reviews.sort((a, b) => b.reviewed_at.localeCompare(a.reviewed_at));
}

function readActionBody(
  req: IncomingMessage,
  res: ServerResponse,
  callback: (value: Record<string, unknown>) => void,
): void {
  const chunks: Buffer[] = [];
  let size = 0;
  req.on("data", (chunk: Buffer) => {
    size += chunk.length;
    if (size <= 16 * 1024) chunks.push(chunk);
  });
  req.on("end", () => {
    if (size > 16 * 1024) {
      json(res, 413, { error: "request body too large" });
      return;
    }
    const text = Buffer.concat(chunks).toString("utf-8").trim();
    try {
      const value = text === "" ? {} : JSON.parse(text) as unknown;
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error("body must be a JSON object");
      }
      callback(value as Record<string, unknown>);
    } catch (err) {
      json(res, 400, { error: `invalid action body: ${String(err)}` });
    }
  });
}

function handle(cwd: string, req: IncomingMessage, res: ServerResponse): void {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(renderDocsHtml());
    return;
  }

  // /system is opt-in (design section 6.4, section 10 non-goals): it is a
  // second, explicitly-navigated page, never the default served on "/". Both
  // "/system" and "/system?scope=<ref>" serve the identical static shell --
  // the scope query param is read and acted on client-side only, exactly
  // like the "/" page's task/run focus params.
  if (req.method === "GET" && url.pathname === "/system") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(renderSystemPageHtml());
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/graph") {
    const result = loadTraceGraph(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.graph);
    return;
  }

  // Layout is computed here, by the tested pure function, so the page never
  // grows a second untested copy of the same arithmetic.
  if (req.method === "GET" && url.pathname === "/api/layout") {
    const result = loadTraceGraph(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    const root = url.searchParams.get("root");
    const hops = Number(url.searchParams.get("hops") ?? "1");
    const scoped =
      root === null
        ? { nodes: result.graph.nodes, edges: result.graph.edges }
        : neighbourhood(
            result.graph.nodes,
            result.graph.edges,
            root,
            Number.isFinite(hops) ? hops : 1,
          );
    json(res, 200, layoutGraph(scoped.nodes, scoped.edges));
    return;
  }

  // /api/system/* projects factory.system's JSON straight through (design
  // section 6.1, 6.3): no freshness/ordering/provenance recomputation here,
  // and only these eight exact paths exist -- anything else falls through
  // to the 404 below.
  if (req.method === "GET" && url.pathname === "/api/system/scope") {
    const result = loadSystemScopes(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  // SP-B Task 6: the composed landing projection the browser renders on load.
  if (req.method === "GET" && url.pathname === "/api/system/health") {
    const result = loadSystemHealth(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/system/brief") {
    const result = loadSystemBriefing(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/system/matrix") {
    const result = loadSystemMatrix(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/system/timeline") {
    const result = loadSystemTimeline(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  // Read-only, computed per request -- the browser has no export affordance
  // (design SS4.5: export is a CLI-only, explicit, user-initiated write;
  // `loadSystemGuide` never passes `--export`).
  if (req.method === "GET" && url.pathname === "/api/system/guide") {
    const result = loadSystemGuide(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  // Increment B "V-cycle": `story` is the forward half (task -> runs ->
  // requirements), `reverse` the backward half (file -> run -> task ->
  // requirements). Same exact-pathname discipline as the five routes above.
  if (req.method === "GET" && url.pathname === "/api/system/story") {
    const result = loadSystemStory(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/system/reverse") {
    const result = loadSystemReverse(cwd, url.searchParams.get("scope") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/evidence/task") {
    const result = loadTaskEvidence(cwd, url.searchParams.get("task") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/preflight") {
    const result = runPreflight(cwd, url.searchParams.get("task") ?? "");
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/reconcile") {
    const task = url.searchParams.get("task") ?? undefined;
    const result = runReconcile(cwd, task);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  const actionMatch = /^\/api\/run-state\/([A-Za-z0-9._-]+)\/(resume|abandon)$/.exec(url.pathname);
  if (req.method === "POST" && actionMatch !== null) {
    const runId = actionMatch[1]!;
    const action = actionMatch[2] as "resume" | "abandon";
    readActionBody(req, res, (body) => {
      const keys = Object.keys(body);
      if (action === "resume" && keys.length !== 0) {
        json(res, 400, { error: "resume body must be empty" });
        return;
      }
      const reason = body.reason;
      if (
        action === "abandon"
        && (keys.length !== 1 || typeof reason !== "string" || reason.trim() === "")
      ) {
        json(res, 400, { error: "abandonment requires exactly one non-blank reason" });
        return;
      }
      const result = requestRunAction(
        cwd,
        runId,
        action,
        typeof reason === "string" ? reason.trim() : undefined,
      );
      if (!result.ok) {
        const status = result.status === 3 ? 409 : result.status === 4 ? 422 : 503;
        json(res, status, { error: result.error });
        return;
      }
      json(res, 200, result.value);
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/run-state") {
    const result = loadCurrentRun(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.value);
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/api/artifact/")) {
    const digest = url.pathname.slice("/api/artifact/".length);
    if (!/^[a-f0-9]{64}$/.test(digest) || !artifactIsReferenced(cwd, digest)) {
      json(res, 404, { error: "artifact not found" });
      return;
    }
    try {
      const data = readFileSync(
        resolve(cwd, ".factory", "artifacts", "objects", digest.slice(0, 2), digest),
      );
      if (createHash("sha256").update(data).digest("hex") !== digest) {
        json(res, 409, { error: "artifact hash mismatch" });
        return;
      }
      res.writeHead(200, {
        "content-type": "application/octet-stream",
        "x-content-type-options": "nosniff",
      });
      res.end(data);
    } catch {
      json(res, 404, { error: "artifact not found" });
    }
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/reviews") {
    json(res, 200, { reviews: loadTaskReviews(cwd, url.searchParams.get("task") ?? "") });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/doc") {
    const relative = url.searchParams.get("path") ?? "";
    const target = resolveDocPath(cwd, relative);
    if (target === null) {
      json(res, 403, { error: "path outside repository" });
      return;
    }
    let raw: string;
    try {
      raw = readFileSync(target, "utf-8");
    } catch {
      json(res, 404, { error: `not found: ${relative}` });
      return;
    }
    json(res, 200, { path: relative, ...renderMarkdown(raw) });
    return;
  }

  res.writeHead(404);
  res.end();
}

export function ensureDocsServer(cwd: string): Promise<RunningDocsServer> {
  const normalizedCwd = resolve(cwd);
  if (running !== null) {
    if (running.cwd !== normalizedCwd) {
      return Promise.reject(
        new Error(`docs server already serves ${running.cwd}; refusing different root ${normalizedCwd}`),
      );
    }
    return Promise.resolve(running.handle);
  }
  return new Promise((resolveStart) => {
    const server = createServer((req, res) => handle(normalizedCwd, req, res));
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      const handleObj: RunningDocsServer = {
        url: `http://127.0.0.1:${port}`,
        port,
        close() {
          stopDocsServer();
        },
      };
      running = { server, handle: handleObj, cwd: normalizedCwd };
      resolveStart(handleObj);
    });
  });
}

export function stopDocsServer(): boolean {
  if (running === null) return false;
  running.server.close();
  running = null;
  return true;
}
