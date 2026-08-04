import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parsePolishTarget, pollPolishState } from "../src/index.js";

const emptyState = {
  usecase: "x",
  entrypoints: [],
  queue_size: 0,
  gate1_ids: [],
  gate1: [],
  gate2: [],
};

describe("pollPolishState", () => {
  it("returns state only when seq advances past lastSeq", () => {
    const dir = mkdtempSync(join(tmpdir(), "pc-"));
    const p = join(dir, "s.json");
    writeFileSync(p, JSON.stringify({ seq: 2, state: emptyState }));
    expect(pollPolishState(p, 1)?.seq).toBe(2);
    expect(pollPolishState(p, 2)).toBeNull(); // no advance
  });

  it("returns null when the state file does not exist yet", () => {
    const dir = mkdtempSync(join(tmpdir(), "pc-"));
    expect(pollPolishState(join(dir, "absent.json"), 0)).toBeNull();
  });

  it("returns null on a half-written file rather than throwing", () => {
    const dir = mkdtempSync(join(tmpdir(), "pc-"));
    const p = join(dir, "s.json");
    writeFileSync(p, '{"seq": 5, "sta');
    expect(pollPolishState(p, 0)).toBeNull();
  });
});

describe("parsePolishTarget", () => {
  it("parses <playground>:<usecase>", () => {
    expect(parsePolishTarget(" web:sign-in ")).toEqual({
      playground: "web",
      usecase: "sign-in",
    });
  });

  it("returns null when the target is missing or malformed", () => {
    expect(parsePolishTarget("")).toBeNull();
    expect(parsePolishTarget("web")).toBeNull();
  });
});
