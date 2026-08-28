import { describe, expect, test } from "vitest";
import { intersectModelCatalog, modelKey, type NativeModelCatalogEntry } from "../src/model-catalog.js";

describe("planning model catalog", () => {
  const configured: NativeModelCatalogEntry[] = [
    { provider: "openai", id: "review", qualityTier: "high", local: false, costClass: "low", free: false },
  ];

  test("intersects policy entries with native configured models deterministically", () => {
    expect(intersectModelCatalog(configured, ["openai:review", "missing:model"])).toEqual(configured);
    expect(modelKey(configured[0]!)).toBe("openai:review");
  });
});
