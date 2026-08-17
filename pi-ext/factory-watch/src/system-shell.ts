// System Navigator shell: semantic HTML, visual system, and inline client assembly.

import { systemBootstrap } from './system-bootstrap.js';
import {
  changeList,
  codeList,
  dossierSection,
  refList,
  renderFeature,
  taskCard,
  verificationRows,
  navLine,
} from './system-feature-view.js';
import { groupSection, nodeCard, renderVcycle, sideSection, stateClass, bandLabel, openRef } from './system-vcycle-view.js';
import { goalSection, refLine, renderGoal, goalStateClass, operatorSymbol, shortCommit } from './system-goal-view.js';
import { rawStateClass, goalStateClass as validationGoalStateClass, refLine as validationRefLine, renderValidation, validationSection } from './system-validation-view.js';
import { refLine as simRefLine, renderSim, resultClass, simSection } from './system-sim-view.js';
import { renderDiagram } from './system-diagram-view.js';
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
import { PANELS_DATA, REMEDIATION_DATA, VOCABULARY_DATA } from './system-vocabulary-data.js';
import {
  appendRunAbsenceNextSteps,
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
  renderTabError,
  openAnchor,
  renderReverse,
  renderReversePath,
  renderRunDetail,
  renderStory,
  renderStoryRun,
  renderTimeline,
  renderTimelineEvent,
  renderTrace,
  renderTraversalNotApplicable,
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
  var PANELS_DATA = ${JSON.stringify(PANELS_DATA)};
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
    appendRunAbsenceNextSteps,
    renderRunDetail,
    renderStoryRun,
    renderStory,
    renderReversePath,
    renderReverse,
    renderNotApplicable,
    renderTraversalNotApplicable,
    renderTabError,
    openAnchor,
    invertTraceForScope,
    renderTrace,
    dossierSection,
    refList,
    codeList,
    taskCard,
    verificationRows,
    changeList,
    renderFeature,
    navLine,
    stateClass,
    nodeCard,
    sideSection,
    groupSection,
    bandLabel,
    openRef,
    renderVcycle,
    goalSection,
    refLine,
    goalStateClass,
    operatorSymbol,
    shortCommit,
    renderGoal,
    validationSection,
    rawStateClass,
    validationGoalStateClass,
    validationRefLine,
    renderValidation,
    simSection,
    resultClass,
    simRefLine,
    renderSim,
    renderDiagram,
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
  .panel-orientation { margin: 8px 0 14px; max-width: 78ch; color: var(--text-muted); font-size: 13px; line-height: 1.6; }
  .panel-orientation .how-to-read { display: block; margin-top: 3px; color: var(--text-dim); }
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
  .traversal-path { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0; margin: 6px 0 20px; counter-reset: trace-step; border: 1px solid var(--line); border-radius: var(--radius-sm); }
  .trace-spine-step { position: relative; min-width: 0; padding: 12px 16px 14px 40px; counter-increment: trace-step; }
  .trace-spine-step + .trace-spine-step { border-top: 1px solid var(--line); }
  .trace-spine-step::before { content: counter(trace-step); position: absolute; top: 14px; left: 13px; width: 20px; height: 20px; border: 1px solid var(--signal); border-radius: 50%; color: var(--signal); font: 650 12px/18px var(--font-mono); text-align: center; }
  .trace-spine-head { display: flex; align-items: baseline; gap: 12px; }
  .trace-spine-label { flex: none; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .trace-spine-head::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--line); }
  .trace-spine-count { flex: none; color: var(--text-muted); font: 12px/1.3 var(--font-mono); }
  .trace-spine-value { min-width: 0; margin-top: 6px; color: var(--text); font: 13px/1.6 var(--font-body); overflow-wrap: anywhere; }
  .matrix-row { display: grid; grid-template-columns: minmax(160px, .7fr) minmax(0, 1.3fr); gap: 8px 18px; }
  .matrix-row .row-head { min-width: 0; align-content: start; }
  .matrix-subject { width: 100%; color: var(--text); font: 650 13px/1.45 var(--font-mono); overflow-wrap: anywhere; }
  .matrix-status { display: flex; gap: 6px; flex-wrap: wrap; }
  .matrix-summary { margin-top: 0; }
  .matrix-row .evidence { grid-column: 1 / -1; }
  #healthSummary { margin: 4px 0 16px; }
  .shape-sentence { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; margin: 0 0 10px; padding: 14px 16px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-soft); color: var(--text); font: 500 15px/1.55 var(--font-body); }
  .health-overall { margin: 4px 0 12px; padding: 18px 20px; border: 1px solid var(--line); border-left: 3px solid var(--signal); border-radius: var(--radius-md); background: var(--surface); color: var(--text); font: 650 clamp(18px, 2.4vw, 27px)/1.2 var(--font-display); }
  .health-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 7px; }
  .health-metric { display: flex; flex-direction: column; min-width: 0; padding: 10px 11px; border-top: 1px solid var(--line); background: rgba(13, 26, 32, .5); }
  .health-metric-label { color: var(--text-muted); font-size: 12px; overflow-wrap: anywhere; }
  .health-metric-raw { margin-top: 1px; color: var(--text-dim); font: 12px/1.4 var(--font-mono); overflow-wrap: anywhere; }
  .health-metric strong { margin-top: 2px; color: var(--text); font: 650 13px/1.4 var(--font-mono); }
  .health-metric-rule { margin-top: 6px; color: var(--text-muted); font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }
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
    .health-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .feature-readiness { justify-self: start; }
    .landing-intro h2, .scope-heading h2 { font-size: 30px; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .01ms !important; }
  }
  .ref-chip { display: inline-flex; align-items: baseline; gap: 6px; max-width: 100%; min-width: 0; }
  .ref-chip .chip-id { padding: 0 3px; border-radius: 3px; background: var(--signal-soft); font: 12px/1.5 var(--font-mono); }
  .ref-chip .chip-sep { color: var(--text-dim); }
  /* min-width: 0 MUST stay -- .ref-chip is inline-flex, and a flex child without
     it will not shrink below its content width, reintroducing the per-element
     overflow Increment 1 fixed and failing Task 9's containment gate. */
  .ref-chip .chip-title { min-width: 0; overflow-wrap: anywhere; }
  .matrix-subject .chip-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ref-chip:hover .chip-id, .ref-chip:focus-visible .chip-id { box-shadow: inset 0 -1px 0 var(--signal); }
  .gloss { margin-top: 2px; color: var(--text-muted); font-size: 12px; line-height: 1.5; }
  .info-trigger { padding: 0 2px; border: 0; background: none; color: var(--signal); font-size: 12px; cursor: pointer; }
  .badge-wrap { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; max-width: 100%; min-width: 0; }
  .badge-wrap .gloss { flex-basis: 100%; }
  .info-card { position: fixed; z-index: 40; max-width: 34ch; padding: 12px 14px; border: 1px solid var(--line-strong); border-radius: var(--radius-md); background: var(--surface-raised); box-shadow: var(--shadow-raised); }
  .presence-rail { border-left: 3px solid var(--line-strong); padding-left: 12px; }
  .presence-rail.is-absent { border-left-style: dashed; border-left-color: var(--stale); }
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
  .bounded-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; min-width: 0; }
  .ref-chip:focus-visible { outline: 2px solid var(--signal); outline-offset: 3px; border-radius: 3px; }
  .info-card { opacity: 0; animation: info-card-in .12s ease forwards; }
  @keyframes info-card-in { from { opacity: 0; } to { opacity: 1; } }
  .info-card-meta { color: var(--text-dim); font: 12px/1.4 var(--font-mono); text-transform: uppercase; letter-spacing: .04em; }
  .info-card-title { margin-top: 4px; color: var(--text); font: 650 14px/1.35 var(--font-display); }
  .info-card-description { margin-top: 6px; color: var(--text-muted); font-size: 13px; line-height: 1.5; max-height: min(60vh, 520px); overflow-y: auto; overscroll-behavior: contain; }
  .info-card-empty { font-style: italic; }
  .info-card-from, .info-card-path, .info-card-relations { margin-top: 6px; font: 12px/1.5 var(--font-mono); overflow-wrap: anywhere; }
  .info-card-from { color: var(--text-dim); }
  .info-card-path { color: var(--text-muted); }
  .info-card-relations { color: var(--text-muted); }
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
  .dossier-heading { margin-bottom: 16px; }
  .dossier-id { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .dossier-title { margin: 2px 0 0; font: 650 clamp(20px, 3vw, 30px)/1.1 var(--font-display); letter-spacing: -.02em; }
  .dossier-section { margin: 14px 0; padding: 14px 16px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .74); }
  .dossier-section-heading { margin: 0 0 9px; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .dossier-section-body { min-width: 0; }
  .dossier-intent { margin: 0; max-width: 72ch; font-size: 14px; line-height: 1.6; }
  .dossier-code-list, .dossier-run-list, .dossier-changes-list, .dossier-verification-list { display: grid; gap: 4px; }
  .dossier-code-file, .dossier-run, .dossier-change { overflow-wrap: anywhere; font: 12px/1.55 var(--font-mono); }
  .dossier-verification-row { display: flex; align-items: center; gap: 7px; font: 12px/1.55 var(--font-mono); }
  .dossier-verification-row.is-stale { border-left: 2px solid var(--stale); padding-left: 6px; }
  .dossier-task { margin: 8px 0; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .6); }
  .dossier-task-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .dossier-task-id { color: var(--signal); font: 650 12px/1.3 var(--font-mono); }
  .dossier-task-title { font: 650 14px/1.35 var(--font-display); }
  .task-status-text { color: var(--text-muted); font: 12px/1.3 var(--font-mono); }
  .dossier-run-list, .dossier-tasks-list { margin-top: 7px; }
  .vcycle-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
  .vcycle-anchor { display: flex; gap: 8px; align-items: center; }
  .vcycle-side-note { color: var(--text-muted); font-size: 12px; max-width: 46ch; }
  .vcycle-side { display: grid; gap: 8px; }
  @media (min-width: 1100px) {
    .vcycle-side.definition, .vcycle-side.verification { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .vcycle-side.verification { margin-top: 10px; }
  }
  .vcycle-band { padding: 10px 12px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .74); }
  .vcycle-band.is-missing { border-style: dashed; background: rgba(13, 26, 32, .4); }
  .vcycle-band-label { margin: 0 0 8px; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .07em; text-transform: uppercase; }
  .vcycle-band-nodes { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .vcycle-empty { color: var(--text-muted); font: 12px/1.5 var(--font-mono); font-style: italic; }
  .vcycle-node { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; padding-left: 7px; border-left: 3px solid transparent; }
  .vcycle-node.is-passed, .vcycle-node.is-reached, .vcycle-node.is-done { border-left-color: var(--fresh); }
  .vcycle-node.is-failed, .vcycle-node.is-regressed, .vcycle-node.is-blocked, .vcycle-node.is-error { border-left-color: var(--degraded); }
  .vcycle-node.is-stale { border-left-color: var(--stale); }
  .vcycle-node.is-todo { border-left-color: var(--signal); }
  .vcycle-node-state { color: var(--text-muted); font: 12px/1.4 var(--font-mono); }
  .vcycle-node-state.is-stale-text { color: var(--stale); }
  .vcycle-group { margin-top: 14px; }
  .vcycle-group-heading { margin: 0 0 8px; color: var(--text-muted); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .vcycle-group-items { display: flex; flex-wrap: wrap; gap: 8px; }
  .goal-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .goal-id { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .goal-title { margin: 0; font: 650 clamp(18px, 2.6vw, 26px)/1.1 var(--font-display); letter-spacing: -.02em; }
  .goal-state { padding: 3px 9px; border: 1px solid var(--line-strong); border-radius: 999px; font: 650 12px/1.3 var(--font-mono); }
  .goal-state.is-reached { color: var(--fresh); border-color: var(--fresh); }
  .goal-state.is-regressed, .goal-state.is-blocked { color: var(--degraded); border-color: var(--degraded); }
  .goal-state.is-not-reached, .goal-state.is-active, .goal-state.is-evaluating { color: var(--stale); border-color: var(--stale); }
  .goal-section { margin: 14px 0; padding: 14px 16px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .74); }
  .goal-section-heading { margin: 0 0 9px; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .goal-section-body { min-width: 0; }
  .goal-ref-line { display: flex; flex-wrap: wrap; gap: 8px; }
  .goal-empty { color: var(--text-muted); font: 12px/1.5 var(--font-mono); font-style: italic; }
  .goal-metric, .goal-evidence { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .goal-metric-spec, .goal-evidence-value { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .goal-evidence-commit { color: var(--text-dim); font: 12px/1.5 var(--font-mono); }
  .goal-history { display: grid; gap: 5px; }
  .goal-history-row { display: flex; align-items: baseline; gap: 10px; font: 12px/1.5 var(--font-mono); }
  .goal-history-state { padding: 2px 7px; border: 1px solid var(--line); border-radius: 999px; }
  .goal-history-state.is-reached { color: var(--fresh); }
  .goal-history-state.is-regressed, .goal-history-state.is-blocked { color: var(--degraded); }
  .goal-history-when { color: var(--text-muted); }
  .goal-history-run { color: var(--text-dim); }
  .goal-error { color: var(--degraded); font: 12px/1.5 var(--font-mono); }
  .validation-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .validation-id { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .validation-raw, .validation-goal-state { padding: 3px 9px; border: 1px solid var(--line-strong); border-radius: 999px; font: 650 12px/1.3 var(--font-mono); }
  .validation-raw.is-passed { color: var(--fresh); border-color: var(--fresh); }
  .validation-raw.is-failed, .validation-raw.is-error { color: var(--degraded); border-color: var(--degraded); }
  .validation-raw.is-never-validated { color: var(--text-muted); }
  .validation-stale { margin-left: 6px; color: var(--stale); }
  .validation-goal-state.is-validated { color: var(--fresh); border-color: var(--fresh); }
  .validation-goal-state.is-regressed { color: var(--degraded); border-color: var(--degraded); }
  .validation-goal-state.is-pending { color: var(--stale); border-color: var(--stale); }
  .validation-section { margin: 14px 0; padding: 14px 16px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .74); }
  .validation-section-heading { margin: 0 0 9px; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .validation-section-body { min-width: 0; }
  .validation-ref-line, .validation-goals { display: flex; flex-wrap: wrap; gap: 8px; }
  .validation-goal-chip { display: inline-flex; align-items: baseline; gap: 8px; }
  .validation-goal-state-text { color: var(--text-muted); font: 12px/1.4 var(--font-mono); }
  .validation-empty { color: var(--text-muted); font: 12px/1.5 var(--font-mono); font-style: italic; }
  .validation-error { color: var(--degraded); font: 12px/1.5 var(--font-mono); }
  .sim-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .sim-id { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .sim-result { padding: 3px 9px; border: 1px solid var(--line-strong); border-radius: 999px; font: 650 12px/1.3 var(--font-mono); }
  .sim-result.is-passed { color: var(--fresh); border-color: var(--fresh); }
  .sim-result.is-failed { color: var(--degraded); border-color: var(--degraded); }
  .sim-recorded { color: var(--text-dim); font: 12px/1.5 var(--font-mono); }
  .sim-section { margin: 14px 0; padding: 14px 16px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-sm); background: rgba(13, 26, 32, .74); }
  .sim-section-heading { margin: 0 0 9px; color: var(--signal); font: 650 12px/1.3 var(--font-mono); letter-spacing: .09em; text-transform: uppercase; }
  .sim-section-body { min-width: 0; }
  .sim-ref-line { display: flex; flex-wrap: wrap; gap: 8px; }
  .sim-empty { color: var(--text-muted); font: 12px/1.5 var(--font-mono); font-style: italic; }
  .sim-metrics { display: grid; gap: 4px; }
  .sim-metric-row { display: flex; align-items: baseline; gap: 10px; font: 12px/1.55 var(--font-mono); }
  .sim-metric-name { color: var(--text-muted); }
  .sim-metric-value { color: var(--text); }
  .sim-recording { color: var(--signal); font: 12px/1.55 var(--font-mono); text-decoration: underline; }
  .sim-error { color: var(--degraded); font: 12px/1.5 var(--font-mono); }
  .diagram-header { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
  .diagram-id { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .diagram-title { font: 650 clamp(18px, 2.6vw, 26px)/1.1 var(--font-display); letter-spacing: -.02em; }
  .diagram-embed { width: 100%; min-height: 460px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--surface-raised); }
  .diagram-open { display: inline-block; margin-top: 10px; color: var(--signal); font: 12px/1.5 var(--font-mono); text-decoration: underline; }
  .diagram-missing { padding: 18px; border: 1px dashed var(--line-strong); border-radius: var(--radius-sm); color: var(--text-muted); font: 12px/1.5 var(--font-mono); font-style: italic; }
  .diagram-error { margin-top: 8px; color: var(--degraded); font: 12px/1.5 var(--font-mono); }
  .diagram-focus { margin-top: 12px; display: flex; align-items: baseline; gap: 8px; }
  .diagram-focus-label { color: var(--signal); font: 650 12px/1.3 var(--font-mono); }
  .diagram-focus-value { color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .dossier-verify { margin-left: auto; }
  .dossier-verify button { padding: 7px 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--surface-soft); color: var(--signal); font: 650 12px/1.3 var(--font-body); cursor: pointer; }
  .dossier-verify-note { margin-top: 8px; color: var(--text-muted); font: 12px/1.5 var(--font-mono); }
  .dossier-nav-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .scope-open { color: var(--signal); font: 12px/1.4 var(--font-mono); text-decoration: underline dotted; }
  .scope-open:hover, .scope-open:focus-visible { text-decoration: underline; }
  /* A ref chip that's also an SPA-navigating anchor (Task 2, legibility inc
     2) must keep the ordinary chip look, not the plain-link .scope-open
     style above -- higher specificity (two classes) wins regardless of
     declaration order. */
  .ref-chip.scope-open { color: inherit; font: inherit; text-decoration: none; }
  @media (min-width: 1200px) {
    .workspace-split { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; }
    #scopeWorkspace.workspace-split { width: min(100%, 1380px); }
    .workspace-split > .panel { width: 100%; order: 1; }
    .context-rail { order: 2; position: sticky; top: 0; align-self: start; border-left: 1px solid var(--line); padding-left: 16px; background: var(--surface-soft); }
  }
  .context-rail-section { padding: 14px 0; border-top: 1px solid var(--line); }
  .context-rail-section:first-child { border-top: 0; padding-top: 0; }
  .context-rail-heading { margin: 0 0 8px; color: var(--text-muted); font: 650 12px/1.3 var(--font-mono); letter-spacing: .08em; text-transform: uppercase; }
  .context-rail-readiness { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .context-rail-body { color: var(--text); font-size: 13px; line-height: 1.5; }
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
      <section id="scopeWorkspace" class="workspace-split" hidden>
        <aside id="contextRail" class="context-rail" aria-label="Scope context"></aside>
        <div class="panel">
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
            <button id="tabFeature" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelFeature" aria-label="Feature">Feature</button>
            <button id="tabVcycle" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelVcycle" aria-label="V-cycle">V-cycle</button>
            <button id="tabGoal" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelGoal" aria-label="Goal">Goal</button>
            <button id="tabValidation" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelValidation" aria-label="Validation">Validation</button>
            <button id="tabSim" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelSim" aria-label="Simulation">Simulation</button>
            <button id="tabDiagram" class="tab" role="tab" tabindex="-1" aria-selected="false" aria-controls="panelDiagram" aria-label="Diagram">Diagram</button>
          </div></nav>
          <p id="panelOrientation" class="panel-orientation"></p>
          <div id="panelBrief" class="panel" role="tabpanel" aria-labelledby="tabBrief"></div>
          <div id="panelMatrix" class="panel" role="tabpanel" aria-labelledby="tabMatrix" hidden></div>
          <div id="panelTimeline" class="panel" role="tabpanel" aria-labelledby="tabTimeline" hidden></div>
          <div id="panelGuide" class="panel" role="tabpanel" aria-labelledby="tabGuide" hidden></div>
          <div id="panelStory" class="panel" role="tabpanel" aria-labelledby="tabStory" hidden></div>
          <div id="panelReverse" class="panel" role="tabpanel" aria-labelledby="tabReverse" hidden></div>
          <div id="panelTrace" class="panel" role="tabpanel" aria-labelledby="tabTrace" hidden></div>
          <div id="panelFeature" class="panel" role="tabpanel" aria-labelledby="tabFeature" hidden></div>
          <div id="panelVcycle" class="panel" role="tabpanel" aria-labelledby="tabVcycle" hidden></div>
          <div id="panelGoal" class="panel" role="tabpanel" aria-labelledby="tabGoal" hidden></div>
          <div id="panelValidation" class="panel" role="tabpanel" aria-labelledby="tabValidation" hidden></div>
          <div id="panelSim" class="panel" role="tabpanel" aria-labelledby="tabSim" hidden></div>
          <div id="panelDiagram" class="panel" role="tabpanel" aria-labelledby="tabDiagram" hidden></div>
        </div>
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
