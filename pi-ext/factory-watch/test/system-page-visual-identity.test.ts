import { describe, expect, it } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

describe("system navigator visual identity", () => {
  const html = renderSystemPageHtml();

  it("renders distinct landing and focus workspaces immediately", () => {
    expect(html).not.toContain('<section id="content" hidden>');
    expect(html).toContain('id="landingPanel"');
    expect(html).toContain('id="scopeWorkspace" hidden');
    expect(html).toContain('id="healthStatus"');
    expect(html).toContain('id="retryHealth"');
  });

  it("defines the midnight evidence-console tokens", () => {
    expect(html).toContain("--bg: #071015");
    expect(html).toContain("--surface: #0d1a20");
    expect(html).toContain("--signal: #65d9ff");
    expect(html).toContain("--font-display:");
    expect(html).toContain("--font-mono:");
    expect(html).toContain("prefers-reduced-motion: reduce");
  });

  it("becomes one column on narrow viewports", () => {
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
    expect(html).toMatch(/@media \(max-width: 760px\)[\s\S]*#tabs\s*\{[^}]*overflow-x:\s*auto/);
  });

  it("relates tabs and panels accessibly", () => {
    expect(html).toContain('id="panelBrief" class="panel" role="tabpanel" aria-labelledby="tabBrief"');
    expect(html).toContain('id="tabBrief" class="tab" role="tab" tabindex="0"');
    expect(html).toContain('id="tabMatrix" class="tab" role="tab" tabindex="-1"');
  });
});
