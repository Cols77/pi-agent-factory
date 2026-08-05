export function renderDocsHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly),
  // mirroring review-html.ts. Document HTML from /api/doc is produced by
  // md-render.ts, which escapes its input before emitting any markup.
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Docs</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.6 system-ui, sans-serif; margin: 0; display: grid;
         grid-template-columns: 280px 1fr 300px; height: 100vh; }
  #sidebar, #right { overflow: auto; padding: 8px; }
  #sidebar { border-right: 1px solid #8884; }
  #right { border-left: 1px solid #8884; }
  #main { overflow: auto; padding: 16px 24px; }
  #doc { max-width: 80ch; }
  #doc pre { background: #8881; padding: 8px; overflow-x: auto; }
  #doc table { border-collapse: collapse; display: block; overflow-x: auto; }
  #doc th, #doc td { border: 1px solid #8884; padding: 3px 6px; }
  #doc code { background: #8881; padding: 0 3px; }
  .item { cursor: pointer; padding: 2px 4px; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; }
  .item:hover, .item.active { background: #8884; }
  .group { font-weight: 600; opacity: .7; margin-top: 8px; text-transform: uppercase; font-size: 11px; }
  #toc div { cursor: pointer; padding: 1px 0; opacity: .85; }
  #toc div:hover { opacity: 1; text-decoration: underline; }
  .gap { color: #c80; }
  .gap.exempt { opacity: .55; text-decoration: line-through; }
  .gap.deferred { color: #6ab; }
  .bar { height: 6px; background: #8883; margin: 4px 0; }
  .bar > div { height: 100%; background: #4a4; }
  #map { overflow: auto; }
  #map text, #trace text { font: 10px sans-serif; fill: currentColor; }
  #map line, #trace line { stroke: #8886; }
  .legend { font-size: 11px; opacity: .8; margin: 6px 0; }
  button { font: inherit; margin-right: 4px; }
</style></head>
<body>
  <div id="sidebar"><div id="health"></div><div id="list"></div></div>
  <div id="main">
    <div><button id="showMap">Map</button><span id="crumb"></span></div>
    <div id="map"></div>
    <div id="doc"></div>
  </div>
  <div id="right"><div id="toc"></div><hr><div id="trace"></div></div>
<script>
(async () => {
  const KINDS = [["sr","Requirements"],["spec","Specs"],["plan","Plans"],["task","Tasks"],["br","Business"]];
  const STATE_MARK = { passed: "\\u25c9", failed: "\\u25cf", error: "\\u2715", never_validated: "\\u25cb" };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const el = (id) => document.getElementById(id);
  const text = (node, s) => { node.appendChild(document.createTextNode(s)); return node; };

  let graph = null;
  let active = null;

  const res = await fetch('/api/graph');
  if (!res.ok) {
    text(el('health'), 'trace unavailable: ' + ((await res.json()).error || res.status));
  } else {
    graph = await res.json();
  }

  function badge(id) {
    if (!graph || !graph.validation) return '';
    const v = graph.validation[id];
    if (!v) return ' \\u25cb';
    return ' ' + (STATE_MARK[v.state] || '') + (v.stale ? ' \\u26a0' : '');
  }

  function renderHealth() {
    const box = el('health'); box.innerHTML = '';
    if (!graph) return;
    const h = graph.health;
    const title = text(document.createElement('div'), 'Traceability ' + h.percent + '%');
    title.style.fontWeight = '600';
    box.appendChild(title);
    const bar = document.createElement('div'); bar.className = 'bar';
    const fill = document.createElement('div'); fill.style.width = h.percent + '%';
    bar.appendChild(fill); box.appendChild(bar);
    for (const c of h.classes) {
      box.appendChild(text(document.createElement('div'),
        c.name + '  ' + c.satisfied + '/' + c.expected + (c.exempt ? '  (' + c.exempt + ' exempt)' : '')));
    }
    box.appendChild(text(document.createElement('div'),
      'dangling ' + h.dangling + '   deferred ' + h.deferred));
    const legend = text(document.createElement('div'),
      '\\u25c9 pass  \\u25cf fail  \\u2715 error  \\u25cb never validated  \\u26a0 stale');
    legend.className = 'legend';
    box.appendChild(legend);
  }

  function renderList() {
    const box = el('list'); box.innerHTML = '';
    if (!graph) return;
    for (const [kind, label] of KINDS) {
      const nodes = graph.nodes.filter((n) => n.kind === kind);
      if (nodes.length === 0) continue;
      const header = text(document.createElement('div'), label + ' (' + nodes.length + ')');
      header.className = 'group';
      box.appendChild(header);
      for (const n of nodes) {
        const row = text(document.createElement('div'), n.title + (n.kind === 'sr' ? badge(n.id) : ''));
        row.className = 'item' + (active === n.id ? ' active' : '');
        row.title = n.path;
        row.onclick = () => openDoc(n.id);
        box.appendChild(row);
      }
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
    group(box, 'TRACEABILITY');
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    for (const e of graph.edges.filter((e) => e.src === nodeId)) {
      const target = byId.get(e.dst);
      const row = text(document.createElement('div'),
        e.kind + ' \\u2192 ' + (target ? target.title : e.dst + '  (missing)'));
      if (target) { row.className = 'item'; row.onclick = () => openDoc(e.dst); }
      box.appendChild(row);
    }
    for (const e of graph.edges.filter((e) => e.dst === nodeId)) {
      const source = byId.get(e.src);
      const row = text(document.createElement('div'),
        e.kind + ' \\u2190 ' + (source ? source.title : e.src));
      if (source) { row.className = 'item'; row.onclick = () => openDoc(e.src); }
      box.appendChild(row);
    }
    const v = graph.validation[nodeId];
    if (v) {
      group(box, 'VALIDATION');
      box.appendChild(text(document.createElement('div'),
        'state ' + v.state + (v.stale ? '  \\u26a0 STALE' : '')));
      if (v.metric) {
        box.appendChild(text(document.createElement('div'),
          v.metric + ' = ' + v.value + '  assert ' + v.assert_expr));
      }
      if (v.trials !== null && v.trials !== undefined) {
        box.appendChild(text(document.createElement('div'),
          'trials ' + v.trials + '/' + v.declared_trials));
      }
      if (v.error) box.appendChild(text(document.createElement('div'), 'error: ' + v.error));
      for (const a of (v.artifacts || [])) {
        box.appendChild(text(document.createElement('div'), 'artifact ' + a));
      }
    }
    const gaps = graph.gaps.filter((g) => g.node_id === nodeId);
    if (gaps.length) {
      group(box, 'GAPS');
      for (const g of gaps) {
        const row = text(document.createElement('div'), g.kind + ' \\u2014 ' + g.detail);
        row.className = 'gap ' + g.disposition;
        box.appendChild(row);
      }
    }
  }

  // Layout arithmetic lives in graph-layout.ts and arrives via /api/layout, so
  // this page only draws. Passing a root scopes it to that node's neighbourhood,
  // which is what keeps the in-document mini-map legible.
  async function drawGraph(box, root, hops) {
    box.innerHTML = '';
    const query = root ? '?root=' + encodeURIComponent(root) + '&hops=' + hops : '';
    const r = await fetch('/api/layout' + query);
    if (!r.ok) { text(box, 'layout unavailable'); return; }
    const layout = await r.json();
    if (layout.nodes.length === 0) { text(box, 'nothing to draw'); return; }
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', String(layout.width));
    svg.setAttribute('height', String(layout.height));
    for (const e of layout.edges) {
      const line = document.createElementNS(SVG_NS, 'line');
      line.setAttribute('x1', e.x1); line.setAttribute('y1', e.y1);
      line.setAttribute('x2', e.x2); line.setAttribute('y2', e.y2);
      svg.appendChild(line);
    }
    for (const n of layout.nodes) {
      const t = document.createElementNS(SVG_NS, 'text');
      t.setAttribute('x', n.x); t.setAttribute('y', n.y);
      t.style.cursor = 'pointer';
      t.appendChild(document.createTextNode(n.id + (n.kind === 'sr' ? badge(n.id) : '')));
      t.onclick = () => openDoc(n.id);
      svg.appendChild(t);
    }
    box.appendChild(svg);
  }

  async function renderMap() {
    el('doc').innerHTML = ''; el('toc').innerHTML = ''; el('crumb').textContent = '';
    active = null;
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
    if (!r.ok) { doc.innerHTML = ''; text(doc, 'could not open ' + node.path); return; }
    const data = await r.json();
    doc.innerHTML = data.html;
    el('crumb').textContent = '  ' + node.path +
      (data.progress ? '   [' + data.progress.done + '/' + data.progress.total + ' steps]' : '');
    const toc = el('toc'); toc.innerHTML = '';
    group(toc, 'CONTENTS');
    for (const entry of data.toc) {
      const row = text(document.createElement('div'), '  '.repeat(entry.level - 1) + entry.text);
      row.onclick = () => { const h = document.getElementById(entry.slug); if (h) h.scrollIntoView(); };
      toc.appendChild(row);
    }
    renderTrace(nodeId);
    renderList();
    // The 1-hop mini-map: same layout component, smaller scope.
    const mini = document.createElement('div');
    el('trace').appendChild(mini);
    await drawGraph(mini, nodeId, 1);
  }

  el('showMap').onclick = renderMap;
  renderHealth();
  renderList();
  renderMap();
})();
</script>
</body></html>`;
}
