import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { isAbsolute, resolve, sep } from "node:path";
import { renderMarkdown } from "./md-render.js";
import { layoutGraph, neighbourhood } from "./graph-layout.js";
import { loadTraceGraph } from "./trace-cli.js";
import { renderDocsHtml } from "./docs-html.js";

export interface RunningDocsServer {
  url: string;
  port: number;
  close(): void;
}

let running: { server: Server; handle: RunningDocsServer } | null = null;

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

function handle(cwd: string, req: IncomingMessage, res: ServerResponse): void {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(renderDocsHtml());
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
  if (running !== null) return Promise.resolve(running.handle);
  return new Promise((resolveStart) => {
    const server = createServer((req, res) => handle(cwd, req, res));
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      const handleObj: RunningDocsServer = {
        url: `http://127.0.0.1:${port}`,
        port,
        close() {
          stopDocsServer();
        },
      };
      running = { server, handle: handleObj };
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
