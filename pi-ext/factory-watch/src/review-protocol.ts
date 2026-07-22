export interface ReviewPendingMessage {
  type: "review_pending";
  task_id: string;
  start_commit: string;
}

export function parseReviewPendingLine(line: string): ReviewPendingMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  if (
    typeof parsed === "object" &&
    parsed !== null &&
    (parsed as { type?: unknown }).type === "review_pending"
  ) {
    return parsed as ReviewPendingMessage;
  }
  return null;
}

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export function writeReviewDecision(
  stdin: NodeJS.WritableStream,
  decision: ReviewDecisionPayload,
): void {
  stdin.write(JSON.stringify(decision) + "\n");
}
