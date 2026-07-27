import { describe, expect, test } from "vitest";
import { parseSessionTranscript } from "../src/session-transcript.js";

const JSONL = [
  JSON.stringify({ type: "session", id: "019f", cwd: "/repo" }),
  JSON.stringify({ type: "message_end", message: { role: "user", content: [{ type: "text", text: "implement T-030" }] } }),
  JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "writing the test first" }, { type: "tool_use", name: "write" }] } }),
  "not json, skip me",
].join("\n");

test("renders user/assistant text with a role prefix", () => {
  const out = parseSessionTranscript(JSONL);
  expect(out).toContain("implement T-030");
  expect(out).toContain("writing the test first");
});

test("summarizes tool calls on one line", () => {
  expect(parseSessionTranscript(JSONL)).toContain("[tool] write");
});

test("skips unparseable lines without throwing", () => {
  expect(() => parseSessionTranscript(JSONL)).not.toThrow();
});

test("empty input yields empty string", () => {
  expect(parseSessionTranscript("")).toBe("");
});
