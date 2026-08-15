// System Navigator shell: semantic HTML, visual system, and inline client assembly.

import { systemBootstrap } from './system-bootstrap.js';
import {
  boundedList,
  closeOpenCard,
  definitionCardFields,
  definitionTrigger,
  ensureCardController,
  glossFor,
  humaniseGroup,
  infoCard,
  nextStepBlock,
  refCardFields,
  refChip,
  renderVocabularyPanel,
  resolveLabel,
  vocabularyBadgeFor,
} from './system-comprehension.js';
import { REMEDIATION_DATA, VOCABULARY_DATA } from './system-vocabulary-data.js';
import {
  badge,
  badgeSpan,
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
  withGloss,
} from './system-renderers.js';

function clientSource(): string {
  const preamble = `
  function clear(el) {
    el.innerHTML = '';
  }
  var LABELS = {};
  var ALIASES = {};
  var LABELS_LOADED = true;
  var VOCABULARY = ${JSON.stringify(VOCABULARY_DATA)};
  var REMEDIATION = ${JSON.stringify(REMEDIATION_DATA)};
  function setLabels(payload) {
    LABELS = (payload && payload.labels) || {};
    ALIASES = (payload && payload.aliases) || {};
    LABELS_LOADED = !!payload;
  }`;
  const renderers = [
    badgeSpan,
    resolveLabel,
    refChip,
    boundedList,
    nextStepBlock,
    infoCard,
    refCardFields,
    ensureCardController,
    closeOpenCard,
    glossFor,
    definitionTrigger,
    withGloss,
    vocabularyBadgeFor,
    definitionCardFields,
    humaniseGroup,
    renderVocabularyPanel,
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
${preamble}
${renderers}
${systemBootstrap.toString()}
await systemBootstrap();
})();
</script>`;
}

export function renderSystemPageHtml(): string {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>System Navigator</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #071015;
    --bg-deep: #04090c;
    --surface: #0d1a20;
    --surface-raised: #12242c;
    --surface-soft: #102028;
    --line: #26404a;
    --line-strong: #3a606c;
    --text: #e7f2f5;
    --text-muted: #91a8b0;
    --text-dim: #698089;
    --signal: #65d9ff;
    --signal-soft: rgba(101, 217, 255, .12);
    --fresh: #72e6a6;
    --stale: #ffc857;
    --degraded: #ff6b6b;
    --na: #91a8b0;
    --font-display: "Bahnschrift", "Aptos Display", "Segoe UI Variable Display", sans-serif;
    --font-body: "Aptos", "Segoe UI Variable Text", sans-serif;
    --font-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
    --radius-sm: 6px;
    --radius-md: 10px;
    --shadow-raised: 0 18px 50px rgba(0, 0, 0, .28);
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  html { min-height: 100%; background: var(--bg-deep); }
  body {
    margin: 0;
    height: 100vh;
    height: 100dvh;
    min-height: 0;
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    overflow: hidden;
    color: var(--text);
    background:
      radial-gradient(circle at 78% -15%, rgba(101, 217, 255, .12), transparent 36rem),
      linear-gradient(rgba(101, 217, 255, .025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(101, 217, 255, .025) 1px, transparent 1px),
      var(--bg);
    background-size: auto, 32px 32px, 32px 32px, auto;
    font: 14px/1.62 var(--font-body);
  }
  .app-header {
    position: relative;
    min-height: 82px;
    padding: 13px 24px 14px;
    border-bottom: 1px solid var(--line);
    background: rgba(4, 9, 12, .84);
    backdrop-filter: blur(18px);
  }
  #vocabularyToggle { position: absolute; top: 14px; right: 24px; }
  .app-header h1 {
    margin: 1px 0 0;
    font: 650 clamp(20px, 2vw, 27px)/1.1 var(--font-display);
    letter-spacing: -.02em;
  }
  .app-header p { margin: 4px 0 0; color: var(--text-muted); max-width: 68ch; }
  .eyebrow, .section-heading > span {
    color: var(--signal);
    font: 650 12px/1.3 var(--font-mono);
    letter-spacing: .14em;
    text-transform: uppercase;
  }
  #banner {
    padding: 8px 24px;
    border-bottom: 1px solid rgba(255, 107, 107, .5);
    background: rgba(255, 107, 107, .1);
    color: #ffd3d3;
  }
  #banner:empty { display: none; }
  #layout {
    display: grid;
    grid-template-columns: 320px minmax(0, 1fr);
    min-height: 0;
    min-width: 0;
    overflow: hidden;
  }
  #picker {
    min-width: 0;
    min-height: 0;
    border-right: 1px solid var(--line);
    overflow: auto;
    padding: 18px 16px 30px;
    background: rgba(7, 16, 21, .88);
  }
  #picker h2 {
    margin: 0 0 10px;
    color: var(--text-muted);
    font: 600 13px/1.3 var(--font-display);
    letter-spacing: .04em;
  }
  #scopeFilter {
    width: 100%;
    min-width: 0;
    padding: 9px 10px;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text);
    font: inherit;
  }
  #scopeFilter::placeholder { color: var(--text-dim); }
  .search-row { display: flex; gap: 7px; margin-bottom: 10px; }
  .search-row #scopeFilter { flex: 1; margin-bottom: 0; }
  button { color: inherit; }
  #searchGo, #refresh, #scopeToggle, .secondary-action {
    padding: 9px 12px;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-raised);
    cursor: pointer;
    font: 650 12px/1 var(--font-body);
  }
  .scope-group-title {
    margin: 14px 0 5px;
    color: var(--text-muted);
    font: 650 12px/1.3 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: .09em;
  }
  .scope-group-title[role="button"], button.scope-group-title {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    padding: 3px 0;
    border: 0;
    background: transparent;
    cursor: pointer;
    user-select: none;
  }
  .scope-row { display: flex; align-items: center; }
  .scope-item {
    display: block;
    flex: 1;
    min-width: 0;
    width: 100%;
    margin: 1px 0;
    padding: 7px 9px;
    border-left: 2px solid transparent;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    color: var(--text-muted);
    font: 13px/1.45 var(--font-body);
    text-align: left;
    text-decoration: none;
    overflow-wrap: anywhere;
  }
  .scope-item:hover { color: var(--text); background: var(--surface-soft); border-left-color: var(--line-strong); }
  .scope-item.is-active, .scope-item[aria-current="page"] { color: var(--text); background: var(--signal-soft); border-left-color: var(--signal); }
  .scope-kind { margin-right: 7px; color: var(--text-dim); font: 600 12px/1.2 var(--font-mono); text-transform: uppercase; }
  #scopeToggle { display: none; }
  #content { min-width: 0; min-height: 0; overflow: auto; padding: 34px clamp(24px, 4vw, 64px) 64px; }
  #landingPanel, #scopeWorkspace { width: min(100%, 1040px); margin: 0 auto; }
  .landing-intro { max-width: 72ch; padding: 8px 0 22px; }
  .landing-intro h2, .scope-heading h2 {
    margin: 6px 0 7px;
    font: 650 clamp(28px, 4vw, 46px)/1.04 var(--font-display);
    letter-spacing: -.035em;
  }
  .landing-intro p { margin: 0; max-width: 64ch; color: var(--text-muted); font-size: 16px; }
  .scope-heading { padding-bottom: 14px; border-bottom: 1px solid var(--line); }
  #scopeRef { color: var(--text-muted); font: 12px/1.5 var(--font-mono); overflow-wrap: anywhere; }
  .scope-meta { display: flex; align-items: center; gap: 11px; margin: 12px 0 18px; color: var(--text-muted); font: 12px/1.4 var(--font-mono); }
  .loading-state { margin: 12px 0; padding: 12px 14px; border-left: 3px solid var(--signal); background: var(--signal-soft); }
  .feature-directory { margin-top: 34px; }
  .section-heading h3 { margin: 5px 0 12px; font: 650 21px/1.2 var(--font-display); }
  a:focus-visible, button:focus-visible, input:focus-visible, .tab:focus-visible, .scope-item:focus-visible, summary:focus-visible {
    outline: 2px solid var(--signal);
    outline-offset: 3px;
  }
  #tabs {
    display: flex;
    gap: 2px;
    position: sticky;
    top: 0;
    z-index: 3;
    margin: 0 0 20px;
    border-bottom: 1px solid var(--line);
    background: rgba(7, 16, 21, .96);
  }
  .tab {
    flex: 0 0 auto;
    padding: 13px 14px 12px;
    border: none;
    border-bottom: 2px solid transparent;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
    font: 650 13px/1 var(--font-body);
  }
  .tab:hover { color: var(--text); background: var(--surface-soft); }
  .tab[aria-selected="true"] { border-bottom-color: var(--signal); color: var(--signal); }
  .panel[hidden] { display: none; }
  .panel { width: min(100%, 1040px); }
  .claim, .matrix-row, .timeline-event, .run, .path, .trace-sr, .trace-task {
    margin: 10px 0;
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-left: 3px solid var(--line-strong);
    border-radius: var(--radius-sm);
    background: rgba(13, 26, 32, .74);
  }
  .claim-head, .row-head, .event-head, .run-head, .story-task { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .badge { padding: 3px 6px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); font: 650 12px/1.3 var(--font-mono); letter-spacing: .07em; text-transform: uppercase; }
  .freshness { padding: 3px 6px; border: 1px solid currentColor; border-radius: var(--radius-sm); font: 650 12px/1.3 var(--font-mono); }
  .freshness-fresh, .source-manifest, .validation-passed { color: var(--fresh); }
  .freshness-stale, .source-session, .validation-stale { color: var(--stale); }
  .freshness-degraded, .validation-failed { color: var(--degraded); }
  .freshness-n-a, .validation-none { color: var(--na); }
  .claim-text { max-width: 90ch; margin-top: 9px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .span { white-space: pre-wrap; overflow-wrap: anywhere; }
  .citation, .evidence-item, .changed-file, .trace-hop { overflow-wrap: anywhere; }
  .citations, .spans, .evidence { margin-top: 7px; color: var(--text-muted); font: 12px/1.6 var(--font-mono); }
  .citation, .span, .evidence-item, .changed-file, .summary-line { padding: 2px 0; }
  .evidence-disclosure { margin-top: 11px; border-top: 1px solid var(--line); padding-top: 8px; }
  .evidence-disclosure summary { width: fit-content; color: var(--signal); cursor: pointer; font: 650 12px/1.5 var(--font-mono); }
  .evidence-disclosure[open] summary { margin-bottom: 5px; }
  .degraded-banner { margin: 10px 0; padding: 10px 14px; border: 1px solid var(--degraded); border-left-width: 3px; border-radius: var(--radius-sm); background: rgba(255, 107, 107, .08); color: #ffd3d3; }
  .empty { color: var(--text-muted); }
  .commit-range, .stops-at { margin-top: 6px; color: var(--text-muted); font: 12px/1.55 var(--font-mono); overflow-wrap: anywhere; }
  .changed-files { margin-top: 7px; font: 12px/1.55 var(--font-mono); }
  .implementation-summary { margin-top: 9px; color: var(--text-muted); font-size: 13px; }
  .path-chain, .trace-chain { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
  .path-chain .arrow, .trace-arrow { color: var(--text-dim); }
  .requirements { margin-top: 8px; font-size: 13px; }
  .requirement { padding: 1px 0; }
  .trace-upstream { margin-top: 3px; color: var(--text-muted); font-size: 12px; }
  .traversal-path { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; margin: 6px 0 20px; counter-reset: trace-step; }
  .trace-spine-step { position: relative; min-width: 0; padding: 12px 14px 12px 37px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: rgba(13, 26, 32, .62); counter-increment: trace-step; }
  .trace-spine-step:first-child { border-left: 1px solid var(--line); border-radius: var(--radius-sm) 0 0 var(--radius-sm); }
  .trace-spine-step:last-child { border-right: 1px solid var(--line); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
  .trace-spine-step::before { content: counter(trace-step); position: absolute; top: 14px; left: 13px; width: 20px; height: 20px; border: 1px solid var(--signal); border-radius: 50%; color: var(--signal); font: 650 12px/18px var(--font-mono); text-align: center; }
  .trace-spine-step:not(:last-child)::after { content: ""; position: absolute; z-index: 1; top: 21px; right: -5px; width: 9px; height: 9px; border-top: 1px solid var(--signal); border-right: 1px solid var(--signal); background: var(--surface); transform: rotate(45deg); }
  .trace-spine-label { color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .trace-spine-value { margin-top: 4px; color: var(--text); font: 12px/1.55 var(--font-mono); overflow-wrap: anywhere; }
  .matrix-row { display: grid; grid-template-columns: minmax(160px, .7fr) minmax(0, 1.3fr); gap: 8px 18px; }
  .matrix-row .row-head { min-width: 0; align-content: start; }
  .matrix-subject { width: 100%; color: var(--text); font: 650 13px/1.45 var(--font-mono); overflow-wrap: anywhere; }
  .matrix-status { display: flex; gap: 6px; flex-wrap: wrap; }
  .matrix-summary { margin-top: 0; }
  .matrix-row .evidence { grid-column: 1 / -1; }
  #healthSummary { margin: 4px 0 16px; }
  .health-overall { margin: 4px 0 12px; padding: 18px 20px; border: 1px solid var(--line); border-left: 3px solid var(--signal); border-radius: var(--radius-md); background: var(--surface); color: var(--text); font: 650 clamp(18px, 2.4vw, 27px)/1.2 var(--font-display); }
  .health-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 7px; }
  .health-metric { display: flex; flex-direction: column; min-width: 0; padding: 10px 11px; border-top: 1px solid var(--line); background: rgba(13, 26, 32, .5); }
  .health-metric-label { color: var(--text-muted); font-size: 12px; overflow-wrap: anywhere; }
  .health-metric-raw { margin-top: 1px; color: var(--text-dim); font: 12px/1.4 var(--font-mono); overflow-wrap: anywhere; }
  .health-metric strong { margin-top: 2px; color: var(--text); font: 650 13px/1.4 var(--font-mono); }
  .health-line { padding: 2px 0; }
  .bundle-group { margin: 14px 0 4px; color: var(--text-muted); font: 650 12px/1.3 var(--font-mono); letter-spacing: .08em; text-transform: uppercase; }
  .readiness-counts { margin-left: 6px; color: var(--text-muted); font: 12px/1.4 var(--font-mono); }
  .feature-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 18px; margin: 7px 0; padding: 13px 15px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .72); color: var(--text); text-decoration: none; }
  .feature-row:hover { border-color: var(--line-strong); background: var(--surface-raised); }
  .feature-row > strong { min-width: 0; font: 650 16px/1.35 var(--font-display); overflow-wrap: anywhere; }
  .feature-readiness { justify-self: end; color: var(--stale); font: 650 12px/1.3 var(--font-mono); letter-spacing: .08em; text-transform: uppercase; }
  .feature-members { color: var(--text-muted); font-size: 12px; }
  .readiness-ready { border-left-color: var(--fresh); }
  .readiness-strong { border-left-color: var(--fresh); }
  .readiness-medium { border-left-color: var(--signal); }
  .readiness-weak { border-left-color: var(--stale); }
  .readiness-blocked { border-left-color: var(--degraded); }
  .readiness-missing { border-left-color: var(--na); }
  .readiness-strong .feature-readiness { color: var(--fresh); }
  .readiness-medium .feature-readiness { color: var(--signal); }
  @media (max-width: 760px) {
    .app-header { min-height: 94px; padding: 12px 16px 13px; }
    .app-header p { font-size: 13px; }
    #vocabularyToggle { position: static; margin-top: 10px; }
    #layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
    #picker { max-height: 42vh; padding: 10px 16px; border-right: 0; border-bottom: 1px solid var(--line); }
    body.focus #picker nav, body.focus #picker h2 { display: none; }
    body.focus.picker-open #picker nav, body.focus.picker-open #picker h2 { display: block; }
    body.focus:not(.picker-open) #picker { max-height: none; }
    body.focus #scopeToggle { display: inline-flex; }
    #content { min-width: 0; padding: 18px 16px 44px; }
    #tabs { overflow-x: auto; scrollbar-width: thin; }
    .matrix-row, .feature-row { grid-template-columns: minmax(0, 1fr); }
    .traversal-path { grid-template-columns: minmax(0, 1fr); }
    .trace-spine-step { border: 1px solid var(--line); border-bottom: 0; border-radius: 0; }
    .trace-spine-step:first-child { border-radius: var(--radius-sm) var(--radius-sm) 0 0; }
    .trace-spine-step:last-child { border-bottom: 1px solid var(--line); border-radius: 0 0 var(--radius-sm) var(--radius-sm); }
    .trace-spine-step:not(:last-child)::after { top: auto; right: auto; bottom: -5px; left: 17px; transform: rotate(135deg); }
    .health-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .feature-readiness { justify-self: start; }
    .landing-intro h2, .scope-heading h2 { font-size: 30px; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .01ms !important; }
  }
  .ref-chip { display: inline-flex; align-items: baseline; gap: 6px; max-width: 100%; }
  .ref-chip .chip-id { padding: 0 3px; border-radius: 3px; background: var(--signal-soft); font: 12px/1.5 var(--font-mono); }
  .ref-chip .chip-sep { color: var(--text-dim); }
  .ref-chip .chip-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ref-chip:hover .chip-id, .ref-chip:focus-visible .chip-id { box-shadow: inset 0 -1px 0 var(--signal); }
  .gloss { margin-top: 2px; color: var(--text-muted); font-size: 12px; line-height: 1.5; }
  .info-trigger { padding: 0 2px; border: 0; background: none; color: var(--signal); font-size: 12px; cursor: pointer; }
  .badge-wrap { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; max-width: 100%; min-width: 0; }
  .badge-wrap .gloss { flex-basis: 100%; }
  .info-card { position: fixed; z-index: 40; max-width: 34ch; padding: 12px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-md); background: var(--surface-raised); box-shadow: var(--shadow-raised); }
  .presence-rail { border-left: 3px solid var(--line-strong); padding-left: 12px; }
  .presence-rail.is-absent { border-left-style: dashed; border-left-color: var(--stale); }
  .presence-rail.is-failure { border-left-style: solid; border-left-color: var(--degraded); }
  .next-step { margin: 12px 0; }
  .next-step p { max-width: 64ch; margin: 6px 0 0; color: var(--text); font: 14px/1.55 var(--font-body); }
  .next-step .command { display: flex; align-items: center; gap: 10px; margin-top: 8px; padding: 9px 11px; border-radius: var(--radius-sm); background: var(--surface-soft); font: 13px/1.5 var(--font-mono); }
  .next-step .prompt { color: var(--signal); }
  .next-step .command-text { flex: 1; overflow-wrap: anywhere; }
  .next-step .command button { flex: 0 0 auto; }
  .scope-description { margin: 8px 0 0; max-width: 64ch; color: var(--text-muted); font: 14px/1.55 var(--font-body); }
  .scope-item .scope-label { display: block; }
  .scope-item .readiness-counts { display: block; margin-left: 0; margin-top: 2px; }
  .orientation-strip { display: flex; align-items: center; gap: 14px; margin: 0 0 20px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface-soft); color: var(--text-muted); }
  .orientation-strip p { margin: 0; max-width: 64ch; }
  .orientation-strip .secondary-action { flex: 0 0 auto; }
  .first-run-card { margin: 10px 0; padding: 16px 18px; border-radius: var(--radius-md); background: rgba(13, 26, 32, .6); }
  .first-run-heading { margin: 0 0 6px; color: var(--text); font: 650 18px/1.3 var(--font-display); }
  .bounded-list { display: grid; gap: 4px; }
  .ref-chip:focus-visible { outline: 2px solid var(--signal); outline-offset: 3px; border-radius: 3px; }
  .info-card { opacity: 0; animation: info-card-in .12s ease forwards; }
  @keyframes info-card-in { from { opacity: 0; } to { opacity: 1; } }
  .info-card-meta { color: var(--text-dim); font: 12px/1.4 var(--font-mono); text-transform: uppercase; letter-spacing: .04em; }
  .info-card-title { margin-top: 4px; color: var(--text); font: 650 14px/1.35 var(--font-display); }
  .info-card-description { margin-top: 6px; color: var(--text-muted); font-size: 13px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .info-card-empty { font-style: italic; }
  .info-card-from, .info-card-path { margin-top: 6px; font: 12px/1.5 var(--font-mono); overflow-wrap: anywhere; }
  .info-card-from { color: var(--text-dim); }
  .info-card-path { color: var(--text-muted); }
  .info-card-open { margin-top: 8px; }
  .info-card-open a { color: var(--signal); font: 650 12px/1.3 var(--font-mono); text-decoration: none; }
  .info-card-badge { margin-top: 0; }
  .info-card-definition { margin-top: 6px; color: var(--text-muted); font-size: 13px; line-height: 1.5; }
  .info-card-siblings, .info-card-computed-by { margin-top: 6px; font: 12px/1.5 var(--font-mono); color: var(--text-muted); overflow-wrap: anywhere; }
  #vocabularyPanel { width: min(100%, 1040px); margin: 0 auto; }
  .vocab-group { margin: 20px 0 8px; }
  .vocab-group-title {
    margin: 0 0 10px;
    color: var(--text-muted);
    font: 650 12px/1.3 var(--font-mono);
    letter-spacing: .09em;
    text-transform: uppercase;
  }
  .vocab-entries { display: grid; gap: 10px; }
  .vocab-entry {
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-left: 3px solid var(--line-strong);
    border-radius: var(--radius-sm);
    background: rgba(13, 26, 32, .74);
  }
  .vocab-definition { margin-top: 8px; color: var(--text-muted); font-size: 13px; line-height: 1.5; }
  .vocab-siblings, .vocab-computed-by { margin-top: 6px; font: 12px/1.5 var(--font-mono); color: var(--text-muted); overflow-wrap: anywhere; }
  @media (min-width: 1200px) {
    .vocab-entries { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  .info-card-open a:hover, .info-card-open a:focus-visible { text-decoration: underline; }
  @media (min-width: 1200px) {
    .workspace-split { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; }
    #scopeWorkspace.workspace-split { width: min(100%, 1380px); }
    .workspace-split > .panel { width: 100%; }
    .context-rail { position: sticky; top: 0; align-self: start; border-left: 1px solid var(--line); padding-left: 16px; background: var(--surface-soft); }
  }
</style></head>
<body>
  <header class="app-header">
    <div class="eyebrow">PIF / EVIDENCE</div>
    <h1>System Navigator</h1>
    <p>Trace what the system claims, what validates it, and where the evidence leads.</p>
    <button id="vocabularyToggle" class="secondary-action" type="button" aria-pressed="false">Vocabulary</button>
  </header>
  <div id="banner" role="status"></div>
  <div id="layout">
    <aside id="picker">
      <h2>Declared scopes</h2>
      <button id="scopeToggle" type="button" aria-expanded="false">Browse scopes</button>
      <nav aria-label="Scopes">
        <div class="search-row">
          <input id="scopeFilter" type="search" placeholder="Search bundles or a ref…" aria-label="Filter scopes" />
          <button id="searchGo" type="button">Go</button>
        </div>
        <div id="scopeList"></div>
        <div id="scopeErrors"></div>
      </nav>
    </aside>
    <main id="content" aria-busy="true">
      <section id="landingPanel" aria-labelledby="landingTitle">
        <div class="landing-intro">
          <div class="eyebrow">PROJECT EVIDENCE</div>
          <h2 id="landingTitle">See the system clearly.</h2>
          <p>Start with weak or unbundled features, then follow their evidence spine.</p>
        </div>
        <div id="orientationStrip" class="orientation-strip" hidden>
          <p>This page is the evidence behind what the system claims. Start with a weak or unbundled feature, open it, and follow its spine: requirement, tasks, decisions, files. Every term here is defined — select the ⓘ beside any badge.</p>
          <button id="orientationDismiss" class="secondary-action" type="button">Hide this</button>
        </div>
        <div id="healthStatus" class="loading-state" role="status">Reading project evidence…</div>
        <button id="retryHealth" class="secondary-action" type="button" hidden>Retry health scan</button>
        <div id="healthSummary"></div>
        <section class="feature-directory" aria-labelledby="featureDirectoryTitle">
          <div class="section-heading"><span>FEATURE DIRECTORY</span><h3 id="featureDirectoryTitle">Browse by readiness</h3></div>
          <div id="bundleList"></div>
        </section>
      </section>
      <section id="scopeWorkspace" hidden>
        <div class="scope-heading"><div id="scopeKind" class="eyebrow"></div><h2 id="scopeHeader"></h2><div id="scopeRef"></div></div>
        <div id="loading" role="status" hidden>Loading…</div>
        <div class="scope-meta"><button id="refresh" type="button">Refresh</button> <span id="loadedAt"></span></div>
        <nav aria-label="System navigator"><div id="tabs" role="tablist">
          <button id="tabBrief" class="tab" role="tab" tabindex="0" aria-selected="true" aria-controls="panelBrief" aria-label="Brief">Brief</button>
          <button id="tabMatrix" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelMatrix" aria-label="Matrix">Matrix</button>
          <button id="tabTimeline" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelTimeline" aria-label="Timeline">Timeline</button>
          <button id="tabGuide" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelGuide" aria-label="Guide">Guide</button>
          <button id="tabStory" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelStory" aria-label="Story">Story</button>
          <button id="tabReverse" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelReverse" aria-label="Reverse">Reverse</button>
          <button id="tabTrace" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelTrace" aria-label="Trace">Trace</button>
        </div></nav>
        <div id="panelBrief" class="panel" role="tabpanel" aria-labelledby="tabBrief"></div>
        <div id="panelMatrix" class="panel" role="tabpanel" aria-labelledby="tabMatrix" hidden></div>
        <div id="panelTimeline" class="panel" role="tabpanel" aria-labelledby="tabTimeline" hidden></div>
        <div id="panelGuide" class="panel" role="tabpanel" aria-labelledby="tabGuide" hidden></div>
        <div id="panelStory" class="panel" role="tabpanel" aria-labelledby="tabStory" hidden></div>
        <div id="panelReverse" class="panel" role="tabpanel" aria-labelledby="tabReverse" hidden></div>
        <div id="panelTrace" class="panel" role="tabpanel" aria-labelledby="tabTrace" hidden></div>
      </section>
      <section id="vocabularyPanel" aria-labelledby="vocabularyTitle" hidden>
        <div class="landing-intro">
          <div class="eyebrow">REFERENCE</div>
          <h2 id="vocabularyTitle">Vocabulary</h2>
          <p>Every term this system uses, with its real badge, definition, and where it's computed.</p>
        </div>
        <div id="vocabularyGroups"></div>
      </section>
    </main>
  </div>
${clientSource()}
</body></html>`;
}
