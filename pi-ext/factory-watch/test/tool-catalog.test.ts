import { describe, expect, test } from "vitest";
import { factoryToolsCatalog, formatToolCatalog } from "../src/tool-catalog.js";

describe("factoryToolsCatalog derives from the real registrations", () => {
  test("includes all five families and the ~30 known tools", () => {
    const catalog = factoryToolsCatalog();
    const names = catalog.map((t) => t.name);
    expect(names).toContain("subagent");
    expect(names).toContain("trace_next");
    expect(names).toContain("trace_defer");
    expect(names).toContain("system_briefing");
    expect(names).toContain("eng_get_vcycle");
    expect(names).toContain("eng_present");
    expect(names).toContain("factory_run_suggest");
    expect(new Set(names).size).toBe(names.length);
    expect(names.length).toBeGreaterThanOrEqual(29);
  });

  test("formats grouped by family", () => {
    const line = formatToolCatalog(factoryToolsCatalog());
    expect(line).toContain("delegation (subagent)");
    expect(line).toContain("trace (");
    expect(line).toContain("system-navigator (");
    expect(line).toContain("engineering-context (");
    expect(line).toContain("session-review (factory_run_suggest)");
  });
});