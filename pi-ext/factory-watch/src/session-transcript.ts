interface Block { type?: string; text?: string; name?: string }
interface Message { role?: string; content?: Block[] }
interface Event { type?: string; message?: Message }

export function parseSessionTranscript(jsonl: string): string {
  const out: string[] = [];
  for (const line of jsonl.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "") continue;
    let ev: Event;
    try {
      ev = JSON.parse(trimmed) as Event;
    } catch {
      continue;
    }
    if (ev.type !== "message_end" || !ev.message) continue;
    const role = ev.message.role ?? "?";
    for (const block of ev.message.content ?? []) {
      if (block.type === "text" && typeof block.text === "string") {
        out.push(`## ${role}`, block.text, "");
      } else if (block.type === "tool_use" && typeof block.name === "string") {
        out.push(`> [tool] ${block.name}`, "");
      }
    }
  }
  return out.join("\n").trimEnd();
}
