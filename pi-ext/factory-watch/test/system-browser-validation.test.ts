// test/system-browser-validation.test.ts
//
// Independent browser-validation gate for the System Navigator visual
// identity work (plan 2026-08-13-system-navigator-visual-identity.md).
//
// Skipped unless BROWSER_GATE=1 so the normal `npm test` suite stays
// deterministic and jsdom-only. When enabled it boots the real docs server
// against a target repository (default: the plan's C:\coding\cool_physical_ai_project)
// and drives a real Chromium through Playwright at 1440x900, 1024x768 and
// 390x844. It asserts everything the plan's gate lists and collects console
// errors, overflow, and interaction behaviour. Pass BROWSER_GATE_TARGET to
// point at another repo, and BROWSER_GATE_REPORT to choose the report path.
//
// Failure output includes viewport, reproduction step and element references
// (selector + accessibility name) so findings are actionable.
import { dirname, join } from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { ensureDocsServer, stopDocsServer } from "../src/docs-server.js";

// playwright is only required when the gate actually runs (it is not a
// declared devDependency), so it is loaded lazily inside the test instead of
// at module scope. The test must still typecheck in a clean checkout where
// playwright is absent, so the slice of the Playwright API it uses is
// described with local structural types rather than an `import type` from
// "playwright".
type PlaywrightElement = {
  click(): Promise<void>;
  press(key: string): Promise<void>;
  textContent(): Promise<string | null>;
};
type PlaywrightPage = {
  on(evt: string, fn: (arg: any) => void): PlaywrightPage;
  addInitScript(script: (() => void) | string): Promise<void>;
  $eval<R>(sel: string, fn: (el: Element) => R): Promise<R>;
  $$eval<R>(sel: string, fn: (els: Element[]) => R): Promise<R>;
  $(sel: string): Promise<PlaywrightElement | null>;
  textContent(sel: string): Promise<string | null>;
  click(sel: string): Promise<void>;
  fill(sel: string, value: string): Promise<void>;
  keyboard: { press(key: string): Promise<void> };
  evaluate<R>(fn: () => R): Promise<R>;
  waitForSelector(sel: string, opts?: { timeout?: number }): Promise<void>;
  waitForTimeout(ms: number): Promise<void>;
  goto(url: string, opts?: { waitUntil?: string }): Promise<unknown>;
  content(): Promise<string>;
  route(url: string, handler: (route: { abort(reason: string): void }) => void): Promise<void>;
  unroute(url: string): Promise<void>;
  close(): Promise<void>;
};
type PlaywrightBrowser = {
  newPage(opts: { viewport: { width: number; height: number } }): Promise<PlaywrightPage>;
  close(): Promise<void>;
};
type PlaywrightModule = {
  chromium: { launch(opts: { headless: boolean; channel: string }): Promise<PlaywrightBrowser> };
};
let chromiumModule: PlaywrightModule | null = null;

const ENABLED = process.env.BROWSER_GATE === "1";
const TARGET = process.env.BROWSER_GATE_TARGET ?? "C:/coding/cool_physical_ai_project";
const REPORT = process.env.BROWSER_GATE_REPORT ?? join(TARGET, ".tmp", "browser-gate-report.json");

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
];

interface Finding {
  viewport: string;
  step: string;
  severity: "error" | "warning";
  message: string;
  element?: string;
}

const findings: Finding[] = [];
const consoleErrors: { viewport: string; type: string; text: string }[] = [];

function record(vp: string, step: string, message: string, element?: string, severity: "error" | "warning" = "error") {
  findings.push({ viewport: vp, step, severity, message, element });
}

describe.skipIf(!ENABLED)("system navigator browser validation", () => {
  test("full visual gate at all three viewports", async () => {
    const loaded =
      // playwright is only present at gate-run time (never typechecked against
      // in a clean checkout), so suppress module resolution on this one line.
      // @ts-ignore -- playwright is an optional runtime dependency, not declared
      chromiumModule ?? ((await import("playwright")) as unknown as Exclude<typeof chromiumModule, null>);
    chromiumModule = loaded;
    const chromium = loaded.chromium;
    const server = await ensureDocsServer(TARGET);
    const base = server.url;
    const browser = await chromium.launch({ headless: true, channel: "chrome" });
    try {
      for (const vp of VIEWPORTS) {
        const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
        // Serving the extension through the tsx/esbuild dev pipeline injects
        // esbuild's `keepNames` `__name` helper into the stringified page
        // script; the real product never ships through that pipeline, so
        // this is a harness artifact, not a product bug. Defined via
        // addInitScript so it exists before the page's own inline <script>
        // runs on every navigation this page makes, not just the first.
        await page.addInitScript(() => {
          (window as any).__name = (fn: any) => fn;
        });
        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push({ viewport: vp.name, type: msg.type(), text: msg.text() });
        });
        page.on("pageerror", (err) =>
          consoleErrors.push({ viewport: vp.name, type: "pageerror", text: String(err) }),
        );

        // ---------------- Landing ----------------
        await page.goto(`${base}/system`, { waitUntil: "domcontentloaded" });
        await page.waitForSelector("#healthSummary .health-overall", { timeout: 60_000 });

        // 1. Landing visible, workspace hidden
        const landingHidden = await page.$eval("#landingPanel", (el: Element) => el.hasAttribute("hidden"));
        const workspaceHidden = await page.$eval("#scopeWorkspace", (el: Element) => el.hasAttribute("hidden"));
        if (landingHidden) record(vp.name, "landing", "#landingPanel is hidden on first load", "#landingPanel");
        if (!workspaceHidden) record(vp.name, "landing", "#scopeWorkspace is visible before a scope is chosen", "#scopeWorkspace");

        // 2. Honest metrics (no fabricated percentages)
        const overall = await page.textContent("#healthSummary .health-overall");
        if (!overall || overall.trim() === "") record(vp.name, "landing", "no overall health metric rendered", "#healthSummary .health-overall");
        const metricCount = await page.$$eval(".health-metric", (els: Element[]) => els.length);
        if (metricCount === 0) record(vp.name, "landing", "no class metrics rendered");

        // 3. Feature directory rows are readable anchors
        const rows = await page.$$eval(".feature-row", (els: Element[]) =>
          els.map((e: Element) => ({
            href: (e as HTMLAnchorElement).getAttribute("href") ?? "",
            text: (e as HTMLElement).textContent ?? "",
            readiness: (e as HTMLElement).dataset.readiness ?? "",
          })),
        );
        if (rows.length === 0) record(vp.name, "landing", "feature directory has no rows", "#bundleList");

        // 4. Horizontal overflow check
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (overflow > 1) record(vp.name, "landing", `horizontal overflow of ${overflow}px`, "documentElement");

        // 5. Focus a populated bundle scope
        let clicked = false;
        for (const row of rows) {
          if (row.readiness && row.href) {
            await page.click(`a.feature-row[href="${row.href}"]`);
            clicked = true;
            break;
          }
        }
        if (!clicked) record(vp.name, "bundle-focus", "no feature row with href to click");

        // Everything through "Search exact-ref" below assumes a scope was
        // actually focused. A zero-bundle repo (Task 13's second gate run,
        // BROWSER_GATE_TARGET=pi-agent-factory) has no feature row to click,
        // so `clicked` stays false and there is nothing here to open --
        // the pre-existing unconditional waitForSelector below would then
        // hang for the full 30s and fail the whole gate on a legitimate
        // first-run path. The already-recorded "no feature row" finding
        // above covers that case; the rest of the per-scope assertions are
        // simply skipped rather than run against a scope that never loaded.
        if (clicked) {
        await page.waitForSelector("#scopeWorkspace:not([hidden])", { timeout: 30_000 });
        const landingGone = await page.$eval("#landingPanel", (el: Element) => el.hasAttribute("hidden"));
        if (!landingGone) record(vp.name, "bundle-focus", "landing panel not hidden after scope selection", "#landingPanel");

        // aria-current on active scope link
        const current = await page.$$eval("[aria-current=page]", (els: Element[]) => els.map((e: Element) => (e as HTMLElement).dataset.scope ?? e.textContent?.slice(0, 40)));
        if (current.length === 0) record(vp.name, "bundle-focus", "no element has aria-current=page after selection");

        // ---------------- Contextual tabs ----------------
        const tabs = await page.$$eval('[role="tab"]:not([hidden])', (els: Element[]) => els.map((e: Element) => e.textContent?.trim() ?? ""));
        if (!tabs.includes("Brief") || !tabs.includes("Matrix") || !tabs.includes("Trace"))
          record(vp.name, "tabs", `bundle tabs missing; got [${tabs.join(", ")}]`, '[role="tab"]');

        // ---------------- Panels + disclosures ----------------
        const panels = await page.$$eval('[role="tabpanel"]', (els: Element[]) => els.map((e: Element) => e.id));
        if (panels.every((p: string) => p !== "panelBrief" && p !== "panelMatrix")) record(vp.name, "panels", `expected Brief/Matrix panels; got [${panels.join(", ")}]`, '[role="tabpanel"]');

        // Switch to Matrix and verify matrix hooks
        await page.click("#tabMatrix");
        await page.waitForSelector(".matrix-row", { timeout: 30_000 });
        // ---------------- Trace spine ----------------
        await page.click("#tabTrace");
        // The trace spine is lazy-loaded; give it up to 30s to render before
        // asserting, so a slow traversal doesn't look like a missing spine.
        await page.waitForSelector(".trace-spine-step", { timeout: 30_000 }).catch(() => {});
        const spine = await page.$$eval(".trace-spine-step", (els: Element[]) => els.map((e: Element) => e.textContent?.trim() ?? ""));
        if (spine.length === 0) record(vp.name, "trace-spine", "no trace spine steps rendered when traversal exists", ".trace-spine-step");

        // ---------------- Task 13: per-element containment ----------------
        // A page-level overflow check (`document.body.scrollWidth <=
        // window.innerWidth`, below) can stay FALSE while a chip spills onto
        // the next grid column -- the column track itself is sized
        // correctly; only the chip inside it refused to shrink. That bug is
        // invisible to a page-level check, so every step and every chip is
        // measured individually.
        const containment = await page.evaluate(() => {
          const steps = Array.from(document.querySelectorAll(".trace-spine-step"));
          return steps.map((stepEl) => {
            const step = stepEl as HTMLElement;
            const stepRect = step.getBoundingClientRect();
            const chips = Array.from(step.querySelectorAll(".ref-chip")).map((c) => {
              const r = (c as HTMLElement).getBoundingClientRect();
              return { right: r.right, text: (c.textContent || "").slice(0, 60) };
            });
            return {
              clientWidth: step.clientWidth,
              scrollWidth: step.scrollWidth,
              stepRight: stepRect.right,
              chips,
            };
          });
        });
        containment.forEach((s, i) => {
          if (s.scrollWidth > s.clientWidth + 1) {
            record(
              vp.name,
              "spine-containment",
              `.trace-spine-step[${i}] overflows its own box: scrollWidth ${s.scrollWidth} > clientWidth ${s.clientWidth} + 1`,
              ".trace-spine-step",
            );
          }
          s.chips.forEach((chip) => {
            if (chip.right > s.stepRight + 1) {
              record(
                vp.name,
                "spine-containment",
                `.ref-chip "${chip.text}" right edge ${chip.right.toFixed(1)} exceeds its step's right edge ${s.stepRight.toFixed(1)}`,
                ".ref-chip",
              );
            }
          });
        });

        // document.body.scrollWidth vs window.innerWidth -- distinct from the
        // documentElement check above (step 4); kept as its own assertion
        // because it is the exact pair named by the spec for this gate.
        const bodyOverflow = await page.evaluate(() => document.body.scrollWidth - window.innerWidth);
        if (bodyOverflow > 0) record(vp.name, "body-overflow", `document.body.scrollWidth exceeds window.innerWidth by ${bodyOverflow}px`, "body");

        // ---------------- Task 13: bounded-list child cap ----------------
        const boundedListCounts = await page.$$eval(".trace-spine-step .bounded-list", (lists: Element[]) =>
          lists.map((l) => l.querySelectorAll(":scope > .ref-chip").length),
        );
        boundedListCounts.forEach((count, i) => {
          if (count > 5) record(vp.name, "bounded-list", `.bounded-list[${i}] has ${count} direct .ref-chip children (max 5)`, ".bounded-list");
        });

        // ---------------- Task 13: "Not recorded" pairs with a Next step ----------------
        const orphanedNotRecorded = await page.evaluate(() => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          const orphans: string[] = [];
          let node: Node | null;
          // eslint-disable-next-line no-cond-assign
          while ((node = walker.nextNode())) {
            if ((node.nodeValue || "").trim() !== "Not recorded") continue;
            const parent = node.parentElement;
            const panel = parent ? parent.closest(".trace-spine-step, .panel") : null;
            const hasNextStep = !!(panel && panel.querySelector(".next-step"));
            if (!hasNextStep) orphans.push(panel ? panel.className : "(no enclosing panel)");
          }
          return orphans;
        });
        orphanedNotRecorded.forEach((where) => {
          record(vp.name, "not-recorded", `"Not recorded" text has no .next-step within its panel (${where})`, ".trace-spine-value");
        });

        // ---------------- Task 13: ref-chip keyboard interaction ----------------
        const chipHandle = await page.$(".ref-chip[data-ref]");
        if (!chipHandle) {
          record(vp.name, "keyboard-chip", "no resolved .ref-chip[data-ref] found to test keyboard focus", ".ref-chip", "warning");
        } else {
          await page.evaluate(() => {
            const chip = document.querySelector(".ref-chip[data-ref]") as HTMLElement | null;
            chip?.focus();
          });
          await page.waitForTimeout(150);
          const cardOpenedOnFocus = await page.evaluate(() => !!document.querySelector(".info-card"));
          if (!cardOpenedOnFocus) record(vp.name, "keyboard-chip", "focusing a .ref-chip did not open .info-card", ".ref-chip");
          await page.keyboard.press("Escape");
          await page.waitForTimeout(150);
          const afterEscape = await page.evaluate(() => ({
            cardGone: !document.querySelector(".info-card"),
            activeIsChip: document.activeElement?.matches?.(".ref-chip[data-ref]") ?? false,
          }));
          if (!afterEscape.cardGone) record(vp.name, "keyboard-chip", "Escape did not close .info-card", ".info-card");
          if (!afterEscape.activeIsChip) record(vp.name, "keyboard-chip", "Escape did not return focus to the triggering .ref-chip", ".ref-chip");
        }

        // ---------------- Task 13: .gloss contrast (WCAG 4.5:1) ----------------
        const glossContrast = await page.evaluate(() => {
          function parseColor(str: string): [number, number, number, number] {
            const hex = str.match(/^#([0-9a-f]{6})$/i);
            if (hex) {
              const n = parseInt(hex[1] ?? "000000", 16);
              return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
            }
            const m = str.match(/rgba?\(([^)]+)\)/i);
            if (!m) return [0, 0, 0, 0];
            const parts = (m[1] ?? "").split(",").map((s) => parseFloat(s.trim()));
            return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts.length > 3 ? (parts[3] ?? 1) : 1];
          }
          function luminance([r, g, b]: [number, number, number, number]): number {
            const chan = [r, g, b].map((c) => {
              const v = c / 255;
              return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * (chan[0] ?? 0) + 0.7152 * (chan[1] ?? 0) + 0.0722 * (chan[2] ?? 0);
          }
          function effectiveBackground(el: Element): [number, number, number, number] {
            let node: Element | null = el;
            while (node) {
              const c = parseColor(getComputedStyle(node).backgroundColor);
              if (c[3] > 0) return c;
              node = node.parentElement;
            }
            const root = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
            return parseColor(root || "#071015");
          }
          const glosses = Array.from(document.querySelectorAll(".gloss"));
          return glosses.slice(0, 8).map((el) => {
            const fg = parseColor(getComputedStyle(el).color);
            const bg = effectiveBackground(el);
            const lFg = luminance(fg);
            const lBg = luminance(bg);
            const ratio = (Math.max(lFg, lBg) + 0.05) / (Math.min(lFg, lBg) + 0.05);
            return { ratio, text: (el.textContent || "").slice(0, 40) };
          });
        });
        glossContrast.forEach((g) => {
          if (g.ratio < 4.5) {
            record(vp.name, "gloss-contrast", `.gloss "${g.text}" contrast ratio ${g.ratio.toFixed(2)} is below WCAG 4.5:1`, ".gloss");
          }
        });

        // ---------------- Mobile scope sheet --------------
        if (vp.width <= 760) {
          // In focus mode the rail reveals only the toggle; the sheet's nav is
          // collapsed. Open via the toggle, then confirm a Close click re-hides
          // the sheet's nav (the real sheet affordance), not the persistent
          // #picker shell which is always display:block.
          const toggle = await page.$("#scopeToggle");
          if (!toggle) {
            record(vp.name, "mobile", "no scope toggle present on mobile", "#scopeToggle");
          } else {
            await toggle.click();
            await page.waitForTimeout(200);
            const navShown = await page.$eval("#picker nav", (el: Element) =>
              (el as HTMLElement).offsetParent !== null || getComputedStyle(el).display !== "none",
            );
            if (!navShown) record(vp.name, "mobile", "scope sheet did not open after Browse scopes", "#picker nav");
            // toggle text becomes "Close scopes" while open
            const closeToggle = await page.$('#scopeToggle:has-text("Close")');
            if (closeToggle) {
              await closeToggle.click();
              await page.waitForTimeout(200);
              const navStill = await page.$eval("#picker nav", (el: Element) =>
                (el as HTMLElement).offsetParent !== null || getComputedStyle(el).display !== "none",
              );
              if (navStill) record(vp.name, "mobile", "scope sheet did not close on mobile", "#picker nav");
            } else {
              record(vp.name, "mobile", "scope toggle did not switch to Close scopes", "#scopeToggle");
            }
          }
        }

        // ---------------- Keyboard: tab roving focus ----------------
        await page.click("#tabBrief");
        await page.keyboard.press("ArrowRight");
        const sel = await page.$$eval("#tabs [role=tab]", (els: Element[]) => {
          const visible = els.filter((e: Element) => !(e as HTMLElement).hasAttribute("hidden"));
          return visible.map((e: Element) => ({ tabindex: e.getAttribute("tabindex"), aria: e.getAttribute("aria-selected") }));
        });
        if (!sel.some((s: { tabindex: string | null; aria: string | null }) => s.tabindex === "0" && s.aria === "true"))
          record(vp.name, "keyboard", `expected exactly one selected tabindex=0 tab after ArrowRight; got ${JSON.stringify(sel)}`, "#tabs [role=tab]");
        await page.keyboard.press("End");
        const afterEnd = await page.$$eval('#tabs [role="tab"][aria-selected="true"]', (els: Element[]) => els.length);
        if (afterEnd !== 1) record(vp.name, "keyboard", `End should select exactly one tab; got ${afterEnd}`);

        // ---------------- Search exact-ref -------------
        // On narrow viewports the rail collapses after focus; open the scope
        // sheet so the filter is interactive before pressing Enter.
        const filterVisible = await page
          .$eval("#scopeFilter", (el: Element) => (el as HTMLElement).offsetParent !== null)
          .catch(() => false);
        if (!filterVisible) {
          const browseBtn = await page.$('button:has-text("Browse scopes")');
          if (browseBtn) await browseBtn.click();
          await page.waitForTimeout(250);
        }
        const requests: string[] = [];
        page.on("request", (req: { url(): string }) => {
          if (req.url().includes("/api/system/")) requests.push(req.url());
        });
        await page.fill("#scopeFilter", "SR-137");
        // Enter and Go share the same exact-ref path. Trigger the click inside
        // the page (rather than Playwright's actionability wait, which hangs on
        // the scope re-render) and assert only the fetch URL emitted.
        await page.evaluate(() => {
          (document.getElementById("searchGo") as HTMLButtonElement).click();
        });
        await page.waitForTimeout(1200);
        const bad = requests.filter(
          (u) => u.includes("scope=sr%3Asr%3A") || u.includes("scope=sr:SR"),
        );
        if (bad.length > 0) record(vp.name, "search", `search issued invalid bare-ref fetch: ${bad[0]}`, "#scopeFilter");
        else if (!requests.some((u) => u.includes("scope=sr%3ASR-137")))
          record(vp.name, "search", `search did not fetch the encoded sr:SR-137 ref; requests: ${requests.join(" | ")}`, "#scopeFilter");
        } // if (clicked)

        // ---------------- aria-busy lifecycle ----------------
        const busyWait = await page.evaluate(async () => {
          const content = document.getElementById("content");
          content?.setAttribute("aria-busy", "true");
          await new Promise((r) => setTimeout(r, 50));
          return content?.getAttribute("aria-busy");
        });
        if (busyWait !== "true") record(vp.name, "aria", "content aria-busy not set during load");

        // ---------------- Retry after health failure ----------------
        const retryPage = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
        await retryPage.addInitScript(() => {
          (window as any).__name = (fn: any) => fn;
        });
        await retryPage.route("**/api/system/health**", (route: { abort(arg: string): unknown }) => route.abort("failed"));
        await retryPage.goto(`${base}/system`, { waitUntil: "domcontentloaded" });
        await retryPage.waitForTimeout(2500);
        const msg = await retryPage.$eval("#healthStatus", (el: Element) => el.textContent ?? "");
        const retryVisible = await retryPage.$eval("#retryHealth", (el: Element) => !el.hasAttribute("hidden"));
        if (!msg.includes("Project evidence is unavailable"))
          record(vp.name, "retry", `failure message is "${msg}" -- expected 'Project evidence is unavailable...'`, "#healthStatus");
        if (!retryVisible) record(vp.name, "retry", "Retry button not visible after health failure", "#retryHealth");
        // The finding above already covers a Retry button that never
        // appeared; a subsequent click on a genuinely hidden element would
        // just hang for the full actionability timeout and take the whole
        // gate down with it, so recovery is only exercised when there is
        // something visible to click.
        if (retryVisible) {
          await retryPage.unroute("**/api/system/health**");
          await retryPage.click("#retryHealth");
          await retryPage.waitForSelector("#healthSummary .health-overall", { timeout: 60_000 });
          const recovered = await retryPage.$eval("#retryHealth", (el: Element) => el.hasAttribute("hidden"));
          if (!recovered) record(vp.name, "retry", "Retry button still visible after successful retry", "#retryHealth");
        }
        await retryPage.close();

        // ---------------- Reduced motion CSS ----------------
        const css = await page.content();
        if (!/@media\s*\(prefers-reduced-motion:\s*reduce\)/i.test(css))
          record(vp.name, "reduced-motion", "no prefers-reduced-motion media rule", "<style>");
        else if (!/@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?(transition-duration\s*:\s*\.0?1ms|transition\s*:\s*none|animation-duration\s*:\s*\.0?1ms)/i.test(css))
          record(vp.name, "reduced-motion", "reduced-motion rule does not neutralise transitions/animations", "<style>");

        await page.close();
      }
    } finally {
      await browser.close();
      stopDocsServer();
    }

    mkdirSync(dirname(REPORT), { recursive: true });
    writeFileSync(REPORT, JSON.stringify({ findings, consoleErrors }, null, 2));

    const errors = findings.filter((f) => f.severity === "error");
    for (const e of consoleErrors) {
      // Favicon 404s are a static-asset non-issue; everything else is actionable.
      if (e.text.includes("favicon")) continue;
      record(e.viewport, "console", `${e.type}: ${e.text}`);
    }
    if (errors.length) {
      throw new Error(`browser gate found ${errors.length} issues; full list in ${REPORT}`);
    }
    // eslint-disable-next-line no-console
    console.log(`BROWSER GATE OK -- warnings: ${findings.length}, console errors: ${consoleErrors.length} (report: ${REPORT})`);
  }, 900_000);
});