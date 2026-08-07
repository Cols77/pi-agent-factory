// The `/system` navigator shell: scope picker plus brief/matrix/timeline
// tabs. This file owns every bit of navigator UI (design section 6, task 4
// brief) -- docs-server.ts and index.ts get wiring only, never markup or
// rendering rules.
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
  body { font: 13px/1.55 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 0 0 48px; }
  header { padding: 12px 20px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 15px; margin: 0; }
  #banner { padding: 8px 20px; background: color-mix(in srgb, var(--degraded) 15%, transparent); }
  #banner:empty { display: none; }
  main { max-width: 100ch; margin: 0 auto; padding: 0 20px; }
  #picker { padding: 16px 0; }
  .scope-item { display: block; padding: 5px 8px; border: 1px solid var(--line); border-radius: 4px; margin: 4px 0; text-decoration: none; color: inherit; }
  .scope-item:hover { background: var(--hover); }
  .scope-error { color: var(--degraded); font-size: 12px; }
  #content { padding: 16px 0; }
  #tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }
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
  .claim-text { margin-top: 4px; }
  .citations, .spans, .evidence { margin-top: 4px; font-size: 11px; opacity: .8; }
  .citation, .span, .evidence-item { padding: 1px 0; }
  .degraded-banner { border: 1px solid var(--degraded); color: var(--degraded); border-radius: 4px; padding: 6px 10px; margin: 8px 0; }
  .empty { opacity: .7; }
</style></head>
<body>
  <header><h1>System Navigator</h1></header>
  <div id="banner" role="status"></div>
  <main>
    <div id="picker">
      <h2>Declared scopes</h2>
      <div id="scopeList"></div>
      <div id="scopeErrors"></div>
    </div>
    <div id="content" hidden>
      <h2 id="scopeHeader"></h2>
      <div id="tabs">
        <button id="tabBrief" class="tab" aria-selected="true">Brief</button>
        <button id="tabMatrix" class="tab" aria-selected="false">Matrix</button>
        <button id="tabTimeline" class="tab" aria-selected="false">Timeline</button>
      </div>
      <div id="panelBrief" class="panel"></div>
      <div id="panelMatrix" class="panel" hidden></div>
      <div id="panelTimeline" class="panel" hidden></div>
    </div>
  </main>
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
        sp.appendChild(document.createTextNode('quoted: "' + s.text + '" (citation ' + s.citation_index + ')'));
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
      const banner2 = document.createElement('div');
      banner2.className = 'degraded-banner';
      banner2.appendChild(document.createTextNode('degraded: one or more declared members did not resolve'));
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

  function scopeHref(ref) {
    return '/system?scope=' + encodeURIComponent(ref);
  }

  function renderScopeList(data) {
    const list = document.getElementById('scopeList');
    clear(list);
    if (!data.scopes.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No scopes declared in this repository yet.'));
      list.appendChild(empty);
    } else {
      data.scopes.forEach((scope) => {
        const a = document.createElement('a');
        a.className = 'scope-item';
        a.href = scopeHref(scope.ref);
        a.appendChild(document.createTextNode(scope.ref));
        list.appendChild(a);
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

  function showTab(name) {
    ['Brief', 'Matrix', 'Timeline'].forEach((tab) => {
      document.getElementById('tab' + tab).setAttribute('aria-selected', String(tab === name));
      document.getElementById('panel' + tab).hidden = tab !== name;
    });
  }
  document.getElementById('tabBrief').onclick = () => showTab('Brief');
  document.getElementById('tabMatrix').onclick = () => showTab('Matrix');
  document.getElementById('tabTimeline').onclick = () => showTab('Timeline');

  async function loadScope(scopeRef) {
    const scopeParam = encodeURIComponent(scopeRef);
    const [briefRes, matrixRes, timelineRes] = await Promise.all([
      fetch('/api/system/brief?scope=' + scopeParam),
      fetch('/api/system/matrix?scope=' + scopeParam),
      fetch('/api/system/timeline?scope=' + scopeParam),
    ]);
    const failed = [briefRes, matrixRes, timelineRes].find((r) => !r.ok);
    if (failed) {
      const body = await failed.json().catch(() => ({}));
      showBanner('could not resolve scope ' + scopeRef + ': ' + (body.error || failed.status));
      content.hidden = true;
      picker.hidden = false;
      return;
    }
    showBanner('');
    const [brief, matrix, timeline] = await Promise.all([
      briefRes.json(), matrixRes.json(), timelineRes.json(),
    ]);
    content.hidden = false;
    document.getElementById('scopeHeader').textContent = scopeRef;
    renderBrief(brief);
    renderMatrix(matrix);
    renderTimeline(timeline);
  }

  await loadScopes();
  const requestedScope = new URLSearchParams(window.location.search).get('scope');
  if (requestedScope) {
    try {
      await loadScope(requestedScope);
    } catch (err) {
      showBanner('could not resolve scope ' + requestedScope + ': ' + String(err));
      content.hidden = true;
      picker.hidden = false;
    }
  }
})();
</script>
</body></html>`;
}
