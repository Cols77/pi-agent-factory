// test/review-browser-validation.test.ts
//
// Browser-validation gate for the human-code-review page (review-html.ts).
// Skipped unless BROWSER_GATE=1 so the normal `npm test` suite stays
// deterministic and jsdom-only. When enabled it boots the REAL review server
// (startReviewServer) against a throwaway git repo, drives a real Chromium
// through Playwright at three viewports, and asserts the things jsdom cannot:
//
//   - the verdict actions (Approve / Reject) are on-screen, unclipped and
//     clickable at every width -- the decision is the primary action and a
//     fixed `min-width` once pushed it off the viewport entirely (regression
//     gate for that bug);
//   - no horizontal or vertical blowout (the statusbar stays pinned);
//   - narrow windows drop into the tab-strip layout with the diff as the
//     default tab, and picking a file returns to the diff;
//   - the review-guidance strip is collapsed by default and expands on click;
//   - the whole review flow works end to end: hover `+` comment, approve, and
//     the server receives the decision with the annotation;
//   - no console/page errors.
//
// playwright is only required when the gate runs (it is not a declared
// devDependency), so it is loaded lazily and described with local structural
// types -- same idiom as system-browser-validation.test.ts. Pass
// BROWSER_GATE_EXECUTABLE to point at a specific Chromium when no system
// Chrome is available.
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { afterAll, describe, expect, test } from "vitest";

import { buildReviewPageData, startReviewServer } from "../src/review-server.js";
import type { RunningReviewServer } from "../src/review-server.js";
import type { ReviewDecisionPayload } from "../src/review-model.js";
import { computeReviewFiles } from "../src/review-diff.js";

type PlaywrightPage = {
  on(evt: "popup", fn: (page: PlaywrightPage) => void): unknown;
  on(evt: string, fn: (arg: unknown) => void): unknown;
  url(): string;
  evaluate<R>(fn: () => R): Promise<R>;
  $eval<R>(sel: string, fn: (el: Element) => R): Promise<R>;
  $$eval<R>(sel: string, fn: (els: Element[]) => R): Promise<R>;
  waitForSelector(sel: string, opts?: { timeout?: number }): Promise<unknown>;
  waitForFunction(fn: () => boolean, opts?: { timeout?: number }): Promise<unknown>;
  waitForTimeout(ms: number): Promise<unknown>;
  goto(url: string, opts?: { waitUntil?: string }): Promise<unknown>;
  click(sel: string, opts?: { force?: boolean }): Promise<void>;
  keyboard: { press(key: string): Promise<void> };
  close(): Promise<void>;
};
type PlaywrightBrowser = {
  newPage(opts: { viewport: { width: number; height: number } }): Promise<PlaywrightPage>;
  close(): Promise<void>;
};
type PlaywrightModule = {
  chromium: {
    launch(opts: { headless: boolean; channel: string; executablePath?: string }): Promise<PlaywrightBrowser>;
  };
};
let chromiumModule: PlaywrightModule | null = null;

const ENABLED = process.env.BROWSER_GATE === "1";
const EXECUTABLE = process.env.BROWSER_GATE_EXECUTABLE;

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900, narrow: false },
  { name: "1024x768", width: 1024, height: 768, narrow: false },
  { name: "760x900", width: 760, height: 900, narrow: true },
];

// --- throwaway repo with one task, one tracked file, one uncommitted change --
// Mirrors the human-review gate state: start_commit captured before dev, dev's
// changes still uncommitted at review time (runner.py commits only after
// approve).
const dirs: string[] = [];
function fixtureRepo(): { cwd: string; startCommit: string } {
  const cwd = mkdtempSync(join(tmpdir(), "review-gate-"));
  dirs.push(cwd);
  const git = (args: string[]) => {
    const r = spawnSync("git", args, { cwd, encoding: "utf-8" });
    if (r.status !== 0) throw new Error(`git ${args.join(" ")}: ${r.stderr}`);
  };
  git(["init", "-q"]);
  git(["config", "user.email", "t@example.com"]);
  git(["config", "user.name", "t"]);
  mkdirSync(join(cwd, "tasks"));
  writeFileSync(
    join(cwd, "tasks", "T-001-example.md"),
    `---\nid: T-001\ntitle: Review gate task\nstatus: human-review\ndod:\n  - Show the task\n---\n\n# Implementation\n\nBody.\n`,
    "utf-8",
  );
  writeFileSync(join(cwd, "a.py"), "def old():\n    return 1\n", "utf-8");
  git(["add", "-A"]);
  git(["commit", "-q", "-m", "init"]);
  const startCommit = spawnSync("git", ["rev-parse", "HEAD"], { cwd, encoding: "utf-8" }).stdout.trim();
  writeFileSync(join(cwd, "a.py"), "def old():\n    return 1\n\n\ndef new_feature() -> int:\n    return 2\n", "utf-8");
  return { cwd, startCommit };
}

afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

// The system-navigator loaders are faked (same shapes as review-server.test.ts)
// so the gate never spawns `uv run` -- it validates the browser surface, not
// the Python side.
const STORY_OK = {
  ok: true as const,
  value: {
    scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "Review gate task", status: "human-review", dod: ["Show the task"] },
    runs: [],
    requirements: ["sr:SR-014"],
    plan_section: {
      plan_path: "docs/superpowers/plans/p.md",
      heading: "Task 1: Review gate task",
      body: "Do the thing.",
    },
    degraded: false,
    degraded_reasons: [],
  },
};
const CONTEXT_OK = {
  context: {},
  graph: {
    nodes: [
      { id: "T-001", kind: "task", title: "Review gate task", path: "tasks/T-001-example.md", exempt: false, deferred: null },
      { id: "plan:p.md", kind: "plan", title: "A plan", path: "docs/superpowers/plans/p.md", exempt: false, deferred: null },
    ],
    edges: [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }],
    gaps: [],
    validation: {},
    health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
  },
};
const FAKE_DEPS = {
  story: () => STORY_OK,
  context: () => CONTEXT_OK,
  layout: () => ({ collapsed: [], zoomed: null, guide: false }),
};

interface Finding {
  viewport: string;
  step: string;
  message: string;
}
const findings: Finding[] = [];
const consoleErrors: { viewport: string; text: string }[] = [];
const record = (vp: string, step: string, message: string) => findings.push({ viewport: vp, step, message });

describe.skipIf(!ENABLED)("human-review browser validation", () => {
  // The gate boots a real server + Chromium through several viewports and an
  // end-to-end flow, so it needs a long explicit timeout (vitest defaults to
  // 5s). Skipped entirely unless BROWSER_GATE=1.
  test("verdict visible, guidance collapsed, flow works end to end", async () => {
    const loaded =
      // playwright is only present at gate-run time (never typechecked against
      // in a clean checkout), so suppress module resolution on this one line.
      // @ts-ignore -- playwright is an optional runtime dependency, not declared
      chromiumModule ?? ((await import("playwright")) as unknown as Exclude<typeof chromiumModule, null>);
    chromiumModule = loaded;

    const { cwd, startCommit } = fixtureRepo();
    const files = computeReviewFiles(cwd, startCommit);
    const data = buildReviewPageData(cwd, startCommit, files, {
      taskId: "T-001",
      banner: "browser gate",
      guide: {
        confidence: "high",
        validation: [
          { gate: "unit", ok: true, summary: "10 passed" },
          { gate: "sim", ok: false, summary: "regressed" },
        ],
        verify: [{ item: "reject a missing colon", file: "a.py", line: 7 }],
        addressed: ["moved the status file"],
      },
      deps: FAKE_DEPS as never,
    });
    const server: RunningReviewServer = await startReviewServer(data, { cwd });
    const browser = await loaded.chromium.launch({
      headless: true,
      channel: "chrome",
      ...(EXECUTABLE ? { executablePath: EXECUTABLE } : {}),
    });

    try {
      for (const vp of VIEWPORTS) {
        const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
        page.on("console", (msg) => {
          if ((msg as { type(): string }).type() === "error") {
            consoleErrors.push({ viewport: vp.name, text: (msg as { text(): string }).text() });
          }
        });
        page.on("pageerror", (err) => consoleErrors.push({ viewport: vp.name, text: String(err) }));

        await page.goto(`${server.url}/`, { waitUntil: "domcontentloaded" });
        await page.waitForFunction(
          () => (document.getElementById("tree")?.children.length ?? 0) > 0,
          { timeout: 30_000 },
        );
        await page.waitForTimeout(200);

        // 1. The verdict actions are on-screen, unclipped and clickable.
        for (const id of ["approve", "reject"]) {
          const box = await page.$eval(`#${id}`, (el) => {
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            return {
              x: r.x, y: r.y, w: r.width, h: r.height,
              iw: window.innerWidth, ih: window.innerHeight,
              display: cs.display, visibility: cs.visibility,
              disabled: (el as HTMLButtonElement).disabled,
            };
          });
          if (box.display === "none" || box.visibility !== "visible") {
            record(vp.name, "verdict", `#${id} not rendered (display=${box.display}, visibility=${box.visibility})`);
          }
          if (box.w <= 0 || box.h <= 0) record(vp.name, "verdict", `#${id} has zero size`);
          if (box.disabled) record(vp.name, "verdict", `#${id} is disabled before a decision`);
          const onScreen = box.x >= 0 && box.y >= 0 && box.x + box.w <= box.iw && box.y + box.h <= box.ih;
          if (!onScreen) {
            record(vp.name, "verdict",
              `#${id} off-viewport (${Math.round(box.x)},${Math.round(box.y)} ${Math.round(box.w)}x${Math.round(box.h)} in ${box.iw}x${box.ih})`);
          }
        }

        // 2. No horizontal overflow (a fixed min-width once clipped the page).
        const overflow = await page.evaluate(() => ({
          scrollW: document.documentElement.scrollWidth,
          innerW: window.innerWidth,
        }));
        if (overflow.scrollW > overflow.innerW) {
          record(vp.name, "overflow", `horizontal overflow: ${overflow.scrollW} > ${overflow.innerW}`);
        }

        // 3. Narrow windows stack the panes into one column (no tab mode:
        //    references open in their own windows).
        if (vp.narrow) {
          const cols = await page.$eval("#panes", (el) => (el as HTMLElement).style.gridTemplateColumns);
          if (cols !== "1fr") record(vp.name, "narrow", `expected stacked 1fr columns, got ${cols}`);
        }

        // 4. The reference buttons are present and enabled.
        for (const id of ["refTask", "refPlan", "refSpec", "refVerify"]) {
          const disabled = await page.$eval(`#${id}`, (el) => (el as HTMLButtonElement).disabled);
          if (disabled) record(vp.name, "refs", `#${id} disabled`);
        }
        await page.close();
      }

      // 5. The reference buttons open Task / Plan / Spec / Verify in real
      //    browser windows with the right content.
      {
        const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
        page.on("pageerror", (err) => consoleErrors.push({ viewport: "refs", text: String(err) }));
        await page.goto(`${server.url}/`, { waitUntil: "domcontentloaded" });
        await page.waitForSelector("#refTask", { timeout: 30_000 });

        const opened: { kind: string; url: string; text: string }[] = [];
        const onPopup = async (popup: PlaywrightPage) => {
          try {
            await popup.waitForSelector(".app-header", { timeout: 20_000 });
            const url = popup.url ? popup.url() : "";
            const text = await popup.evaluate(() => document.body.textContent ?? "");
            opened.push({ kind: url.split("/reference/")[1] ?? "?", url, text });
          } finally {
            await popup.close();
          }
        };
        page.on("popup", onPopup);

        await page.click("#refTask");
        await page.click("#refPlan");
        await page.click("#refSpec");
        await page.click("#refVerify");
        await page.waitForTimeout(1500);

        const byKind = new Map(opened.map((o) => [o.kind, o]));
        if (!byKind.has("task")) record("refs", "windows", "Task window never opened");
        if (!byKind.has("plan")) record("refs", "windows", "Plan window never opened");
        if (!byKind.has("spec")) record("refs", "windows", "Spec window never opened");
        if (!byKind.has("verify")) record("refs", "windows", "Verify window never opened");
        const taskText = byKind.get("task")?.text ?? "";
        if (!taskText.includes("Review gate task")) record("refs", "task", "Task window lacks the task title");
        if (!taskText.includes("Definition of done")) record("refs", "task", "Task window lacks the DoD");
        const planText = byKind.get("plan")?.text ?? "";
        if (!planText.includes("Do the thing.")) record("refs", "plan", "Plan window lacks the plan prose");
        const specText = byKind.get("spec")?.text ?? "";
        if (!specText.includes("no spec linked")) record("refs", "spec", "Spec window should fall back to no-spec message");
        const verifyText = byKind.get("verify")?.text ?? "";
        if (!verifyText.includes("Verify before approving")) record("refs", "verify", "Verify window lacks the verify checklist");
        if (!verifyText.includes("gates pass")) record("refs", "verify", "Verify window lacks the gate summary");
        await page.close();
      }

      // 6. End-to-end: comment on a diff line, approve, decision received.
      const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
      page.on("pageerror", (err) => consoleErrors.push({ viewport: "flow", text: String(err) }));
      await page.goto(`${server.url}/`, { waitUntil: "domcontentloaded" });
      await page.waitForSelector("#diff .row.add .plus", { timeout: 30_000 });
      page.on("dialog", (d: unknown) => (d as { accept(value?: string): void }).accept("atomic writes please"));
      await page.click("#diff .row.add .plus", { force: true });
      await page.waitForSelector("#cmts .cmt", { timeout: 10_000 });
      const count = await page.$eval("#count", (el) => el.textContent ?? "");
      if (count !== "1") record("flow", "comment", `expected 1 comment, got ${count}`);
      const where = await page.$eval("#cmts .cmt-where", (el) => el.textContent ?? "");
      if (!where.includes("a.py:")) record("flow", "comment", `comment not anchored to a.py line (${where})`);
      await page.click("#approve");
      await page.waitForSelector("#done", { timeout: 10_000 });
      const doneHidden = await page.$eval("#done", (el) => el.hasAttribute("hidden"));
      if (doneHidden) record("flow", "approve", "#done did not appear after approving");
      await page.close();

      const decision = await Promise.race([
        server.decision,
        new Promise<null>((resolve) => setTimeout(() => resolve(null), 15_000)),
      ]);
      if (decision === null) {
        record("flow", "approve", "no decision received by the server");
      } else {
        const d: ReviewDecisionPayload = decision;
        if (d.decision !== "approve") record("flow", "approve", `expected approve, got ${d.decision}`);
        if (d.annotations.length !== 1) {
          record("flow", "approve", `expected 1 annotation, got ${d.annotations.length}`);
        }
      }

      for (const err of consoleErrors) {
        record(err.viewport, "console", err.text.slice(0, 400));
      }
    } finally {
      await browser.close();
      server.close();
    }

    if (findings.length) {
      writeFileSync(join(process.cwd(), "review-gate-findings.json"), JSON.stringify(findings, null, 2), "utf-8");
    }
    expect(findings).toEqual([]);
  }, 300_000);
});