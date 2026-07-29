export interface Annotation {
  file: string;
  line?: number;                 // 1-based line in the diff's `side`; absent = file-level note
  side?: "old" | "new";          // default "new"
  body: string;
  severity?: "must-fix" | "suggestion";
}

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  annotations: Annotation[];
  reviewedFiles: string[];
}

export function buildDecision(
  decision: "approve" | "reject",
  annotations: Annotation[],
  reviewedFiles: string[],
): ReviewDecisionPayload {
  return { decision, annotations, reviewedFiles };
}

export function annotationsForFile(annotations: Annotation[], file: string): Annotation[] {
  return annotations.filter((a) => a.file === file);
}

export interface DiffRowMeta {
  kind: "add" | "del" | "context" | "hunk" | "meta";
  line?: number;
  side?: "old" | "new";
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function mapDiffRows(rawDiffLines: string[]): DiffRowMeta[] {
  const out: DiffRowMeta[] = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const raw of rawDiffLines) {
    if (raw.startsWith("diff --git ")) {
      inHunk = false; // new file section: treat following index/---/+++ as meta again
      out.push({ kind: "meta" });
      continue;
    }
    const hunk = HUNK_RE.exec(raw);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      inHunk = true;
      out.push({ kind: "hunk" });
      continue;
    }
    if (!inHunk) {
      out.push({ kind: "meta" }); // diff/index/---/+++ headers before the first hunk
      continue;
    }
    const c = raw[0];
    if (c === "\\") {
      // "\ No newline at end of file" marker -> not a real source line, no anchor
      out.push({ kind: "meta" });
    } else if (c === "+") {
      out.push({ kind: "add", line: newLine, side: "new" });
      newLine += 1;
    } else if (c === "-") {
      out.push({ kind: "del", line: oldLine, side: "old" });
      oldLine += 1;
    } else {
      // context (leading space)
      out.push({ kind: "context", line: newLine, side: "new" });
      oldLine += 1;
      newLine += 1;
    }
  }
  return out;
}

export function anchorForRow(meta: DiffRowMeta[], rowIndex: number): { line?: number; side?: "old" | "new" } {
  const m = meta[rowIndex];
  if (m === undefined || m.line === undefined) return {};
  return { line: m.line, side: m.side };
}
