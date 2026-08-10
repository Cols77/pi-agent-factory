// The `/system` navigator shell: scope picker plus brief/matrix/timeline/
// guide tabs. This file owns every bit of navigator UI (design section 6) --
// docs-server.ts and index.ts get wiring only, never markup or rendering
// rules. The guide tab renders exactly what Python already decided
// (synthesized prose with verified verbatim spans, or recorded bullets --
// design section 4.4's collapse predicate) and falls back to a plain notice
// pointing at the other three tabs if the guide fetch itself fails (design
// section 8) -- it never guesses at freshness or assembles prose here.
//
// The one rule this whole file exists to obey: Python computes, this only
// renders. No freshness, ordering, or provenance logic lives here -- every
// claim/row/event is rendered exactly as Python emitted it, in payload
// order, with its own `kind`/`status`/`freshness.state` used verbatim as the
// visible label (never remapped, filtered, or recoloured-only). All
// payload-derived text reaches the DOM through `createTextNode`/`textContent`
// (never string-built `innerHTML`), mirroring review-html.ts's discipline.
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
  .scope-item { display: block; padding: 5px 8px; border: 1px solid var(--line); border-radius: 4px; margin: 4px 0; text-decoration: none; color: inherit; }
  .scope-item:hover { background: var(--hover); }
  .scope-error { color: var(--degraded); font-size: 12px; }
  /* Task 1 (system nav): the scope picker is a searchable, kind-grouped
     list that collapses to a compact bar once a scope is open. When the
     page is in body.focus (a scope is loaded) the big list, its filter,
     the group titles and the heading are hidden behind the single
     "All scopes ▾" toggle button. */
  #picker nav { margin: 10px 0; }
  #scopeFilter { width: 100%; padding: 6px 8px; font: inherit; border: 1px solid var(--line); border-radius: 4px; background: Canvas; color: inherit; margin-bottom: 6px; }
  .scope-group-title { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; opacity: .6; margin: 10px 0 2px; }
  .scope-row { display: flex; align-items: center; }
  .scope-item { display: block; flex: 1; padding: 3px 8px; border: none; border-radius: 3px; margin: 1px 0; text-decoration: none; color: inherit; font: inherit; text-align: left; width: 100%; }
  .scope-item:hover, .scope-item:focus-visible { background: var(--hover); outline: 2px solid currentColor; outline-offset: 1px; }
  .scope-kind { font-size: 10px; text-transform: uppercase; opacity: .55; margin-right: 6px; }
  /* On wide screens the scope list is always an open, independently
     scrollable column; the compact-bar collapse (Task 1) applies only on
     narrow screens via the media query below. */
  @media (max-width: 760px) {
    body.focus #scopeList, body.focus .scope-group-title, body.focus #scopeFilter, body.focus #picker h2 { display: none; }
    #scopeToggle { display: inline-block; font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--sunk); cursor: pointer; }
    body.focus #scopeToggle { display: inline-block; }
  }
  /* Wide screens: the sidebar is always an open column; the toggle + collapse are irrelevant. */
  #scopeToggle { display: none; }
  /* Task 3 (system nav): a slim meta row under the scope header carries the
     per-scope Refresh button and the "loaded at" timestamp. The spinner is
     its own status element above it, shown only while a scope is loading. */
  .scope-meta { display: flex; gap: 10px; align-items: center; margin: 6px 0 2px; font-size: 11px; opacity: .8; }
  #refresh { font: inherit; padding: 2px 8px; border: 1px solid var(--line); border-radius: 3px; background: var(--sunk); cursor: pointer; }
  #content { overflow: auto; padding: 8px 24px 48px; }
  /* Task 4 (system nav): a global visible-focus rule for every interactive
     element so keyboard navigation reveals where focus is. It widens the
     Task 1 .scope-item:focus-visible outline to tabs/buttons/inputs too. */
  a:focus-visible, button:focus-visible, input:focus-visible, .tab:focus-visible, .scope-item:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
  /* Task 2 (system nav): #tabs is sticky so the Brief/Matrix/Timeline/Guide/
     Story/Reverse switch stays visible while scrolling a long panel. Canvas
     background keeps the tab strip opaque (not see-through over scrolled
     content) and z-index keeps it above the panels. */
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
  /* Requirement statements and summaries are multi-line prose. Without
     pre-wrap the payload's own paragraph breaks collapse into one unreadable
     blob -- the single worst rendering problem on this page. pre-wrap keeps
     the recorded structure without running a markdown parser over payload
     text, so nothing here can inject markup. */
  .claim-text { margin-top: 4px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .span { white-space: pre-wrap; overflow-wrap: anywhere; }
  .citation, .evidence-item { overflow-wrap: anywhere; }
  .citations, .spans, .evidence { margin-top: 4px; font-size: 11px; opacity: .8; }
  .citation, .span, .evidence-item { padding: 1px 0; }
  .degraded-banner { border: 1px solid var(--degraded); color: var(--degraded); border-radius: 4px; padding: 6px 10px; margin: 8px 0; }
  .empty { opacity: .7; }
  /* Increment B "V-cycle": Story (forward, task -> runs -> requirements)
     and Reverse (backward, file -> run -> task -> requirements). .run and
     .path reuse .claim's frame; the rest are their own small elements. */
  .run, .path { border: 1px solid var(--line); border-radius: 4px; padding: 8px 10px; margin: 8px 0; }
  .run-head, .story-task { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .source-manifest { color: var(--fresh); }
  .source-session { color: var(--stale); }
  .commit-range, .stops-at { margin-top: 4px; font-size: 11px; opacity: .8; overflow-wrap: anywhere; }
  .changed-files { margin-top: 4px; font-size: 11px; }
  .changed-file { padding: 1px 0; overflow-wrap: anywhere; }
  /* Task 5's implementation_summary (design SS4.3), rendered on a bundle
     task: member claim -- run count, latest outcome, changed-file count,
     latest validation. Uses the same --fresh/--stale/--degraded/--na
     palette as freshnessBadge above so a stale validation reads distinctly
     from a plain pass, never flattened to the same colour. */
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
  /* Task B (system nav): the recovered per-requirement trace -- sr -> its
     upstream br, then each satisfying task -> plan -> spec from the trace
     graph. .trace-sr/.trace-task reuse .claim's frame; the chain reuses the
     .path-chain arrow idiom with its own hop/arrow tokens. */
  .trace-sr, .trace-task { border: 1px solid var(--line); border-radius: 4px; padding: 8px 10px; margin: 8px 0; }
  .trace-chain { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
  .trace-hop { padding: 1px 0; overflow-wrap: anywhere; }
  .trace-arrow { opacity: .6; }
  .trace-upstream { font-size: 11px; opacity: .8; margin-top: 2px; }
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
<script>
(async () => {
  const banner = document.getElementById('banner');
  const picker = document.getElementById('picker');
  const content = document.getElementById('content');

  function showBanner(text) {
    banner.textContent = text || '';
  }

  function clear(el) {
    el.innerHTML = '';
  }

  // Task 3 (system nav): shows/hides the #loading status row. With ok=true
  // (a successful load) the #loadedAt timestamp is stamped with the local
  // time via a text node -- never innerHTML. Loading is cleared on both
  // success and failure so the spinner never lingers.
  function setLoading(on, ok) {
    const loading = document.getElementById('loading');
    if (loading) loading.hidden = !on;
    if (ok) {
      const loadedAt = document.getElementById('loadedAt');
      if (loadedAt) {
        loadedAt.textContent = '';
        loadedAt.appendChild(document.createTextNode(new Date().toLocaleTimeString()));
      }
    }
  }

  function badge(text, extraClass) {
    const el = document.createElement('span');
    el.className = 'badge' + (extraClass ? ' ' + extraClass : '');
    el.appendChild(document.createTextNode(text));
    return el;
  }

  // Freshness is always rendered as its own literal state word (fresh /
  // stale / degraded / n/a) -- the CSS class only adds colour on top of
  // that text, it never stands in for it (design section 6.3).
  function freshnessBadge(freshness) {
    const el = document.createElement('span');
    el.className = 'freshness freshness-' + freshness.state.replace('/', '-');
    el.appendChild(document.createTextNode(freshness.state));
    if (freshness.reason) el.title = freshness.reason;
    return el;
  }

  function citationLine(citation) {
    const el = document.createElement('div');
    el.className = 'citation';
    let text = citation.kind + ': ' + citation.path;
    if (citation.anchor) text += ' #' + citation.anchor;
    el.appendChild(document.createTextNode(text));
    return el;
  }

  // Renders Task 5's implementation_summary (design SS4.3): run count,
  // latest outcome, changed-file count, latest validation -- attached only
  // to a bundle task: member claim. Every field is rendered plainly,
  // including null: changed_file_count is deliberately null (never 0)
  // when nothing was recorded, so "no runs yet" is never confused with
  // "changed nothing" -- that distinction must stay visible here, not be
  // flattened into a blank cell or a zero. Same for latest_outcome and
  // latest_validation. latest_validation's three real verdicts
  // (passed/stale/failed) each get their own colour via the CSS above --
  // a stale pass must never render identically to a plain pass.
  function renderImplementationSummary(summary) {
    const el = document.createElement('div');
    el.className = 'implementation-summary';

    const runs = document.createElement('div');
    runs.className = 'summary-line';
    runs.appendChild(document.createTextNode('runs: ' + summary.runs));
    el.appendChild(runs);

    const outcome = document.createElement('div');
    outcome.className = 'summary-line';
    outcome.appendChild(document.createTextNode(
      'latest outcome: ' + (summary.latest_outcome === null ? 'not recorded' : summary.latest_outcome)
    ));
    el.appendChild(outcome);

    const changedFiles = document.createElement('div');
    changedFiles.className = 'summary-line';
    changedFiles.appendChild(document.createTextNode(
      'changed files: ' + (summary.changed_file_count === null ? 'not recorded' : String(summary.changed_file_count))
    ));
    el.appendChild(changedFiles);

    const validation = document.createElement('div');
    validation.className = 'summary-line';
    validation.appendChild(document.createTextNode('latest validation: '));
    const validationValue = document.createElement('span');
    const validationText = summary.latest_validation === null ? 'not recorded' : summary.latest_validation;
    validationValue.className = 'validation-' + (summary.latest_validation === null ? 'none' : summary.latest_validation);
    validationValue.appendChild(document.createTextNode(validationText));
    validation.appendChild(validationValue);
    el.appendChild(validation);

    return el;
  }

  // Renders one SystemClaim exactly as Python emitted it: claim.kind is the
  // badge text verbatim (recorded/derived/synthesized/missing), never
  // remapped or dropped -- a 'missing' claim renders through this same path,
  // plainly, alongside every other kind.
  function renderClaim(claim) {
    const row = document.createElement('div');
    row.className = 'claim claim-' + claim.kind;
    const head = document.createElement('div');
    head.className = 'claim-head';
    head.appendChild(badge(claim.kind, 'kind-' + claim.kind));
    head.appendChild(freshnessBadge(claim.freshness));
    row.appendChild(head);
    const text = document.createElement('div');
    text.className = 'claim-text';
    text.appendChild(document.createTextNode(claim.text));
    row.appendChild(text);
    if (claim.implementation_summary) {
      row.appendChild(renderImplementationSummary(claim.implementation_summary));
    }
    if (claim.citations && claim.citations.length) {
      const cites = document.createElement('div');
      cites.className = 'citations';
      claim.citations.forEach((c) => cites.appendChild(citationLine(c)));
      row.appendChild(cites);
    }
    if (claim.spans && claim.spans.length) {
      const spans = document.createElement('div');
      spans.className = 'spans';
      claim.spans.forEach((s) => {
        const sp = document.createElement('div');
        sp.className = 'span';
        // Name the source, not its array index. "(citation 0)" is an
        // implementation detail of the payload leaking into a human surface;
        // the reader wants to know WHICH document the words were copied from.
        const cited = (claim.citations || [])[s.citation_index];
        const source = cited ? cited.path + (cited.anchor ? ' #' + cited.anchor : '') : 'unknown source';
        sp.appendChild(document.createTextNode('quoted from ' + source + ': "' + s.text + '"'));
        spans.appendChild(sp);
      });
      row.appendChild(spans);
    }
    return row;
  }

  function renderBrief(brief) {
    const panel = document.getElementById('panelBrief');
    clear(panel);
    if (brief.degraded) {
      // Rendered from brief.degraded_reasons exactly as Python computed
      // it -- never a fixed banner string invented client-side (design
      // section 6.3: browser code must not state a cause the payload
      // itself never asserted). Same shape/rendering as the timeline
      // banner below.
      const banner2 = document.createElement('div');
      banner2.className = 'degraded-banner';
      const label = document.createElement('div');
      label.appendChild(document.createTextNode('degraded:'));
      banner2.appendChild(label);
      const reasons = document.createElement('ul');
      (brief.degraded_reasons || []).forEach((reason) => {
        const li = document.createElement('li');
        li.appendChild(document.createTextNode(reason));
        reasons.appendChild(li);
      });
      banner2.appendChild(reasons);
      panel.appendChild(banner2);
    }
    if (!brief.claims.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No claims recorded for this scope.'));
      panel.appendChild(empty);
      return;
    }
    // Rendered in the payload's own order -- no client-side sort.
    brief.claims.forEach((claim) => panel.appendChild(renderClaim(claim)));
  }

  function renderMatrixRow(row) {
    const el = document.createElement('div');
    el.className = 'matrix-row';
    const head = document.createElement('div');
    head.className = 'row-head';
    const subject = document.createElement('span');
    subject.appendChild(document.createTextNode(row.subject.ref));
    head.appendChild(subject);
    head.appendChild(badge(row.status, 'status-' + row.status));
    head.appendChild(freshnessBadge(row.freshness));
    el.appendChild(head);
    const summary = document.createElement('div');
    summary.className = 'claim-text';
    summary.appendChild(document.createTextNode(row.summary));
    el.appendChild(summary);
    if (row.evidence && row.evidence.length) {
      const evidence = document.createElement('div');
      evidence.className = 'evidence';
      row.evidence.forEach((path) => {
        const item = document.createElement('div');
        item.className = 'evidence-item';
        item.appendChild(document.createTextNode(path));
        evidence.appendChild(item);
      });
      el.appendChild(evidence);
    }
    return el;
  }

  function renderMatrix(matrix) {
    const panel = document.getElementById('panelMatrix');
    clear(panel);
    if (!matrix.rows.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No validation rows recorded for this scope.'));
      panel.appendChild(empty);
      return;
    }
    matrix.rows.forEach((row) => panel.appendChild(renderMatrixRow(row)));
  }

  function renderTimelineEvent(event) {
    const el = document.createElement('div');
    el.className = 'timeline-event';
    const head = document.createElement('div');
    head.className = 'event-head';
    const when = document.createElement('span');
    when.appendChild(document.createTextNode(event.at ? event.at : 'sequence=' + event.sequence));
    head.appendChild(when);
    head.appendChild(badge(event.actor, 'actor'));
    head.appendChild(badge(event.action, 'action'));
    head.appendChild(freshnessBadge(event.freshness));
    el.appendChild(head);
    const subject = document.createElement('div');
    subject.className = 'claim-text';
    subject.appendChild(document.createTextNode(event.subject.ref));
    el.appendChild(subject);
    const cite = citationLine(event.citation);
    el.appendChild(cite);
    return el;
  }

  function renderTimeline(timeline) {
    const panel = document.getElementById('panelTimeline');
    clear(panel);
    if (timeline.degraded) {
      const banner2 = document.createElement('div');
      banner2.className = 'degraded-banner';
      const label = document.createElement('div');
      label.appendChild(document.createTextNode('degraded:'));
      banner2.appendChild(label);
      const reasons = document.createElement('ul');
      timeline.degraded_reasons.forEach((reason) => {
        const li = document.createElement('li');
        li.appendChild(document.createTextNode(reason));
        reasons.appendChild(li);
      });
      banner2.appendChild(reasons);
      panel.appendChild(banner2);
    }
    if (!timeline.events.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No recorded decisions for this scope.'));
      panel.appendChild(empty);
      return;
    }
    // events already arrives chronologically ordered by Python
    // (recorded timestamp, then recorded sequence) -- rendered as-is.
    timeline.events.forEach((event) => panel.appendChild(renderTimelineEvent(event)));
  }

  // A guide section is exactly a SystemClaim -- synthesized prose with
  // verbatim spans (when every supporting dependency is fresh) or recorded
  // bullets otherwise (design section 4.4). Reuses renderClaim verbatim:
  // there is no second rendering rule for a guide section vs. a brief claim.
  function renderGuide(guide) {
    const panel = document.getElementById('panelGuide');
    clear(panel);
    if (!guide.sections.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No guide sections recorded for this scope.'));
      panel.appendChild(empty);
      return;
    }
    guide.sections.forEach((section) => panel.appendChild(renderClaim(section)));
  }

  // design section 8: "If synthesis fails, the browser falls back to the
  // brief + matrix + timeline views with no prose guide." Brief/matrix/
  // timeline are unaffected by a guide failure (loadScope only fails the
  // whole scope when brief/matrix/timeline themselves fail) -- this just
  // tells the reader where to look instead of leaving the tab blank.
  function renderGuideFallback() {
    const panel = document.getElementById('panelGuide');
    clear(panel);
    const note = document.createElement('p');
    note.className = 'empty';
    note.appendChild(document.createTextNode(
      'Guide synthesis is unavailable for this scope. See the Brief, Matrix, and Timeline tabs for the same recorded facts.'
    ));
    panel.appendChild(note);
  }

  // Shared by renderStory/renderReverse below (increment B "V-cycle") --
  // same shape as the inline degraded banners in renderBrief/renderTimeline
  // above, factored out here only because two more callers are added in
  // this file rather than duplicated a third and fourth time.
  function renderDegradedBanner(reasons) {
    const banner2 = document.createElement('div');
    banner2.className = 'degraded-banner';
    const label = document.createElement('div');
    label.appendChild(document.createTextNode('degraded:'));
    banner2.appendChild(label);
    const reasonList = document.createElement('ul');
    (reasons || []).forEach((reason) => {
      const li = document.createElement('li');
      li.appendChild(document.createTextNode(reason));
      reasonList.appendChild(li);
    });
    banner2.appendChild(reasonList);
    return banner2;
  }

  function renderCommitRange(startCommit, resultCommit) {
    const el = document.createElement('div');
    el.className = 'commit-range';
    el.appendChild(document.createTextNode(
      startCommit && resultCommit
        ? 'commits ' + startCommit + '..' + resultCommit
        : 'commit range not recorded'
    ));
    return el;
  }

  // changed_files is null for a session-sourced run (design increment
  // B: a session record never captures changed files) -- that state is
  // already stated plainly by the implementation claim's own 'missing'
  // text (rendered via renderClaim below), so there is nothing further to
  // render here for that case; an empty recorded list is a real, distinct
  // fact and is rendered as such rather than folded into the null case.
  function renderChangedFiles(changedFiles) {
    if (changedFiles === null) return null;
    const el = document.createElement('div');
    el.className = 'changed-files';
    if (!changedFiles.length) {
      const empty = document.createElement('div');
      empty.className = 'changed-file empty';
      empty.appendChild(document.createTextNode('no changed files recorded'));
      el.appendChild(empty);
      return el;
    }
    changedFiles.forEach((path) => {
      const item = document.createElement('div');
      item.className = 'changed-file';
      item.appendChild(document.createTextNode(path));
      el.appendChild(item);
    });
    return el;
  }

  // One storyRun/reverseRun's implementation + changed files + citation --
  // shared by renderStoryRun and renderReversePath below, since a
  // reverseRun is the same shape as a storyRun minus source.
  function renderRunDetail(el, run) {
    el.appendChild(renderCommitRange(run.start_commit, run.result_commit));
    el.appendChild(renderClaim(run.implementation));
    const files = renderChangedFiles(run.implementation.changed_files);
    if (files) el.appendChild(files);
    el.appendChild(citationLine(run.citation));
  }

  // Renders one storyRun: a .source badge naming exactly 'manifest' or
  // 'session' (design increment B) -- a session-sourced run is never
  // rendered identically to a manifest-sourced one, and its 'missing'
  // implementation claim (via renderRunDetail -> renderClaim) is never
  // hidden or folded away.
  function renderStoryRun(run) {
    const el = document.createElement('div');
    el.className = 'run';
    const head = document.createElement('div');
    head.className = 'run-head';
    const source = document.createElement('span');
    source.className = 'badge source source-' + run.source;
    source.appendChild(document.createTextNode(run.source));
    head.appendChild(source);
    const runId = document.createElement('span');
    runId.appendChild(document.createTextNode(run.run_id));
    head.appendChild(runId);
    head.appendChild(badge(run.outcome, 'outcome'));
    el.appendChild(head);
    renderRunDetail(el, run);
    return el;
  }

  function renderStory(story) {
    const panel = document.getElementById('panelStory');
    clear(panel);
    const head = document.createElement('div');
    head.className = 'story-task';
    head.appendChild(document.createTextNode(
      story.task.id + ': ' + story.task.title + ' (' + story.task.status + ')'
    ));
    panel.appendChild(head);
    if (story.degraded) panel.appendChild(renderDegradedBanner(story.degraded_reasons));
    if (!story.runs.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No recorded runs for this task.'));
      panel.appendChild(empty);
    } else {
      // runs already arrives ordered by Python (started_at, then citation
      // path) -- rendered as-is, no client-side sort.
      story.runs.forEach((run) => panel.appendChild(renderStoryRun(run)));
    }
    const reqs = document.createElement('div');
    reqs.className = 'requirements';
    if (story.requirements.length) {
      const label = document.createElement('div');
      label.appendChild(document.createTextNode('requirements:'));
      reqs.appendChild(label);
      story.requirements.forEach((ref) => {
        const item = document.createElement('div');
        item.className = 'requirement';
        item.appendChild(document.createTextNode(ref));
        reqs.appendChild(item);
      });
    } else {
      reqs.appendChild(document.createTextNode('no requirements recorded'));
    }
    panel.appendChild(reqs);
  }

  // One reversePath: file -> run -> task -> requirements, with stops_at
  // always named plainly (never omitted, even when null -- "the chain
  // completed" is itself a fact worth stating, not just the stopping case).
  function renderReversePath(path) {
    const el = document.createElement('div');
    el.className = 'path';
    const chain = document.createElement('div');
    chain.className = 'path-chain';
    function hop(text) {
      const span = document.createElement('span');
      span.className = 'hop';
      span.appendChild(document.createTextNode(text));
      return span;
    }
    function arrow() {
      const span = document.createElement('span');
      span.className = 'arrow';
      span.appendChild(document.createTextNode('→'));
      return span;
    }
    chain.appendChild(hop(path.file));
    chain.appendChild(arrow());
    chain.appendChild(hop(path.run.run_id));
    chain.appendChild(arrow());
    chain.appendChild(hop(path.task ? path.task.id : 'unresolved'));
    chain.appendChild(arrow());
    chain.appendChild(hop(path.requirements.length ? path.requirements.join(', ') : 'unresolved'));
    el.appendChild(chain);
    const stops = document.createElement('div');
    stops.className = 'stops-at';
    stops.appendChild(document.createTextNode(
      'stops_at: ' + (path.stops_at === null ? 'null (chain complete)' : path.stops_at)
    ));
    el.appendChild(stops);
    renderRunDetail(el, path.run);
    return el;
  }

  function renderReverse(reverse) {
    const panel = document.getElementById('panelReverse');
    clear(panel);
    if (reverse.degraded) panel.appendChild(renderDegradedBanner(reverse.degraded_reasons));
    if (!reverse.paths.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No recorded run touches this file.'));
      panel.appendChild(empty);
      return;
    }
    // paths already arrives ordered by Python (started_at, then citation
    // path) -- rendered as-is, no client-side sort.
    reverse.paths.forEach((path) => panel.appendChild(renderReversePath(path)));
  }

  // A plain, visible notice for a panel whose view does not apply to the
  // currently loaded scope's kind (e.g. the Brief panel for a task: scope)
  // -- rendered rather than left blank, mirroring renderGuideFallback's
  // "say where to look instead" discipline above.
  function renderNotApplicable(panelId, note) {
    const panel = document.getElementById(panelId);
    clear(panel);
    const p = document.createElement('p');
    p.className = 'empty';
    p.appendChild(document.createTextNode(note));
    panel.appendChild(p);
  }

  // Task B (system nav): pure inversion of the /api/graph trace graph for the
  // Current scope's SR refs -- the per-requirement trace the /system
  // navigator used to show. No .sort, no payload remap: walk graph.edges in
  // the order factory.trace emits them. For each sr in refs (matching an
  // sr-kind node id, stripping a leading sr:), find every task whose
  // satisfies edge targets it (in edge order), then that task's
  // source_plan -> plan node and the plan's spec_ref -> spec node, plus
  // the sr's upstream -> br node. An unresolved hop stays null (its id/
  // title are never guessed) -- the renderer names it plainly, mirroring
  // reverse.py/walkIntentChain's say-where-it-stopped discipline.
  function invertTraceForScope(graph, refs) {
    const nodes = new Map();
    (graph.nodes || []).forEach((n) => nodes.set(n.id, n));
    const edges = graph.edges || [];
    const result = [];
    refs.forEach((ref) => {
      const srId = ref.replace(/^sr:/, '');
      const srNode = nodes.get(srId) || null;
      const entry = {
        sr: ref,
        srTitle: srNode ? (srNode.title || null) : null,
        br: null,
        tasks: [],
      };
      edges.forEach((e) => {
        if (e.kind === 'upstream' && e.src === srId) {
          if (!entry.br) entry.br = nodes.get(e.dst) || null;
        }
      });
      edges.forEach((e) => {
        if (e.kind === 'satisfies' && e.dst === srId) {
          const taskId = e.src;
          const taskNode = nodes.get(taskId) || null;
          const task = {
            task: taskId,
            plan: null,
            planTitle: null,
            spec: null,
            specTitle: null,
          };
          edges.forEach((e2) => {
            if (e2.kind === 'source_plan' && e2.src === taskId) {
              const planNode = nodes.get(e2.dst) || null;
              if (planNode && !task.plan) {
                task.plan = planNode.id;
                task.planTitle = planNode.title || null;
                edges.forEach((e3) => {
                  if (e3.kind === 'spec_ref' && e3.src === planNode.id && !task.spec) {
                    const specNode = nodes.get(e3.dst) || null;
                    if (specNode) {
                      task.spec = specNode.id;
                      task.specTitle = specNode.title || null;
                    }
                  }
                });
              }
            }
          });
          entry.tasks.push(task);
        }
      });
      result.push(entry);
    });
    return result;
  }

  // Task B (system nav): renders one inverted trace entry's chain per SR.
  // All payload-derived text through createTextNode. The plan/spec hops name
  // the graph node id (and title when present) verbatim, so an unresolved
  // hop -- (plan: unresolved) / (spec: unresolved) -- is never guessed.
  function renderTrace(trace) {
    const panel = document.getElementById('panelTrace');
    clear(panel);
    if (!trace.length) {
      renderNotApplicable('panelTrace', 'No trace recorded for this scope. See the Story or Reverse tabs.');
      return;
    }
    trace.forEach((entry) => {
      const srBox = document.createElement('div');
      srBox.className = 'trace-sr';
      const srHead = document.createElement('div');
      srHead.appendChild(document.createTextNode(
        'SR ' + entry.sr + (entry.srTitle ? ' — ' + entry.srTitle : '')
      ));
      srBox.appendChild(srHead);
      if (entry.br) {
        const upstream = document.createElement('div');
        upstream.className = 'trace-upstream';
        upstream.appendChild(document.createTextNode(
          'upstream: ' + entry.br.id + (entry.br.title ? ' — ' + entry.br.title : '')
        ));
        srBox.appendChild(upstream);
      }
      if (!entry.tasks.length) {
        const none = document.createElement('div');
        none.className = 'empty';
        none.appendChild(document.createTextNode('no satisfying tasks recorded'));
        srBox.appendChild(none);
      }
      entry.tasks.forEach((t) => {
        const taskBox = document.createElement('div');
        taskBox.className = 'trace-task';
        const chain = document.createElement('div');
        chain.className = 'trace-chain';
        function hop(text) {
          const span = document.createElement('span');
          span.className = 'trace-hop';
          span.appendChild(document.createTextNode(text));
          return span;
        }
        function arrow() {
          const span = document.createElement('span');
          span.className = 'trace-arrow';
          span.appendChild(document.createTextNode('→'));
          return span;
        }
        const planLabel = t.plan
          ? 'plan: ' + t.plan + (t.planTitle ? ' (' + t.planTitle + ')' : '')
          : 'plan: (plan: unresolved)';
        const specLabel = t.spec
          ? 'spec: ' + t.spec + (t.specTitle ? ' (' + t.specTitle + ')' : '')
          : 'spec: (spec: unresolved)';
        chain.appendChild(hop(t.task));
        chain.appendChild(arrow());
        chain.appendChild(hop(planLabel));
        chain.appendChild(arrow());
        chain.appendChild(hop(specLabel));
        taskBox.appendChild(chain);
        srBox.appendChild(taskBox);
      });
      panel.appendChild(srBox);
    });
  }

  // Task B (system nav): the lazy trace loader. Fetches /api/graph only on
  // the first click of the Trace tab (never during scope load). On success
  // caches the payload and renders the inversion; on failure renders a plain
  // fallback notice and never touches the other tabs.
  async function loadTrace() {
    if (!scopeSrRefs.length) {
      renderNotApplicable('panelTrace', 'Not applicable for this scope. See the Story or Reverse tabs.');
      return;
    }
    if (traceLoaded) {
      renderTrace(invertTraceForScope(traceData, scopeSrRefs));
      return;
    }
    try {
      const res = await fetch('/api/graph');
      if (!res.ok) throw new Error('graph fetch failed');
      traceData = await res.json();
      traceLoaded = true;
      renderTrace(invertTraceForScope(traceData, scopeSrRefs));
    } catch (err) {
      renderNotApplicable('panelTrace', 'Trace map is unavailable for this scope. See the Brief, Story, or Reverse tabs.');
    }
  }

  // Full, ordered scope list captured for client-side filtering. The refs
  // stay in payload order (never a client-side sort); the filter only ever
  // toggles visibility, never reorders or drops a scope permanently.
  let scopeListData = [];

  // Task 2 (system nav): the currently loaded scope ref (null until one
  // loads). Set at the top of loadScope so all three kind loaders and the
  // SPA URL both see it.
  let currentScope = null;

  // Task B (system nav): the SR refs the current scope resolves to. For an
  // sr: scope that is the single ref; for a bundle: scope it is the
  // bundle's sr: member refs. Set by each kind loader; trace is N/A (empty)
  // for task:/file: scopes.
  let scopeSrRefs = [];
  // Task B (system nav): lazy trace cache -- the /api/graph payload is
  // fetched only on the first click of the Trace tab, never during scope
  // load, so existing dom tests whose fetch mocks throw on /api/graph are
  // never perturbed.
  let traceLoaded = false;
  let traceData = null;
  // Task B (system nav): for an sr: scope the SR is already known
  // synchronously from the requested URL ref, so it is set eagerly here (in
  // the synchronous boot region, before the first await) -- a Trace click
  // that lands before the scope payload finishes still has the SR to
  // invert. This assignment fetches nothing, so the Trace tab stays
  // lazy-on-first-click. bundle: SRs are only known once the scope payload
  // arrives, so they are captured in loadBundleScope instead.
  const bootScope = new URLSearchParams(window.location.search).get('scope');
  if (bootScope && scopeKind(bootScope) === 'sr') scopeSrRefs = [bootScope];

  // Task 2 (system nav): records the active scope in the URL via
  // history.pushState -- SPA navigation with no full page reload, and
  // back/forward work because every load pushed a real history entry. The
  // pushed URL is pathname + ?scope= query only (no hash) so a stale
  // per-tab #hash from a previous scope never lingers after switching
  // scope. The try/catch is required because jsdom and some embeddings
  // throw when pushState targets a cross-origin/non-serializable URL.
  function pushScope(ref) {
    try {
      history.pushState({ scope: ref }, '', location.pathname + '?scope=' + encodeURIComponent(ref));
    } catch {
      /* ignore: SPA URL is best-effort; the load itself already happened */
    }
  }

  // Collapses/expands the picker: a loaded scope puts the body in focus
  // (hiding the big list behind the "All scopes ▾" toggle); the failure /
  // initial / toggle-reveal paths take it back out. aria-expanded on the
  // toggle mirrors the opposite: it reports whether the picker list is open.
  function setPickerClass(focused) {
    document.body.classList.toggle('focus', !!focused);
    const toggle = document.getElementById('scopeToggle');
    if (toggle) toggle.setAttribute('aria-expanded', String(!focused));
  }

  function scopeHref(ref) {
    return '/system?scope=' + encodeURIComponent(ref);
  }

  function renderScopeList(data) {
    const list = document.getElementById('scopeList');
    clear(list);
    scopeListData = [];
    if (!data.scopes.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No scopes declared in this repository yet.'));
      list.appendChild(empty);
    } else {
      let lastKind = null;
      data.scopes.forEach((scope) => {
        scopeListData.push({ kind: scope.kind, ref: scope.ref });
        if (scope.kind !== lastKind) {
          const title = document.createElement('div');
          title.className = 'scope-group-title';
          title.appendChild(document.createTextNode(scope.kind));
          list.appendChild(title);
          lastKind = scope.kind;
        }
        const row = document.createElement('div');
        row.className = 'scope-row';
        const chip = document.createElement('span');
        chip.className = 'scope-kind';
        chip.appendChild(document.createTextNode(scope.kind));
        row.appendChild(chip);
        const a = document.createElement('a');
        a.className = 'scope-item';
        a.dataset.kind = scope.kind;
        a.href = scopeHref(scope.ref);
        a.appendChild(document.createTextNode(scope.ref));
        // Task 2 (system nav): stay in the SPA -- clicking loads the scope
        // in-place via loadScope (which also pushState's the URL) instead of
        // a full page reload that would re-fetch everything and lose your
        // place. The href is kept on the element so middle-click / open-in-
        // new-tab / no-JS still work. The ref is captured in the closure, so
        // no dataset/lookup is needed at click time.
        a.addEventListener('click', (clickEvent) => {
          clickEvent.preventDefault();
          loadScope(scope.ref);
        });
        row.appendChild(a);
        list.appendChild(row);
      });
    }
    const errors = document.getElementById('scopeErrors');
    clear(errors);
    (data.errors || []).forEach((err) => {
      const p = document.createElement('p');
      p.className = 'scope-error';
      p.appendChild(document.createTextNode(
        'bundle load failed: ' + err.bundle_id + ' (' + err.path + '): ' + err.error
      ));
      errors.appendChild(p);
    });
  }

  async function loadScopes() {
    try {
      const res = await fetch('/api/system/scope');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showBanner('could not load declared scopes: ' + (body.error || res.status));
        return;
      }
      renderScopeList(await res.json());
    } catch (err) {
      showBanner('could not load declared scopes: ' + String(err));
    }
  }

  // The search input filters the rendered list in place: a scope row matches
  // when the query appears in its ref or its kind. Group titles are hidden
  // when every scope in their group has been filtered out; an empty query
  // resets visibility so the full, ordered list comes back.
  const scopeFilter = document.getElementById('scopeFilter');
  const scopeList = document.getElementById('scopeList');
  const scopeToggle = document.getElementById('scopeToggle');

  function applyScopeFilter() {
    const q = scopeFilter.value.trim().toLowerCase();
    scopeList.querySelectorAll('.scope-row').forEach((row) => {
      const item = row.querySelector('.scope-item');
      const matches = !q ||
        item.textContent.toLowerCase().includes(q) ||
        (item.dataset.kind || '').toLowerCase().includes(q);
      row.style.display = matches ? '' : 'none';
    });
    scopeList.querySelectorAll('.scope-group-title').forEach((title) => {
      let sibling = title.nextElementSibling;
      let anyVisible = false;
      while (sibling && !sibling.classList.contains('scope-group-title')) {
        if (sibling.style.display !== 'none') { anyVisible = true; break; }
        sibling = sibling.nextElementSibling;
      }
      title.style.display = anyVisible ? '' : 'none';
    });
  }
  scopeFilter.addEventListener('input', applyScopeFilter);

  // The toggle re-opens the collapsed list (removes body.focus). When a
  // scope is loaded the list group titles/filter/heading are hidden and the
  // picker shrinks to just this button (CSS body.focus rules above).
  if (scopeToggle) {
    scopeToggle.addEventListener('click', () => setPickerClass(false));
  }


  function showTab(name) {
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace'].forEach((tab) => {
      document.getElementById('tab' + tab).setAttribute('aria-selected', String(tab === name));
      document.getElementById('panel' + tab).hidden = tab !== name;
    });
    // Task 2 (system nav): keep the active tab in the URL hash so a reload
    // or bookmark restores it. replaceState (not pushState) so switching
    // tabs doesn't pad the back-stack; the hash maps tab name -> lower-case
    // (#Matrix -> #matrix). The try/catch is required for jsdom/odd
    // embeddings that reject URL mutation.
    try {
      history.replaceState(null, '', location.pathname + location.search + '#' + name.toLowerCase());
    } catch {
      /* ignore: hash update is best-effort; the tab switch itself happened */
    }
  }

  // Task 2 (system nav): picks the boot tab from the URL hash when it names
  // a valid tab, otherwise falls back to the scope kind's default tab. A hash
  // that doesn't apply to the current scope kind (e.g. #story on a bundle
  // scope) falls back so we never surface a hidden/mismatched panel.
  function selectInitialTab(kindDefault) {
    const hash = (location.hash || '').replace('#', '').toLowerCase();
    const names = { brief: 'Brief', matrix: 'Matrix', timeline: 'Timeline', guide: 'Guide', story: 'Story', reverse: 'Reverse', trace: 'Trace' };
    showTab(names[hash] || kindDefault);
  }
  document.getElementById('tabBrief').onclick = () => showTab('Brief');
  document.getElementById('tabMatrix').onclick = () => showTab('Matrix');
  document.getElementById('tabTimeline').onclick = () => showTab('Timeline');
  document.getElementById('tabGuide').onclick = () => showTab('Guide');
  document.getElementById('tabStory').onclick = () => showTab('Story');
  document.getElementById('tabReverse').onclick = () => showTab('Reverse');
  document.getElementById('tabTrace').onclick = () => { showTab('Trace'); if (scopeSrRefs.length) loadTrace(); };

  // Task 3 (system nav): the Refresh button re-runs the current scope's load
  // in place (currentScope is set at the top of loadScope), so a stale view
  // can be re-fetched without navigating away. No-op when no scope is loaded.
  document.getElementById('refresh').onclick = () => { if (currentScope) loadScope(currentScope); };

  // Task 4 (system nav): keyboard shortcuts + scope-list arrow navigation.
  // Alt+1..6 (no ctrl/meta) switch tabs via the same showTab used by clicks
  // (aria-selected + hash). When keyboard focus is on a .scope-item and the
  // list is open, ArrowDown/ArrowUp move focus to the next/previous VISIBLE
  // item -- the Task 1 filter hides non-matches with display:none, so only
  // visible rows are reachable, wrapping around at the ends.
  const TAB_ORDER = ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace'];
  window.addEventListener('keydown', (e) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && /^[1-7]$/.test(e.key)) {
      showTab(TAB_ORDER[Number(e.key) - 1]);
      e.preventDefault();
      return;
    }
    const el = (e.target instanceof HTMLElement && e.target.closest('.scope-item')) ? e.target : null;
    if (el && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      const items = Array.from(scopeList.querySelectorAll('.scope-item'))
        .filter((item) => item.style.display !== 'none');
      const idx = items.indexOf(el);
      if (idx === -1) return;
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      const next = items[(idx + delta + items.length) % items.length];
      next.focus();
    }
  });

  // Each of story/reverse/brief+matrix+timeline+guide only resolves one
  // particular scope kind (design increment B: story is task:-only,
  // reverse is file:-only, matching storyScopeRef/reverseScopeRef in
  // system_response.schema.json exactly) -- this reads the same kind:
  // prefix Python itself parses (_task_id_from_scope,
  // _resolve_scope_file) to pick which of Python's own endpoints to call,
  // the same way scopeHref above already builds a scope-kind-agnostic
  // URL. It is dispatch, not interpretation: no freshness, ordering, or
  // provenance is decided here, only which already-built request to send.
  function scopeKind(ref) {
    const idx = ref.indexOf(':');
    return idx === -1 ? '' : ref.slice(0, idx);
  }

  async function loadStoryScope(scopeRef) {
    const res = await fetch('/api/system/story?scope=' + encodeURIComponent(scopeRef));
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner('could not resolve scope ' + scopeRef + ': ' + (body.error || res.status));
      content.hidden = true;
      picker.hidden = false;
      setPickerClass(false);
      setLoading(false);
      return;
    }
    showBanner('');
    content.hidden = false;
    setPickerClass(true);
    document.getElementById('scopeHeader').textContent = scopeRef;
    scopeSrRefs = [];
    renderStory(await res.json());
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Reverse', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a task: scope. See the Story tab.'
    ));
    selectInitialTab('Story');
    setLoading(false, true);
  }

  async function loadReverseScope(scopeRef) {
    const res = await fetch('/api/system/reverse?scope=' + encodeURIComponent(scopeRef));
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner('could not resolve scope ' + scopeRef + ': ' + (body.error || res.status));
      content.hidden = true;
      picker.hidden = false;
      setPickerClass(false);
      setLoading(false);
      return;
    }
    showBanner('');
    content.hidden = false;
    setPickerClass(true);
    document.getElementById('scopeHeader').textContent = scopeRef;
    scopeSrRefs = [];
    renderReverse(await res.json());
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a file: scope. See the Reverse tab.'
    ));
    selectInitialTab('Reverse');
    setLoading(false, true);
  }

  async function loadBundleScope(scopeRef) {
    const scopeParam = encodeURIComponent(scopeRef);
    // The guide fetch is intentionally not in the failure gate below: a
    // failed/unavailable guide degrades only its own tab (design section 8),
    // it must never take down the brief/matrix/timeline views too.
    const [briefRes, matrixRes, timelineRes, guideRes] = await Promise.all([
      fetch('/api/system/brief?scope=' + scopeParam),
      fetch('/api/system/matrix?scope=' + scopeParam),
      fetch('/api/system/timeline?scope=' + scopeParam),
      fetch('/api/system/guide?scope=' + scopeParam),
    ]);
    const failed = [briefRes, matrixRes, timelineRes].find((r) => !r.ok);
    if (failed) {
      const body = await failed.json().catch(() => ({}));
      showBanner('could not resolve scope ' + scopeRef + ': ' + (body.error || failed.status));
      content.hidden = true;
      picker.hidden = false;
      setPickerClass(false);
      setLoading(false);
      return;
    }
    showBanner('');
    const [brief, matrix, timeline] = await Promise.all([
      briefRes.json(), matrixRes.json(), timelineRes.json(),
    ]);
    content.hidden = false;
    setPickerClass(true);
    document.getElementById('scopeHeader').textContent = scopeRef;
    renderBrief(brief);
    renderMatrix(matrix);
    renderTimeline(timeline);
    if (guideRes.ok) {
      renderGuide(await guideRes.json());
    } else {
      renderGuideFallback();
    }
    renderNotApplicable('panelStory', 'Not applicable for a bundle:/sr: scope. See the Story tab for a task: scope.');
    renderNotApplicable('panelReverse', 'Not applicable for a bundle:/sr: scope. See the Reverse tab for a file: scope.');
    // Task B (system nav): record the trace-able SR refs for this scope so the
    // lazy Trace tab knows what to invert when first clicked. An sr: scope
    // is its own single SR; a bundle: scope's SRs come from the matrix rows
    // (the payload field through which the docs server states requirement
    // membership), in payload order.
    if (scopeKind(scopeRef) === 'sr') {
      scopeSrRefs = [scopeRef];
    } else {
      scopeSrRefs = [];
      (matrix.rows || []).forEach((row) => {
        if (row.subject && row.subject.kind === 'sr') scopeSrRefs.push(row.subject.ref);
      });
    }
    traceLoaded = false;
    traceData = null;
    selectInitialTab('Brief');
    setLoading(false, true);
  }

  async function loadScope(scopeRef) {
    // Task 2 (system nav): SPA entry -- record the ref and push a history
    // entry so the URL stays in sync and back/forward work, then dispatch to
    // the kind loader. pushScope runs here (not inside the kind loaders) so
    // all three paths get it exactly once.
    currentScope = scopeRef;
    pushScope(scopeRef);
    const kind = scopeKind(scopeRef);
    if (kind === 'task') {
      await loadStoryScope(scopeRef);
      return;
    }
    if (kind === 'file') {
      await loadReverseScope(scopeRef);
      return;
    }
    await loadBundleScope(scopeRef);
  }

  await loadScopes();
  setPickerClass(false);
  const requestedScope = new URLSearchParams(window.location.search).get('scope');
  if (requestedScope) {
    try {
      await loadScope(requestedScope);
    } catch (err) {
      showBanner('could not resolve scope ' + requestedScope + ': ' + String(err));
      content.hidden = true;
      picker.hidden = false;
      setPickerClass(false);
      setLoading(false);
    }
  }
})();
</script>
</body></html>`;
}
