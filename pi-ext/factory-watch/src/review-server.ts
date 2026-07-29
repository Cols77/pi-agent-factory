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
