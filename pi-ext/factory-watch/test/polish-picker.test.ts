// test/polish-picker.test.ts
import { describe, expect, test } from "vitest";
import {
  parsePolishGroupList,
  polishPlaygroundLabel,
  parsePlaygroundIdFromLabel,
} from "../src/polish-picker.js";

describe("parsePolishGroupList", () => {
  test("parses the polish list --json contract", () => {
    const raw = JSON.stringify([
      { playground: "sim-live", usecases: ["scn_001", "scn_002"] },
      { playground: "ref", usecases: ["shark_warning"] },
    ]);
    expect(parsePolishGroupList(raw)).toEqual([
      { playground: "sim-live", usecases: ["scn_001", "scn_002"] },
      { playground: "ref", usecases: ["shark_warning"] },
    ]);
  });

  test("returns null on malformed JSON or bad shape", () => {
    expect(parsePolishGroupList("not json")).toBeNull();
    expect(parsePolishGroupList("{}")).toBeNull();
    expect(parsePolishGroupList('[{"playground":"x"}]')).toBeNull(); // missing usecases
    expect(parsePolishGroupList('[{"playground":"x","usecases":[1,2]}]')).toBeNull(); // non-string
  });

  test("returns an empty list for an empty array", () => {
    expect(parsePolishGroupList("[]")).toEqual([]);
  });
});

describe("polishPlaygroundLabel / parsePlaygroundIdFromLabel", () => {
  test("labels a playground with its usecase count", () => {
    expect(polishPlaygroundLabel({ playground: "sim-live", usecases: ["a", "b", "c"] })).toBe(
      "sim-live (3 usecases)",
    );
    expect(polishPlaygroundLabel({ playground: "ref", usecases: ["solo"] })).toBe(
      "ref (1 usecase)",
    );
  });

  test("round-trips playground id from its label", () => {
    expect(parsePlaygroundIdFromLabel("sim-live (3 usecases)")).toBe("sim-live");
  });

  test("returns null from a label with no id", () => {
    expect(parsePlaygroundIdFromLabel("  (3 usecases)")).toBeNull();
    expect(parsePlaygroundIdFromLabel("   ")).toBeNull();
  });
});
