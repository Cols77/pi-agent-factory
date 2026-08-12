// SP-B Task 5 split — system shell (HTML + CSS + inline-script assembly).
//
// This module owns the `/system` HTML template and its inline CSS. It renders
// the exact same page as before the split, with the full client script embedded
// inline so the DOM tests (which parse this HTML and execute its inline <script>
// via jsdom `runScripts: "dangerously"`) keep passing unchanged.
//
// The client script is split *for maintenance* across two other modules:
//   - system-renderers.ts  : the pure per-tab DOM renderers
//   - system-bootstrap.ts  : the client controller (systemBootstrap)
// The shell embeds them into one flat IIFE via `Function.prototype.toString()`
// so they share a single scope (renderers reference `clear` and each other;
// bootstrap references the renderers). "Python computes, this only renders"
// is unchanged.

import { systemBootstrap } from './system-bootstrap.js';
import {
  badge,
  citationLine,
  freshnessBadge,
  invertTraceForScope,
  renderBrief,
  renderChangedFiles,
  renderClaim,
  renderCommitRange,
  renderDegradedBanner,
  renderGuide,
  renderGuideFallback,
  renderImplementationSummary,
  renderMatrix,
  renderMatrixRow,
  renderNotApplicable,
  renderReverse,
  renderReversePath,
  renderRunDetail,
  renderStory,
  renderStoryRun,
  renderTimeline,
  renderTimelineEvent,
  renderTrace,
} from './system-renderers.js';

function clientSource(): string {
  // `clear` is shared by the renderers and the bootstrap, so it is defined at
  // the IIFE scope (not inside either embedded module).
  const clear = `
  function clear(el) {
    el.innerHTML = '';
  }`;
  const renderers = [
    badge,
    freshnessBadge,
    citationLine,
    renderImplementationSummary,
    renderClaim,
    renderBrief,
    renderMatrixRow,
    renderMatrix,
    renderTimelineEvent,
    renderTimeline,
    renderGuide,
    renderGuideFallback,
    renderDegradedBanner,
    renderCommitRange,
    renderChangedFiles,
    renderRunDetail,
    renderStoryRun,
    renderStory,
    renderReversePath,
    renderReverse,
    renderNotApplicable,
    invertTraceForScope,
    renderTrace,
  ]
    .map((fn) => fn.toString())
    .join('\n');
  return `<script>
(async () => {
${clear}
${renderers}
${systemBootstrap.toString()}
await systemBootstrap();
})();
</script>`;
}

export function renderSystemPageHtml(): string {
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>System Navigator</title>
<style>
  :root {
    color-scheme: light dark;
    --line: color-mix(in srgb, currentColor 18%, transparent);
    --sunk: color-mix(in srgb, currentColor 6%, transparent);
    --hover: color-mix(in srgb, currentColor 12%, transparent);
    --fresh: #3fa14a; --stale: #c8871a; --degraded: #d24b3f; --na: #8a8a8a;
  }
  * { box-sizing: border-box; }
  body { font: 13px/1.55 ui-sans-serif, system-ui, sans-serif; margin: 0; height: 100vh; overflow: hidden; }
  header { padding: 12px 20px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 15px; margin: 0; }
  #banner { padding: 8px 20px; background: color-mix(in srgb, var(--degraded) 15%, transparent); }
  #banner:empty { display: none; }
  #layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); height: calc(100vh - 60px); }
  #picker { border-right: 1px solid var(--line); overflow: auto; padding: 10px 14px 24px; }
  #picker h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; opacity: .6; margin: 0 0 6px; }
  #scopeFilter { width: 100%; padding: 6px 8px; font: inherit; border: 1px solid var(--line); border-radius: 4px; background: Canvas; color: inherit; margin-bottom: 6px; }
  .scope-group-title { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; opacity: .6; margin: 10px 0 2px; }
  .scope-row { display: flex; align-items: center; }
  .scope-item { display: block; flex: 1; padding: 3px 8px; border: none; border-radius: 3px; margin: 1px 0; text-decoration: none; color: inherit; font: inherit; text-align: left; width: 100%; }
  .scope-item:hover, .scope-item:focus-visible { background: var(--hover); outline: 2px solid currentColor; outline-offset: 1px; }
  .scope-kind { font-size: 10px; text-transform: uppercase; opacity: .55; margin-right: 6px; }
  #scopeToggle { display: none; }
  @media (max-width: 760px) {
    body.focus #scopeList, body.focus .scope-group-title, body.focus #scopeFilter, body.focus #picker h2 { display: none; }
    #scopeToggle { display: inline-block; font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--sunk); cursor: pointer; }
    body.focus #scopeToggle { display: inline-block; }
  }
  .scope-meta { display: flex; gap: 10px; align-items: center; margin: 6px 0 2px; font-size: 11px; opacity: .8; }
  #refresh { font: inherit; padding: 2px 8px; border: 1px solid var(--line); border-radius: 3px; background: var(--sunk); cursor: pointer; }
  #content { overflow: auto; padding: 8px 24px 48px; }
  a:focus-visible, button:focus-visible, input:focus-visible, .tab:focus-visible, .scope-item:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
  #tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--line); margin-bottom: 12px; position: sticky; top: 0; z-index: 3; background: Canvas; }
  .tab { font: inherit; padding: 6px 12px; border: none; background: none; cursor: pointer; border-bottom: 2px solid transparent; color: inherit; }
  .tab[aria-selected="true"] { border-bottom-color: currentColor; font-weight: 600; }
  .panel[hidden] { display: none; }
  .claim, .matrix-row, .timeline-event { border: 1px solid var(--line); border-radius: 4px; padding: 8px 10px; margin: 8px 0; }
  .claim-head, .row-head, .event-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .badge { font-size: 10px; text-transform: uppercase; letter-spacing: .04em; border: 1px solid var(--line); border-radius: 3px; padding: 1px 5px; }
  .freshness { font-size: 11px; border-radius: 3px; padding: 1px 5px; border: 1px solid currentColor; }
  .freshness-fresh { color: var(--fresh); }
  .freshness-stale { color: var(--stale); }
  .freshness-degraded { color: var(--degraded); }
  .freshness-n-a { color: var(--na); }
  .claim-text { margin-top: 4px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .span { white-space: pre-wrap; overflow-wrap: anywhere; }
  .citation, .evidence-item { overflow-wrap: anywhere; }
  .citations, .spans, .evidence { margin-top: 4px; font-size: 11px; opacity: .8; }
  .citation, .span, .evidence-item { padding: 1px 0; }
  .degraded-banner { border: 1px solid var(--degraded); color: var(--degraded); border-radius: 4px; padding: 6px 10px; margin: 8px 0; }
  .empty { opacity: .7; }
  .run, .path { border: 1px solid var(--line); border-radius: 4px; padding: 8px 10px; margin: 8px 0; }
  .run-head, .story-task { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .source-manifest { color: var(--fresh); }
  .source-session { color: var(--stale); }
  .commit-range, .stops-at { margin-top: 4px; font-size: 11px; opacity: .8; overflow-wrap: anywhere; }
  .changed-files { margin-top: 4px; font-size: 11px; }
  .changed-file { padding: 1px 0; overflow-wrap: anywhere; }
  .implementation-summary { margin-top: 6px; font-size: 11px; opacity: .85; }
  .summary-line { padding: 1px 0; }
  .validation-passed { color: var(--fresh); }
  .validation-stale { color: var(--stale); }
  .validation-failed { color: var(--degraded); }
  .validation-none { color: var(--na); }
  .path-chain { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
  .path-chain .arrow { opacity: .6; }
  .requirements { margin-top: 8px; font-size: 12px; }
  .requirement { padding: 1px 0; }
  .trace-sr, .trace-task { border: 1px solid var(--line); border-radius: 4px; padding: 8px 10px; margin: 8px 0; }
  .trace-chain { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
  .trace-hop { padding: 1px 0; overflow-wrap: anywhere; }
  .trace-arrow { opacity: .6; }
  .trace-upstream { font-size: 11px; opacity: .8; margin-top: 2px; }
  /* SP-B: the health landing + feature-first sidebar (Tasks 6-7). */
  #healthSummary { margin: 4px 0 14px; }
  .health-line { padding: 1px 0; }
  .bundle-group { margin: 10px 0 2px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; opacity: .6; }
  .readiness-counts { font-size: 11px; opacity: .8; margin-left: 6px; }
</style></head>
<body>
  <nav aria-label="System navigator"><header><h1>System Navigator</h1></header></nav>
  <div id="banner" role="status"></div>
  <div id="layout">
    <aside id="picker">
      <h2>Declared scopes</h2>
      <button id="scopeToggle" aria-expanded="false">All scopes ▾</button>
      <nav aria-label="Scopes">
        <input id="scopeFilter" type="search" placeholder="Filter scopes…" aria-label="Filter scopes" />
        <div id="scopeList"></div>
        <div id="scopeErrors"></div>
      </nav>
    </aside>
    <section id="content" hidden>
      <div id="healthSummary"></div>
      <h2 id="scopeHeader"></h2>
      <div id="loading" role="status" hidden>Loading…</div>
      <div class="scope-meta"><button id="refresh">Refresh</button> <span id="loadedAt"></span></div>
      <nav aria-label="System navigator"><div id="tabs" role="tablist">
        <button id="tabBrief" class="tab" role="tab" aria-selected="true" aria-controls="panelBrief" aria-label="Brief">Brief</button>
        <button id="tabMatrix" class="tab" role="tab" aria-selected="false" aria-controls="panelMatrix" aria-label="Matrix">Matrix</button>
        <button id="tabTimeline" class="tab" role="tab" aria-selected="false" aria-controls="panelTimeline" aria-label="Timeline">Timeline</button>
        <button id="tabGuide" class="tab" role="tab" aria-selected="false" aria-controls="panelGuide" aria-label="Guide">Guide</button>
        <button id="tabStory" class="tab" role="tab" aria-selected="false" aria-controls="panelStory" aria-label="Story">Story</button>
        <button id="tabReverse" class="tab" role="tab" aria-selected="false" aria-controls="panelReverse" aria-label="Reverse">Reverse</button>
        <button id="tabTrace" class="tab" role="tab" aria-selected="false" aria-controls="panelTrace" aria-label="Trace">Trace</button>
      </div></nav>
      <div id="panelBrief" class="panel"></div>
      <div id="panelMatrix" class="panel" hidden></div>
      <div id="panelTimeline" class="panel" hidden></div>
      <div id="panelGuide" class="panel" hidden></div>
      <div id="panelStory" class="panel" hidden></div>
      <div id="panelReverse" class="panel" hidden></div>
      <div id="panelTrace" class="panel" hidden></div>
    </section>
  </div>
${clientSource()}
</body></html>`;
}
