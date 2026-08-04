// Shared JSON shapes for the polish file bridge. These MUST stay identical to
// what PolishBridge publishes and consumes (src/factory/polish/bridge.py); the
// two processes agree on nothing else.

export interface Gate1Item {
  gid: string;
  description: string;
  sr: string | null;
}

export interface Gate2Row {
  gid: string;
  task_id: string;
  description: string;
  sr: string | null;
  status: "landed" | "failed";
  verdict: "pending" | "accepted" | "wrong";
}

export interface PolishState {
  usecase: string;
  entrypoints: string[];
  queue_size: number;
  gate1_ids: string[];
  gate1: Gate1Item[];
  gate2: Gate2Row[];
}

export interface PolishStateFile {
  seq: number;
  state: PolishState;
}

export type PolishCommand =
  | { kind: "feedback"; args: { text: string } }
  | { kind: "accept"; args: { gid: string } }
  | { kind: "edit"; args: { gid: string; changes: Record<string, unknown> } }
  | { kind: "discard"; args: { gid: string } }
  | { kind: "tick"; args: { gid: string } }
  | { kind: "comment"; args: { gid: string; text: string } };

export function parsePolishStateFile(raw: string): PolishStateFile | null {
  try {
    const obj = JSON.parse(raw) as PolishStateFile;
    if (typeof obj?.seq !== "number" || typeof obj?.state !== "object" || obj.state === null) {
      return null;
    }
    return obj;
  } catch {
    return null; // half-written file or garbage; caller keeps the last good state
  }
}
