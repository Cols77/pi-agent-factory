export function renderDocsHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly),
  // mirroring review-html.ts. Document HTML from /api/doc is produced by
  // md-render.ts, which escapes its input before emitting any markup.
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Docs</title>
<style>
  :root {
    color-scheme: light dark;
    --line: color-mix(in srgb, currentColor 18%, transparent);
    --sunk: color-mix(in srgb, currentColor 6%, transparent);
    --hover: color-mix(in srgb, currentColor 12%, transparent);
    --pass: #3fa14a; --fail: #d24b3f; --warn: #c8871a; --none: #8a8a8a;
  }
  * { box-sizing: border-box; }
  body {
    font: 13px/1.55 ui-sans-serif, system-ui, sans-serif; margin: 0;
    display: grid; grid-template-columns: 290px minmax(0, 1fr) 320px;
    height: 100vh; overflow: hidden;
  }
  #sidebar, #right { overflow: auto; padding: 10px 12px; }
  #sidebar { border-right: 1px solid var(--line); }
  #right { border-left: 1px solid var(--line); }
  #main { overflow: auto; display: flex; flex-direction: column; min-width: 0; }
  #bar {
    position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; align-items: center;
    padding: 8px 16px; border-bottom: 1px solid var(--line);
    background: Canvas;
  }
  #crumb { opacity: .7; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #doc { padding: 4px 24px 24px; max-width: 82ch; }
  #doc pre { background: var(--sunk); padding: 10px; overflow-x: auto; border-radius: 4px; }
  #reviews { padding: 0 24px 48px; max-width: 110ch; }
  .review-record { border: 1px solid var(--line); border-radius: 4px; margin: 8px 0; padding: 6px 9px; }
  .review-record summary { cursor: pointer; font-weight: 600; }
  .review-record .review-meta { font-size: 12px; opacity: .75; margin: 5px 0; }
  .review-record pre { background: var(--sunk); padding: 10px; overflow: auto; max-height: 50vh; }
  .review-record ul { margin: 5px 0; }
  #doc table { border-collapse: collapse; display: block; overflow-x: auto; max-width: 100%; }
  #doc th, #doc td { border: 1px solid var(--line); padding: 4px 7px; text-align: left; }
  #doc code { background: var(--sunk); padding: 0 3px; border-radius: 3px; }
  #doc img { max-width: 100%; }
  #doc h1, #doc h2, #doc h3 { line-height: 1.25; }

  .item {
    cursor: pointer; padding: 3px 6px; border-radius: 4px; display: flex; gap: 6px;
    align-items: baseline; min-width: 0;
  }
  .item:hover { background: var(--hover); }
  .item[aria-current="true"] { background: var(--hover); font-weight: 600; }
  .item .nid {
    font: 11px/1.4 ui-monospace, monospace; opacity: .75; flex: none;
  }
  .item .ntitle { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .group {
    font-weight: 600; opacity: .6; margin: 12px 0 4px; letter-spacing: .06em;
    text-transform: uppercase; font-size: 10px;
  }
  #filter {
    width: 100%; padding: 5px 8px; font: inherit; border: 1px solid var(--line);
    border-radius: 4px; background: var(--sunk); color: inherit;
  }
  #toc div { cursor: pointer; padding: 2px 0; opacity: .8; }
  #toc div:hover { opacity: 1; text-decoration: underline; }
  .gap { color: var(--warn); font-size: 12px; padding: 2px 0; }
  .gap.exempt { opacity: .5; text-decoration: line-through; }
  .gap.deferred { color: var(--none); }
  .bar-track { height: 5px; background: var(--sunk); border-radius: 3px; margin: 5px 0 8px; }
  .bar-track > div { height: 100%; background: var(--pass); border-radius: 3px; }
  .kv { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
  .kv span:last-child { font-variant-numeric: tabular-nums; opacity: .85; }
  .legend { font-size: 11px; opacity: .7; margin-top: 6px; line-height: 1.7; }
  button {
    font: inherit; padding: 3px 10px; border: 1px solid var(--line); border-radius: 4px;
    background: transparent; color: inherit; cursor: pointer;
  }
  button:hover { background: var(--hover); }
  :focus-visible { outline: 2px solid currentColor; outline-offset: 1px; }

  #map { padding: 8px 16px 32px; }
  #map svg, #mini svg { max-width: 100%; height: auto; }
  .gnode rect { fill: Canvas; stroke: var(--line); }
  .gnode:hover rect { stroke: currentColor; }
  .gnode text { fill: currentColor; }
  .gid { font: 600 10px ui-monospace, monospace; }
  .gtitle { font: 10px ui-sans-serif, system-ui, sans-serif; opacity: .65; }
  .gcol { font: 600 9px ui-sans-serif, system-ui, sans-serif; fill: currentColor;
          opacity: .5; letter-spacing: .08em; }
  .gedge { stroke: var(--line); fill: none; }
  svg.dimmed .gnode:not(.on) { opacity: .22; }
  svg.dimmed .gedge:not(.on) { opacity: .06; }
  .gedge.on { stroke: currentColor; opacity: .55; }
  @media (prefers-reduced-motion: no-preference) {
    .gnode, .gedge { transition: opacity .12s ease; }
  }

  @media (max-width: 1180px) {
    body { grid-template-columns: 250px minmax(0, 1fr); }
    #right { display: none; }
    body.show-trace { grid-template-columns: 250px minmax(0, 1fr) 300px; }
    body.show-trace #right { display: block; }
  }
  @media (max-width: 760px) {
    body { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto 1fr; }
    #sidebar { max-height: 34vh; border-right: 0; border-bottom: 1px solid var(--line); }
    body.show-trace { grid-template-columns: minmax(0, 1fr); }
    body.show-trace #right { display: none; }
  }
</style></head>
<body>
  <div id="sidebar">
    <input id="filter" type="search" placeholder="Filter by id or title, e.g. T-051" aria-label="Filter documents">
    <div id="health"></div>
    <div id="list"></div>
  </div>
  <div id="main">
    <div id="bar">
      <button id="showMap">Map</button>
      <button id="toggleTrace">Trace</button>
      <span id="crumb"></span>
    </div>
    <div id="map"></div>
    <div id="doc"></div>
    <div id="reviews"></div>
  </div>
  <div id="right"><div id="toc"></div><div id="trace"></div><div id="mini"></div></div>
<script>
(async () => {
  const KINDS = [["sr","Requirements"],["spec","Specs"],["plan","Plans"],["task","Tasks"],["br","Business"]];
  const STATE = {
    passed:  { mark: "\\u25c9", color: "var(--pass)", label: "pass" },
    failed:  { mark: "\\u25cf", color: "var(--fail)", label: "fail" },
    error:   { mark: "\\u2715", color: "var(--fail)", label: "error" },
    never_validated: { mark: "\\u25cb", color: "var(--none)", label: "never validated" },
  };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const el = (id) => document.getElementById(id);
  const text = (node, s) => { node.appendChild(document.createTextNode(s)); return node; };
  const svgEl = (name, attrs) => {
    const n = document.createElementNS(SVG_NS, name);
    for (const k in attrs) n.setAttribute(k, String(attrs[k]));
    return n;
  };

  let graph = null;
  let active = null;
  let filter = '';

  const res = await fetch('/api/graph');
  if (!res.ok) {
    text(el('health'), 'trace unavailable: ' + ((await res.json()).error || res.status));
  } else {
    graph = await res.json();
  }

  // A node's identity is its id -- that is what factory-run and the CLI report,
  // so it must be visible everywhere the node appears, not only on the map.
  function shortId(id) { return id.replace(/^(plan|spec):/, ''); }

  function validation(id) { return (graph && graph.validation && graph.validation[id]) || null; }

  function badge(id) {
    const v = validation(id);
    if (!v) return '';
    return ' ' + ((STATE[v.state] || {}).mark || '') + (v.stale ? ' \\u26a0' : '');
  }

  function matches(n) {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return n.id.toLowerCase().includes(q) || n.title.toLowerCase().includes(q);
  }

  function renderHealth() {
    const box = el('health'); box.innerHTML = '';
    if (!graph) return;
    const h = graph.health;
    const head = document.createElement('div');
    head.className = 'group'; head.style.marginTop = '10px';
    text(head, 'Traceability ' + h.percent + '%');
    box.appendChild(head);
    const track = document.createElement('div'); track.className = 'bar-track';
    const fill = document.createElement('div'); fill.style.width = h.percent + '%';
    track.appendChild(fill); box.appendChild(track);
    for (const c of h.classes) {
      const row = document.createElement('div'); row.className = 'kv';
      text(document.createElement('span'), '');
      const a = text(document.createElement('span'), c.name);
      const b = text(document.createElement('span'),
        c.satisfied + '/' + c.expected + (c.exempt ? '  (' + c.exempt + ' ex)' : ''));
      row.append(a, b); box.appendChild(row);
    }
    const extra = document.createElement('div'); extra.className = 'kv';
    extra.append(
      text(document.createElement('span'), 'dangling / deferred'),
      text(document.createElement('span'), h.dangling + ' / ' + h.deferred));
    box.appendChild(extra);
    const legend = document.createElement('div'); legend.className = 'legend';
    for (const key of ['passed','failed','error','never_validated']) {
      const s = STATE[key];
      const chip = text(document.createElement('span'), s.mark + ' ' + s.label + '   ');
      chip.style.color = s.color;
      legend.appendChild(chip);
    }
    legend.appendChild(text(document.createElement('span'), '\\u26a0 stale'));
    box.appendChild(legend);
  }

  function renderList() {
    const box = el('list'); box.innerHTML = '';
    if (!graph) return;
    let shown = 0;
    for (const [kind, label] of KINDS) {
      const nodes = graph.nodes.filter((n) => n.kind === kind && matches(n));
      if (nodes.length === 0) continue;
      shown += nodes.length;
      const header = text(document.createElement('div'), label + ' (' + nodes.length + ')');
      header.className = 'group';
      box.appendChild(header);
      for (const n of nodes) {
        const row = document.createElement('div');
        row.className = 'item';
        row.setAttribute('aria-current', String(active === n.id));
        row.tabIndex = 0;
        const id = text(document.createElement('span'), shortId(n.id) + badge(n.id));
        id.className = 'nid';
        const v = validation(n.id);
        if (v) id.style.color = (STATE[v.state] || {}).color || '';
        const title = text(document.createElement('span'), n.title);
        title.className = 'ntitle';
        row.append(id, title);
        row.title = n.path;
        row.onclick = () => openDoc(n.id);
        row.onkeydown = (e) => { if (e.key === 'Enter') openDoc(n.id); };
        box.appendChild(row);
      }
    }
    if (shown === 0) {
      const empty = text(document.createElement('div'), 'Nothing matches "' + filter + '".');
      empty.className = 'legend';
      box.appendChild(empty);
    }
  }

  function group(box, label) {
    const g = text(document.createElement('div'), label);
    g.className = 'group';
    box.appendChild(g);
  }

  function renderTrace(nodeId) {
    const box = el('trace'); box.innerHTML = '';
    if (!graph) return;
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const out = graph.edges.filter((e) => e.src === nodeId);
    const inc = graph.edges.filter((e) => e.dst === nodeId);

    group(box, 'Traceability');
    if (out.length === 0 && inc.length === 0) {
      const none = text(document.createElement('div'), 'No declared links.');
      none.className = 'legend';
      box.appendChild(none);
    }
    for (const e of out.concat(inc)) {
      const outgoing = e.src === nodeId;
      const otherId = outgoing ? e.dst : e.src;
      const other = byId.get(otherId);
      const row = document.createElement('div');
      row.className = 'item';
      const k = text(document.createElement('span'),
        (outgoing ? '\\u2192 ' : '\\u2190 ') + e.kind);
      k.className = 'nid';
      const label = text(document.createElement('span'),
        other ? shortId(otherId) + '  ' + other.title : otherId + '  (missing)');
      label.className = 'ntitle';
      row.append(k, label);
      if (other) { row.onclick = () => openDoc(otherId); } else { row.style.color = 'var(--warn)'; }
      box.appendChild(row);
    }

    const v = validation(nodeId);
    if (v) {
      group(box, 'Validation');
      const s = STATE[v.state] || {};
      const head = text(document.createElement('div'),
        (s.mark || '') + ' ' + (s.label || v.state) + (v.stale ? '   \\u26a0 STALE' : ''));
      head.style.color = v.stale ? 'var(--warn)' : (s.color || '');
      box.appendChild(head);
      if (v.stale) {
        const why = text(document.createElement('div'),
          'Statement or binding changed since this result was earned. Rerun before trusting it.');
        why.className = 'legend';
        box.appendChild(why);
      }
      if (v.metric) {
        const row = document.createElement('div'); row.className = 'kv';
        row.append(text(document.createElement('span'), v.metric),
                   text(document.createElement('span'), v.value + '  ' + (v.assert_expr || '')));
        box.appendChild(row);
      }
      if (v.trials !== null && v.trials !== undefined) {
        const row = document.createElement('div'); row.className = 'kv';
        row.append(text(document.createElement('span'), 'trials'),
                   text(document.createElement('span'), v.trials + ' / ' + v.declared_trials));
        box.appendChild(row);
      }
      if (v.error) {
        const row = text(document.createElement('div'), v.error);
        row.style.color = 'var(--fail)';
        box.appendChild(row);
      }
      for (const a of (v.artifacts || [])) {
        box.appendChild(text(document.createElement('div'), a)).className = 'legend';
      }
    }

    const gaps = graph.gaps.filter((g) => g.node_id === nodeId);
    if (gaps.length) {
      group(box, 'Gaps');
      for (const g of gaps) {
        const row = text(document.createElement('div'), g.kind + ' \\u2014 ' + g.detail);
        row.className = 'gap ' + g.disposition;
        box.appendChild(row);
      }
    }
  }

  // Layout arithmetic lives in graph-layout.ts and arrives via /api/layout, so
  // this page only draws. Edges terminate on box edges, and boxes are painted
  // after edges with an opaque fill, so a link can never run across a label.
  function truncate(s, max) { return s.length > max ? s.slice(0, max - 1) + '\\u2026' : s; }

  async function drawGraph(box, root, hops) {
    box.innerHTML = '';
    const query = root ? '?root=' + encodeURIComponent(root) + '&hops=' + hops : '';
    const r = await fetch('/api/layout' + query);
    if (!r.ok) { text(box, 'Layout unavailable.').className = 'legend'; return; }
    const layout = await r.json();
    if (layout.nodes.length === 0) { text(box, 'Nothing to draw.').className = 'legend'; return; }

    const pad = 4;
    const svg = svgEl('svg', {
      viewBox: (-pad) + ' ' + (-pad) + ' ' + (layout.width + pad * 2) + ' ' + (layout.height + pad * 2),
      width: layout.width, height: layout.height, role: 'img',
    });

    for (const c of layout.columns) {
      svg.appendChild(text(svgEl('text', { x: c.x, y: 10, class: 'gcol' }), c.label.toUpperCase()));
    }

    const edgeEls = new Map();
    for (const e of layout.edges) {
      // Horizontal-tangent cubic: leaves and enters each box side-on, so the
      // curve stays inside the gutter instead of cutting across a column.
      const dx = Math.max(24, Math.abs(e.x2 - e.x1) * 0.5);
      const dir = e.x2 >= e.x1 ? 1 : -1;
      const d = 'M' + e.x1 + ',' + e.y1 +
                ' C' + (e.x1 + dx * dir) + ',' + e.y1 +
                ' ' + (e.x2 - dx * dir) + ',' + e.y2 +
                ' ' + e.x2 + ',' + e.y2;
      const path = svgEl('path', { d, class: 'gedge' });
      svg.appendChild(path);
      edgeEls.set(e, path);
    }

    const nodeEls = new Map();
    for (const n of layout.nodes) {
      const g = svgEl('g', { class: 'gnode', tabindex: '0', role: 'link' });
      g.appendChild(svgEl('rect', { x: n.x, y: n.y, width: n.w, height: n.h, rx: 5 }));
      const v = validation(n.id);
      if (v) {
        g.appendChild(svgEl('rect', {
          x: n.x, y: n.y, width: 3, height: n.h, rx: 1.5,
          fill: v.stale ? 'var(--warn)' : ((STATE[v.state] || {}).color || 'var(--none)'),
          stroke: 'none',
        }));
      }
      g.appendChild(text(svgEl('text', { x: n.x + 9, y: n.y + 14, class: 'gid' }),
        shortId(n.id) + badge(n.id)));
      g.appendChild(text(svgEl('text', { x: n.x + 9, y: n.y + 26, class: 'gtitle' }),
        truncate(n.title, 30)));
      g.appendChild(text(svgEl('title', {}), n.id + ' — ' + n.title));
      g.onclick = () => openDoc(n.id);
      g.onkeydown = (ev) => { if (ev.key === 'Enter') openDoc(n.id); };
      g.onmouseenter = () => highlight(n.id);
      g.onmouseleave = () => highlight(null);
      g.onfocus = () => highlight(n.id);
      g.onblur = () => highlight(null);
      svg.appendChild(g);
      nodeEls.set(n.id, g);
    }

    function highlight(id) {
      if (!id) {
        svg.classList.remove('dimmed');
        for (const g of nodeEls.values()) g.classList.remove('on');
        for (const p of edgeEls.values()) p.classList.remove('on');
        return;
      }
      svg.classList.add('dimmed');
      const near = new Set([id]);
      for (const [e, p] of edgeEls) {
        const touches = e.src === id || e.dst === id;
        p.classList.toggle('on', touches);
        if (touches) { near.add(e.src); near.add(e.dst); }
      }
      for (const [nid, g] of nodeEls) g.classList.toggle('on', near.has(nid));
    }

    box.appendChild(svg);
  }

  async function renderReviews(node) {
    const box = el('reviews'); box.innerHTML = '';
    if (node.kind !== 'task') return;
    const r = await fetch('/api/reviews?task=' + encodeURIComponent(shortId(node.id)));
    if (active !== node.id) return; // a later navigation won the race
    const heading = text(document.createElement('div'), 'Human review history');
    heading.className = 'group'; box.appendChild(heading);
    if (!r.ok) { text(box, 'Review history unavailable.').className = 'legend'; return; }
    const data = await r.json();
    if (!data.reviews.length) {
      text(box, 'No retained human reviews for this task yet. Reviews created before archival was enabled cannot be reconstructed.').className = 'legend';
      return;
    }
    for (const review of data.reviews) {
      const details = document.createElement('details'); details.className = 'review-record';
      const summary = document.createElement('summary');
      summary.appendChild(document.createTextNode((review.reviewed_at || 'unknown time') + ' · ' + review.decision +
        ' · ' + review.annotations.length + ' comment' + (review.annotations.length === 1 ? '' : 's')));
      details.appendChild(summary);
      const meta = document.createElement('div'); meta.className = 'review-meta';
      meta.appendChild(document.createTextNode('Start commit: ' + (review.start_commit || 'unknown') +
        (review.reviewed_files.length ? ' · reviewed: ' + review.reviewed_files.join(', ') : '')));
      details.appendChild(meta);
      if (review.annotations.length) {
        const list = document.createElement('ul');
        review.annotations.forEach((a) => {
          const row = document.createElement('li');
          row.appendChild(document.createTextNode(a.file + (a.line === null ? '' : ':' + a.line) +
            (a.severity ? ' [' + a.severity + ']' : '') + ': ' + a.body));
          list.appendChild(row);
        });
        details.appendChild(list);
      }
      const patch = document.createElement('pre');
      patch.appendChild(document.createTextNode(review.diff || review.diff_error || '(no changes captured)'));
      details.appendChild(patch);
      box.appendChild(details);
    }
  }

  async function renderMap() {
    el('doc').innerHTML = ''; el('reviews').innerHTML = ''; el('toc').innerHTML = '';
    el('trace').innerHTML = ''; el('mini').innerHTML = '';
    el('crumb').textContent = 'All artifacts';
    active = null;
    renderList();
    await drawGraph(el('map'), null, 1);
  }

  async function openDoc(nodeId) {
    if (!graph) return;
    const node = graph.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    active = nodeId;
    el('map').innerHTML = '';
    const r = await fetch('/api/doc?path=' + encodeURIComponent(node.path));
    const doc = el('doc');
    if (!r.ok) {
      doc.innerHTML = '';
      text(doc, 'Could not open ' + node.path + '.');
      return;
    }
    const data = await r.json();
    doc.innerHTML = data.html;
    el('crumb').textContent = shortId(node.id) + '  ·  ' + node.path +
      (data.progress ? '  ·  ' + data.progress.done + '/' + data.progress.total + ' steps' : '');

    const toc = el('toc'); toc.innerHTML = '';
    if (data.toc.length) {
      group(toc, 'Contents');
      for (const entry of data.toc) {
        const row = text(document.createElement('div'),
          '\\u00a0'.repeat((entry.level - 1) * 2) + entry.text);
        row.onclick = () => { const h = document.getElementById(entry.slug); if (h) h.scrollIntoView(); };
        toc.appendChild(row);
      }
    }
    renderTrace(nodeId);
    renderList();
    await renderReviews(node);
    // The 1-hop mini-map: same layout component, smaller scope.
    el('mini').innerHTML = '';
    group(el('mini'), 'Neighbourhood');
    await drawGraph(el('mini'), nodeId, 1);
    document.body.classList.add('show-trace');
  }

  el('showMap').onclick = renderMap;
  el('toggleTrace').onclick = () => document.body.classList.toggle('show-trace');
  el('filter').oninput = (e) => { filter = e.target.value; renderList(); };
  el('filter').onkeydown = (e) => {
    if (e.key !== 'Enter' || !graph) return;
    const hit = graph.nodes.find((n) => matches(n));
    if (hit) openDoc(hit.id);
  };

  renderHealth();
  renderList();
  renderMap();
})();
</script>
</body></html>`;
}
