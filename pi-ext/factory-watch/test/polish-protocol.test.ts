import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  polishCommandsDir,
  polishStatePath,
  readPolishState,
  writePolishCommand,
} from "../src/polish-protocol.js";

let dir: string;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "polish-"));
});

describe("polish-protocol", () => {
  it("readPolishState returns null when the file is absent", () => {
    expect(readPolishState(join(dir, "nope.json"))).toBeNull();
  });

  it("readPolishState round-trips a written state", () => {
    const p = join(dir, "polish-state.json");
    writeFileSync(
      p,
      JSON.stringify({
        seq: 1,
        state: {
          usecase: "x",
          entrypoints: [],
          queue_size: 0,
          gate1_ids: [],
          gate1: [],
          gate2: [],
        },
      }),
    );
    expect(readPolishState(p)?.seq).toBe(1);
  });

  it("readPolishState returns null on a half-written file instead of throwing", () => {
    const p = join(dir, "polish-state.json");
    writeFileSync(p, '{"seq": 1, "sta');
    expect(readPolishState(p)).toBeNull();
  });

  it("writePolishCommand drops a uniquely-named json file each call", () => {
    writePolishCommand(dir, { kind: "feedback", args: { text: "a" } });
    writePolishCommand(dir, { kind: "accept", args: { gid: "g1-1" } });
    const files = readdirSync(dir)
      .filter((f) => f.endsWith(".json"))
      .sort();
    expect(files.length).toBe(2);
    expect(JSON.parse(readFileSync(join(dir, files[0]!), "utf-8")).kind).toBe("feedback");
  });

  it("leaves no .tmp files behind", () => {
    writePolishCommand(dir, { kind: "tick", args: { gid: "g2-1" } });
    expect(readdirSync(dir).filter((f) => f.endsWith(".tmp"))).toEqual([]);
  });

  it("derives session-scoped bridge paths", () => {
    expect(polishStatePath("/repo", "S1").replace(/\\/g, "/")).toBe(
      "/repo/sessions/.factory-transcripts/S1/polish-state.json",
    );
    expect(polishCommandsDir("/repo", "S1").replace(/\\/g, "/")).toBe(
      "/repo/sessions/.factory-transcripts/S1/polish-commands",
    );
  });
});
