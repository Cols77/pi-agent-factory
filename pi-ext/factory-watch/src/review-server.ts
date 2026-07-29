import {
  computeFileDiffText,
  computeImplementingFileDiffText,
} from "./review-diff.js";
import type { FileStat } from "./review-diff.js";
import { mapDiffRows } from "./review-model.js";
import type { DiffRowMeta } from "./review-model.js";
import type { ReviewGuide } from "./review-guide.js";

export interface ReviewPageData {
  taskId: string;
  banner: string;
  implementing: boolean;
  guide: ReviewGuide | null;
  files: FileStat[];
  diffs: Record<string, { lines: string[]; meta: DiffRowMeta[] }>;
}

export function buildReviewPageData(
  cwd: string,
  startCommit: string,
  files: FileStat[],
  opts: { implementing?: boolean; banner?: string; guide?: ReviewGuide | null; taskId: string },
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
  return {
    taskId: opts.taskId,
    banner: opts.banner ?? "",
    implementing,
    guide: opts.guide ?? null,
    files,
    diffs,
  };
}

import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
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
  });
}

export function startReviewServer(data: ReviewPageData): Promise<RunningReviewServer> {
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
        const payload = JSON.parse(await readBody(req)) as ReviewDecisionPayload;
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        if (!settled) { settled = true; resolveDecision(payload); }
        server.close();
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
