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
