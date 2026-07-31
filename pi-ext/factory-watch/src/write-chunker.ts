// Threshold chosen conservatively relative to real-world max-output-token
// budgets (some models are configured with as few as 4096 max output
// tokens -- see the janvitos report on earendil-works/pi#4408). ~4000 chars
// is roughly 1000-1300 tokens, leaving comfortable headroom even there.
export const WRITE_CHUNK_THRESHOLD_CHARS = 4000;

export function splitContent(content: string, chunkSize: number): string[] {
  if (chunkSize <= 0) {
    throw new Error("chunkSize must be positive");
  }
  const chunks: string[] = [];
  for (let i = 0; i < content.length; i += chunkSize) {
    chunks.push(content.slice(i, i + chunkSize));
  }
  return chunks.length === 0 ? [""] : chunks;
}
