import { describe, it, expect } from "vitest";
import { parsePolishStateFile } from "../src/polish-model.js";

describe("parsePolishStateFile", () => {
  it("parses a well-formed state file", () => {
    const raw = JSON.stringify({
      seq: 3,
      state: {
        usecase: "sign-in",
        entrypoints: ["http://x"],
        queue_size: 1,
        gate1_ids: ["g1-1"],
        gate1: [{ gid: "g1-1", description: "broken", sr: "SR-010" }],
        gate2: [
          {
            gid: "g2-1",
            task_id: "T-007",
            description: "fix",
            sr: null,
            status: "landed",
            verdict: "pending",
          },
        ],
      },
    });
    const parsed = parsePolishStateFile(raw);
    expect(parsed?.seq).toBe(3);
    expect(parsed?.state.gate1[0]?.description).toBe("broken");
    expect(parsed?.state.gate2[0]?.status).toBe("landed");
  });

  it("returns null on malformed json (never throws)", () => {
    expect(parsePolishStateFile("{not json")).toBeNull();
  });

  it("returns null when the envelope is missing seq or state", () => {
    expect(parsePolishStateFile(JSON.stringify({ state: {} }))).toBeNull();
    expect(parsePolishStateFile(JSON.stringify({ seq: 1 }))).toBeNull();
  });
});
