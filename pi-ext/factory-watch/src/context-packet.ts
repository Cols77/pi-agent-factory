import { readFileSync } from "node:fs";
import { join } from "node:path";

// Extension-side reader for item 1's content-bearing context packet. The Python
// orchestrator persists `<transcript_dir>/context-packet.json` (the same dir
// that holds the grill result / review guide), so the grill seed can be fed the
// gathered context instead of re-reading the codebase from zero.

interface PacketFileEntry {
  primary?: boolean;
  kind?: string;
  content?: string | null;
  signatures?: Array<{ kind: string; name: string; signature: string; line: number; summary?: string }>;
  reason?: string | null;
}

interface Packet {
  primary_files?: string[];
  reference_files?: string[];
  files?: Record<string, PacketFileEntry>;
  missing?: string[];
  truncated?: boolean;
}

export function contextPacketPath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "context-packet.json");
}

export function readContextPacket(cwd: string, sessionId: string): Packet | null {
  try {
    const raw = readFileSync(contextPacketPath(cwd, sessionId), "utf-8");
    const parsed = JSON.parse(raw) as Packet;
    if (parsed && typeof parsed === "object" && parsed.files) return parsed;
    return null;
  } catch {
    return null;
  }
}

const PACKET_SLICE_MAX_CHARS = 24000;

// Lightweight, bounded mirror of Python's render_packet: primary files in full,
// reference files as signatures. Deterministic grouping (reference then primary,
// matching the packet's file ordering).
export function renderPacketSlice(packet: Packet, maxChars: number = PACKET_SLICE_MAX_CHARS): string {
  const files = packet.files ?? {};
  const lines: string[] = [];
  let used = 0;

  const push = (s: string): void => {
    if (used >= maxChars) return;
    lines.push(s);
    used += s.length;
  };

  push("## Context packet (gathered by your context gatherer)");
  const order = [...(packet.reference_files ?? []), ...(packet.primary_files ?? [])];
  for (const rel of order) {
    if (used >= maxChars) break;
    const entry = files[rel];
    if (!entry) continue;
    push(`### ${entry.primary ? "PRIMARY" : "REFERENCE"} — ${rel}`);
    if (entry.kind === "content" && typeof entry.content === "string") {
      let body = entry.content;
      if (used + body.length > maxChars) body = body.slice(0, maxChars - used) + "\n…(truncated)";
      push("```");
      push(body.replace(/\n+$/, ""));
      push("```");
    } else if (entry.kind === "signatures" && Array.isArray(entry.signatures)) {
      if (entry.signatures.length === 0) push("_(no extractable signatures)_");
      for (const s of entry.signatures) {
        if (used >= maxChars) break;
        push(`- L${s.line} ${s.signature}${s.summary ? ` — ${s.summary}` : ""}`);
      }
    } else {
      push(`_(skipped: ${entry.reason ?? "skipped"})_`);
    }
    push("");
  }
  if (Array.isArray(packet.missing) && packet.missing.length > 0) {
    push(`_Note: ${packet.missing.length} referenced file(s) missing on disk._`);
  }
  if (packet.truncated) push("_Note: packet was truncated to its token budget._");
  return lines.join("\n");
}
