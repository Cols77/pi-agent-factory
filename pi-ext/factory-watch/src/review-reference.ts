// Read-only reference pages served by the review browser (GET /reference/*,
// review-server.ts). One standalone, self-contained page per component a
// reviewer may need to consult while judging a diff -- Task, Plan, Spec,
// Verify (verifications / validation state before approving). Each is opened
// in a new browser window from the review page's header buttons.
//
// XSS discipline: these pages are server-rendered strings with no client
// script at all -- every server-controlled string is escaped through esc(),
// and the only unescaped markup spliced in is renderMarkdown output (the same
// trusted renderer the review page and /review-plans already use). There are
// no innerHTML writes at runtime because there is no runtime.

import { readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import { renderMarkdown, stripDocFrontmatter } from "./md-render.js";
import type { ReviewPageData } from "./review-server.js";

export const REFERENCE_KINDS = ["task", "plan", "spec", "verify"] as const;
export type ReferenceKind = (typeof REFERENCE_KINDS)[number];

export function isReferenceKind(value: string): value is ReferenceKind {
  return (REFERENCE_KINDS as readonly string[]).includes(value);
}

function esc(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const STYLE = `
:root {
  color-scheme: dark;
  --bg-deep: #04090c; --bg: #071015; --surface: #0d1a20; --raised: #12242c; --soft: #102028;
  --line: #26404a; --line-strong: #3a606c;
  --text: #e7f2f5; --muted: #91a8b0; --dim: #698089;
  --signal: #65d9ff; --signal-soft: rgba(101, 217, 255, .12);
  --add: #72e6a6; --add-soft: rgba(114, 230, 166, .09); --add-softer: rgba(114, 230, 166, .05);
  --warn: #ffc857; --warn-soft: rgba(255, 200, 87, .10);
  --danger: #ff6b6b; --danger-soft: rgba(255, 107, 107, .09);
  --font-display: "Bahnschrift", "Aptos Display", "Segoe UI Variable Display", sans-serif;
  --font-body: "Aptos", "Segoe UI Variable Text", sans-serif;
  --font-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh;
  color: var(--text);
  background:
    radial-gradient(circle at 85% -12%, rgba(101, 217, 255, .10), transparent 34rem),
    linear-gradient(rgba(101, 217, 255, .02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(101, 217, 255, .02) 1px, transparent 1px),
    var(--bg);
  background-size: auto, 32px 32px, 32px 32px, auto;
  font: 14px/1.6 var(--font-body);
}
.app-header {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 14px;
  padding: 12px 24px; border-bottom: 1px solid var(--line);
  background: rgba(4, 9, 12, .88); backdrop-filter: blur(14px);
}
.eyebrow {
  color: var(--signal);
  font: 650 11px/1.2 var(--font-mono);
  letter-spacing: .16em; text-transform: uppercase;
}
.app-title { font: 650 18px/1.2 var(--font-display); letter-spacing: -.015em; margin: 2px 0 0; }
.back {
  margin-left: auto; border: 1px solid var(--line-strong); background: var(--surface);
  color: var(--muted); border-radius: 8px; padding: 6px 14px;
  font: 650 12px/1 var(--font-mono); text-decoration: none; white-space: nowrap;
}
.back:hover { border-color: var(--signal); color: var(--signal); background: var(--signal-soft); }
main { max-width: 980px; margin: 0 auto; padding: 22px 24px 60px; }
.meta-row { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; margin: 8px 0 4px; color: var(--muted); font: 12px var(--font-mono); }
.chip {
  display: inline-flex; align-items: center; border: 1px solid var(--line-strong); border-radius: 99px;
  padding: 1px 9px; font: 600 10.5px/1.7 var(--font-mono); letter-spacing: .05em; text-transform: uppercase;
  color: var(--muted); background: var(--soft); white-space: nowrap;
}
.chip.ok { color: var(--add); border-color: rgba(114, 230, 166, .45); background: var(--add-softer); }
.chip.warn { color: var(--warn); border-color: rgba(255, 200, 87, .45); background: var(--warn-soft); }
.chip.bad { color: var(--danger); border-color: rgba(255, 107, 107, .5); background: var(--danger-soft); }
.chip.sig { color: var(--signal); border-color: rgba(101, 217, 255, .45); background: var(--signal-soft); }
.chip.dim { color: var(--dim); }
.banner {
  color: #ffd3d3; background: rgba(255, 107, 107, .12);
  border: 1px solid rgba(255, 107, 107, .45); border-radius: 8px;
  padding: 8px 12px; margin: 0 0 18px; font: 12px/1.5 var(--font-mono); white-space: pre-wrap;
}
.banner:empty { display: none; }
.sec { display: flex; align-items: center; gap: 8px; margin: 22px 0 8px; }
.sec-title { color: var(--signal); font: 650 11px/1 var(--font-mono); letter-spacing: .14em; text-transform: uppercase; white-space: nowrap; }
.sec-line { flex: 1; height: 1px; background: linear-gradient(90deg, var(--line), transparent); }
.chain { list-style: none; margin: 0; padding: 0; }
.chain li {
  position: relative; margin: 0; padding: 4px 0 4px 20px;
  border-left: 1px solid rgba(101, 217, 255, .25);
  font: 12.5px/1.5 var(--font-mono); color: var(--text);
}
.chain li::before {
  content: ''; position: absolute; left: -4px; top: 50%;
  width: 7px; height: 7px; margin-top: -3.5px;
  border-radius: 50%; background: var(--surface); border: 1.5px solid var(--signal);
}
.chain li:last-child::before { background: var(--signal); }
.chain li .kind { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .08em; }
.chain li .id { color: var(--signal); font-weight: 700; }
.chain .more { color: var(--warn); font-size: 11px; }
.requirements { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0 2px; }
.dod { list-style: none; margin: 2px 0 0; padding: 0; }
.dod li { position: relative; padding: 2px 0 2px 22px; font: 12.5px/1.5 var(--font-mono); color: var(--text); }
.dod li::before { content: '\\25CB'; position: absolute; left: 4px; color: var(--dim); }
.stops { color: var(--warn); font: 11.5px/1.5 var(--font-mono); margin: 6px 0; }
.prose { margin-top: 8px; }
.prose pre { overflow: auto; padding: 10px 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.prose code { background: rgba(101, 217, 255, .08); padding: 1px 4px; border-radius: 4px; font-family: var(--font-mono); }
.prose pre code { background: none; padding: 0; }
.prose :is(h1, h2, h3, h4) { color: var(--text); margin: 1.1em 0 .45em; font: 650 1.08em/1.3 var(--font-display); }
.prose p { margin: .5em 0; }
.prose ul, .prose ol { padding-left: 1.4em; }
.prose blockquote { margin: .5em 0; padding: 2px 12px; border-left: 3px solid var(--line-strong); color: var(--muted); }
.prose table { border-collapse: collapse; margin: .6em 0; }
.prose th, .prose td { border: 1px solid var(--line); padding: 4px 10px; font-size: 13px; }
.resolved { color: var(--add); font: 600 11.5px/1.5 var(--font-mono); }
.gate-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.gate { border: 1px solid var(--line); background: var(--soft); border-radius: 8px; padding: 6px 10px; font: 12px/1.5 var(--font-mono); }
.gate.ok { border-color: rgba(114, 230, 166, .45); color: #cdeeda; }
.gate.bad { border-color: rgba(255, 107, 107, .5); color: #f4cfcf; }
.verify-item {
  display: flex; gap: 10px; margin: 6px 0; padding: 8px 10px;
  border: 1px solid rgba(255, 200, 87, .35); border-radius: 8px;
  background: var(--warn-soft); font: 12.5px/1.5 var(--font-mono); color: var(--text);
}
.verify-item .idx { color: var(--warn); font-weight: 700; flex: 0 0 auto; }
.verify-item .where { color: var(--dim); font-size: 11px; }
.spec-card { border: 1px solid var(--line); border-radius: 10px; background: var(--surface); padding: 4px 18px 14px; margin: 10px 0; }
`;

function shell(kind: string, title: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(kind)} · human review</title>
<link rel="icon" href="data:,">
<style>${STYLE}</style></head>
<body>
  <header class="app-header">
    <span class="eyebrow">Human review · ${esc(kind)}</span>
    <a class="back" href="/">← back to review</a>
  </header>
  <main>
    <h1 class="app-title">${esc(title)}</h1>
${body}
  </main>
</body></html>`;
}

function chip(cls: string, text: string): string {
  return `<span class="chip ${cls}">${esc(text)}</span>`;
}

function chainHtml(data: ReviewPageData): string {
  const intent = data.intent;
  const out: string[] = [];
  if (intent && intent.chain.length) {
    out.push(`<div class="sec"><span class="sec-title">Intent chain</span><span class="sec-line"></span></div>`);
    const hops = intent.chain.map((n) => {
      const more = n.alternatives ? ` <span class="more">  (+${n.alternatives} more)</span>` : "";
      return `<li><span class="kind">${esc(n.kind)}</span> · <span class="id">${esc(n.id)}</span> — ${esc(n.title)}${more}</li>`;
    });
    out.push(`<ul class="chain">${hops.join("")}</ul>`);
  }
  if (intent && intent.stopsAt) {
    out.push(`<div class="stops">stops at: ${esc(intent.stopsAt)} (nothing recorded links further up)</div>`);
  }
  const requirements = intent && Array.isArray(intent.requirements) ? intent.requirements : [];
  if (requirements.length) {
    out.push(`<div class="requirements">${requirements.map((r) => chip("sig", r)).join("")}</div>`);
  }
  return out.join("\n");
}

function taskPage(data: ReviewPageData): string {
  const task = data.task;
  const intent = data.intent;
  const title = task ? `${task.id} — ${task.title}` : data.taskId || "Task";
  const parts: string[] = [];
  if (data.banner) parts.push(`<div class="banner">${esc(data.banner)}</div>`);
  parts.push(chainHtml(data));
  const status = (intent && intent.status) || (task && task.status) || "unknown";
  parts.push(`<div class="meta-row">${chip("warn", status)}<span>${esc(task ? task.path : "task file unavailable")}</span></div>`);
  const dod = (intent && intent.dod.length ? intent.dod : (task ? task.dod : [])) || [];
  if (dod.length) {
    parts.push(`<div class="sec"><span class="sec-title">Definition of done</span><span class="sec-line"></span></div>`);
    parts.push(`<ul class="dod">${dod.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`);
  }
  if (task && task.html) {
    parts.push(`<div class="sec"><span class="sec-title">Task file</span><span class="sec-line"></span></div>`);
    // task.html is renderMarkdown output -- the trusted renderer, same as the
    // plan section. Every other string on this page is esc()'d.
    parts.push(`<div class="prose">${task.html}</div>`);
  } else {
    parts.push(`<div class="stops">(no task context resolved for this review)</div>`);
  }
  return shell("Task", title, parts.join("\n"));
}

function planPage(data: ReviewPageData): string {
  const intent = data.intent;
  const parts: string[] = [];
  if (intent && intent.planSection) {
    parts.push(
      `<div class="meta-row">${chip("sig", "From plan")}<span>${esc(intent.planSection.heading)} · ${esc(intent.planSection.planPath)}</span></div>`,
    );
    // intent.planSection.html is renderMarkdown output -- the trusted renderer.
    parts.push(`<div class="prose">${intent.planSection.html}</div>`);
  } else {
    parts.push(`<div class="stops">(no plan section resolved for this task)</div>`);
  }
  return shell("Plan", "Plan section", parts.join("\n"));
}

function specPage(data: ReviewPageData, cwd: string): string {
  const intent = data.intent;
  const parts: string[] = [];
  if (data.banner) parts.push(`<div class="banner">${esc(data.banner)}</div>`);
  const specs = (intent ? intent.chain : []).filter((n) => n.kind === "spec");
  if (specs.length === 0) {
    parts.push(`<div class="stops">(no spec linked in the intent chain for this task)</div>`);
  }
  for (const spec of specs) {
    const rendered = renderRepoDoc(cwd, spec.path);
    const body =
      rendered.status === "ok"
        ? `<div class="prose">${rendered.html}</div>`
        : `<div class="stops">(${esc(rendered.error)})</div>`;
    parts.push(
      `<div class="spec-card">
         <div class="meta-row">${chip("sig", "spec")}<span class="id">${esc(spec.id)}</span><span>${esc(spec.path)}</span></div>
${body}
       </div>`,
    );
  }
  return shell("Spec", "Specifications", parts.join("\n"));
}

function verifyPage(data: ReviewPageData): string {
  const g = data.guide;
  const parts: string[] = [];
  if (data.banner) parts.push(`<div class="banner">${esc(data.banner)}</div>`);
  if (!g) {
    parts.push(`<div class="stops">(no guidance recorded for this task)</div>`);
    return shell("Verify", "Verifications &amp; validation state", parts.join("\n"));
  }
  if (g.confidence) {
    parts.push(`<div class="sec"><span class="sec-title">Confidence</span><span class="sec-line"></span></div>`);
    parts.push(chainCard(`<div class="meta-row">${chip("warn", `Confidence: ${g.confidence}`)}</div>`));
  }
  if (Array.isArray(g.validation) && g.validation.length) {
    const ok = g.validation.filter((v) => v.ok === true).length;
    parts.push(`<div class="sec"><span class="sec-title">Validation</span><span class="sec-line"></span></div>`);
    parts.push(`<div class="meta-row">${chip(ok === g.validation.length ? "ok" : "warn", `${ok}/${g.validation.length} gates pass`)}</div>`);
    const gates = g.validation
      .map((v) => {
        const mark = v.ok === false ? " ✗" : v.ok ? " ✓" : "";
        const cls = v.ok === false ? "bad" : v.ok ? "ok" : "dim";
        return `<span class="gate ${cls}">${esc((v.gate + " " + (v.summary || "") + mark).trim())}</span>`;
      })
      .join("");
    parts.push(`<div class="gate-row">${gates}</div>`);
  }
  if (Array.isArray(g.verify) && g.verify.length) {
    parts.push(`<div class="sec"><span class="sec-title">Verify before approving</span><span class="sec-line"></span></div>`);
    const items = g.verify
      .map((v, i) => {
        const where = v.file ? ` <span class="where">${esc(v.file)}${v.line ? ":" + esc(String(v.line)) : ""}</span>` : "";
        return `<div class="verify-item"><span class="idx">${i + 1}</span><span>${esc(v.item)}</span>${where}</div>`;
      })
      .join("");
    parts.push(items);
  }
  if (Array.isArray(g.addressed) && g.addressed.length) {
    parts.push(`<div class="sec"><span class="sec-title">Already addressed</span><span class="sec-line"></span></div>`);
    parts.push(chainCard(`<div class="resolved">${esc(g.addressed.join("; "))}</div>`));
  }
  return shell("Verify", "Verifications &amp; validation state", parts.join("\n"));
}

function chainCard(inner: string): string {
  return `<div style="margin:6px 0">${inner}</div>`;
}

/** Render a repo-relative markdown file (spec chain nodes carry repo-relative
 * paths). Returns `{status:"ok", html}` or `{status:"err", error}`. The path
 * must stay inside the repo: the navigator resolved it, but the server never
 * trusts a path without containment. */
function renderRepoDoc(cwd: string, relPath: string): { status: "ok"; html: string } | { status: "err"; error: string } {
  const root = resolve(cwd);
  const target = resolve(root, relPath);
  if (target !== root && !target.startsWith(root + sep)) {
    return { status: "err", error: `path escapes the repo root: ${relPath}` };
  }
  try {
    return { status: "ok", html: renderMarkdown(stripDocFrontmatter(readFileSync(target, "utf-8"))).html };
  } catch {
    return { status: "err", error: `could not read ${relPath}` };
  }
}

export function renderReferencePage(kind: ReferenceKind, data: ReviewPageData, cwd: string): string {
  switch (kind) {
    case "task":
      return taskPage(data);
    case "plan":
      return planPage(data);
    case "spec":
      return specPage(data, cwd);
    case "verify":
      return verifyPage(data);
  }
}