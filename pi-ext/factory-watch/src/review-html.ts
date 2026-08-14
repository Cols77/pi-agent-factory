export function renderReviewHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly).
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Review</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.5 ui-monospace, monospace; margin: 0; display: grid;
         grid-template-rows: auto auto 1fr; height: 100vh; }
  #panes { display: grid; grid-template-columns: 1.2fr 240px 2fr 320px; overflow: hidden; }
  .pane { display: flex; flex-direction: column; overflow: hidden; border-left: 1px solid #8884; }
  .pane-head { display: flex; align-items: center; gap: 4px; padding: 2px 4px;
               border-bottom: 1px solid #8884; font-size: 11px; opacity: .8; user-select: none; }
  .pane-toggle { cursor: pointer; border: 0; background: none; font: inherit; padding: 0 2px; }
  .pane-body { overflow: auto; padding: 8px; flex: 1; }
  .pane.collapsed .pane-body, .pane.zoomed-out { display: none; }
  .pane.collapsed .pane-label { writing-mode: vertical-rl; }
  .row { white-space: pre-wrap; padding-left: 18px; position: relative; }
  .row.add { background: rgba(0,200,0,.12); }
  .row.del { background: rgba(220,0,0,.12); }
  .row.hunk { color: #6ab; }
  .row .plus { position: absolute; left: 2px; cursor: pointer; opacity: 0; }
  .row:hover .plus { opacity: .6; }
  .row .plus:hover { opacity: 1; }
  .banner { color: #c80; padding: 4px 8px; }
  .guide { padding: 4px 8px; border-bottom: 1px solid #8884; white-space: pre-wrap;
           font-size: 12px; opacity: .9; }
  .guide:empty { display: none; }
  .chain li { list-style: none; }
  .chain .hop { opacity: .75; font-size: 11px; }
  .stops { color: #c80; font-size: 11px; margin: 4px 0; }
  #tree .file { cursor: pointer; padding: 2px 4px; white-space: nowrap; }
  #tree .file.active { background: #8884; }
  .why { font-size: 11px; opacity: .8; padding: 2px 8px; border-bottom: 1px solid #8884; }
  .plan pre { overflow: auto; padding: 6px; background: #8882; }
  .plan code { background: #8882; }
  button { font: inherit; margin: 4px 4px 0 0; }
  .cmt { border: 1px solid #8884; padding: 4px; margin: 4px 0; }
</style></head>
<body>
  <div class="banner" id="banner"></div>
  <div class="guide" id="guide"></div>
  <div id="panes">
    <section class="pane" data-pane="context">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">1 Task context</span></div>
      <div class="pane-body" id="context"></div>
    </section>
    <section class="pane" data-pane="tree">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">2 Files</span></div>
      <div class="pane-body" id="tree"></div>
    </section>
    <section class="pane" data-pane="diff">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">3 Diff</span></div>
      <div class="why" id="why"></div>
      <div class="pane-body" id="diff"></div>
    </section>
    <section class="pane" data-pane="comments">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">4 Review</span></div>
      <div class="pane-body">
        <div><strong>Comments (<span id="count">0</span>)</strong></div>
        <div style="opacity:.7;font-size:11px;margin:2px 0 8px;">hover a diff line, click + to comment</div>
        <div id="cmts"></div>
        <hr>
        <button id="approve">Approve</button>
        <button id="reject">Reject</button>
        <div id="done" hidden>Decision sent — you can close this tab.</div>
      </div>
    </section>
  </div>
<script>
(async () => {
  const data = await (await fetch('/api/review')).json();
  const annotations = [];
  const reviewed = new Set();
  let active = data.files[0] && data.files[0].path;
  document.getElementById('banner').textContent = data.banner || '';

  // Layout constants and the column-template arithmetic are duplicated from
  // review-layout.ts on purpose: this page is served from node:http and
  // cannot import a TypeScript module, so the reducer there stays
  // unit-testable while this inline copy drives the DOM directly. Keep both
  // in sync by hand if the pane set or sizes change.
  const PANES = ['context', 'tree', 'diff', 'comments'];
  const RAIL = '28px';
  const NATURAL = { context: '1.2fr', tree: '240px', diff: '2fr', comments: '320px' };
  let layout = data.layout || { collapsed: [], zoomed: null };

  function applyLayout() {
    const grid = document.getElementById('panes');
    grid.style.gridTemplateColumns = layout.zoomed
      ? PANES.map(p => p === layout.zoomed ? '1fr' : '0px').join(' ')
      : PANES.map(p => layout.collapsed.includes(p) ? RAIL : NATURAL[p]).join(' ');
    for (const el of document.querySelectorAll('.pane')) {
      const id = el.dataset.pane;
      el.classList.toggle('collapsed', !layout.zoomed && layout.collapsed.includes(id));
      el.classList.toggle('zoomed-out', Boolean(layout.zoomed) && layout.zoomed !== id);
    }
    fetch('/api/layout', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(layout),
    }).catch(() => {}); // a failed write just means we don't remember it
  }

  for (const el of document.querySelectorAll('.pane')) {
    el.querySelector('.pane-toggle').onclick = () => {
      const id = el.dataset.pane;
      layout.collapsed = layout.collapsed.includes(id)
        ? layout.collapsed.filter(p => p !== id)
        : layout.collapsed.concat([id]);
      applyLayout();
    };
  }
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const index = ['1', '2', '3', '4'].indexOf(e.key);
    if (index >= 0) { const p = PANES[index]; layout.zoomed = layout.zoomed === p ? null : p; applyLayout(); }
    else if (e.key === 'Escape') { layout.zoomed = null; applyLayout(); }
    else if (e.key === '?') { alert('1-4 zoom a pane, Esc restores, click a pane header to collapse it'); }
  });
  applyLayout();

  // Intent first: what this change was supposed to accomplish, then the task
  // file as a fallback for when the navigator is unavailable.
  function renderContext() {
    const box = document.getElementById('context');
    box.innerHTML = '';
    const line = (text, cls) => {
      const d = document.createElement('div');
      if (cls) d.className = cls;
      d.appendChild(document.createTextNode(text));
      box.appendChild(d);
      return d;
    };
    const intent = data.intent;
    if (intent && intent.chain.length) {
      const list = document.createElement('ul');
      list.className = 'chain';
      intent.chain.forEach((n, depth) => {
        const item = document.createElement('li');
        // A hop with further candidates says so. Showing one of two satisfied
        // requirements with no marker is the partial picture this pane exists
        // to prevent.
        const more = n.alternatives ? '  (+' + n.alternatives + ' more)' : '';
        item.appendChild(document.createTextNode('  '.repeat(depth) + n.kind + ' · ' + n.id + ' — ' + n.title + more));
        list.appendChild(item);
      });
      box.appendChild(list);
    }
    if (intent && intent.stopsAt) {
      line('stops at: ' + intent.stopsAt + ' (nothing recorded links further up)', 'stops');
    }
    const task = data.task;
    if (task) line(task.id + ' — ' + task.title);
    const status = (intent && intent.status) || (task && task.status) || 'unknown';
    line('status: ' + status + (task ? ' · ' + task.path : ''));

    const dod = (intent && intent.dod.length ? intent.dod : (task ? task.dod : [])) || [];
    if (dod.length) {
      line('Definition of done:');
      const list = document.createElement('ul');
      dod.forEach((item) => {
        const row = document.createElement('li');
        row.appendChild(document.createTextNode(item));
        list.appendChild(row);
      });
      box.appendChild(list);
    }
    if (intent && intent.planSection) {
      line('From plan · ' + intent.planSection.heading + ' · ' + intent.planSection.planPath);
      const body = document.createElement('div');
      body.className = 'plan';
      // renderMarkdown escaped this server-side; it is the only trusted HTML here.
      body.innerHTML = intent.planSection.html;
      box.appendChild(body);
    } else {
      line('(no plan section resolved for this task)', 'stops');
    }
  }
  renderContext();

  // Read-only review-focus guide (confidence / validation / verify checklist /
  // already-addressed), mirroring what the TUI overlay surfaces. Static for the
  // session, so rendered once. All text via createTextNode (no innerHTML of
  // server data).
  function renderGuide() {
    const box = document.getElementById('guide');
    box.innerHTML = '';
    const addLine = (t) => { const d = document.createElement('div'); d.appendChild(document.createTextNode(t)); box.appendChild(d); };
    if (data.taskId) addLine('Task: ' + data.taskId);
    const g = data.guide;
    if (!g) return;
    if (g.confidence) addLine('Confidence: ' + g.confidence);
    if (Array.isArray(g.validation) && g.validation.length) {
      addLine('Validation: ' + g.validation.map(v => (v.gate + ' ' + (v.summary || '') + (v.ok === false ? ' ✗' : v.ok ? ' ✓' : '')).trim()).join('   '));
    }
    if (Array.isArray(g.addressed) && g.addressed.length) {
      addLine('Already addressed (' + g.addressed.length + '): ' + g.addressed.join('; '));
    }
    if (Array.isArray(g.verify) && g.verify.length) {
      addLine('Verify before approving:');
      g.verify.forEach((v, i) => addLine('  [' + (i + 1) + '] ' + v.item + (v.file ? '  ' + v.file + (v.line ? ':' + v.line : '') : '')));
    }
  }
  renderGuide();

  const whyCache = {};
  async function showWhy(path) {
    const box = document.getElementById('why');
    box.textContent = 'why this file: …';
    if (!(path in whyCache)) {
      try {
        whyCache[path] = await (await fetch('/api/why?file=' + encodeURIComponent(path))).json();
      } catch (err) {
        whyCache[path] = { status: 'unknown', error: String(err) };
      }
    }
    const value = whyCache[path];
    if (value.status === 'unknown') { box.textContent = 'why this file: unknown (' + value.error + ')'; return; }
    const paths = value.paths || [];
    box.textContent = paths.length === 0
      ? 'why this file: no recorded evidence names it'
      : 'why this file: ' + paths.map(p => (p.task_id || '?') + (p.stops_at ? ' (stops at ' + p.stops_at + ')' : '')).join(', ');
  }

  function renderTree() {
    const tree = document.getElementById('tree');
    tree.innerHTML = '';
    for (const f of data.files) {
      const n = annotations.filter(a => a.file === f.path).length;
      const el = document.createElement('div');
      el.className = 'file' + (f.path === active ? ' active' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = reviewed.has(f.path);
      cb.onclick = (e) => { e.stopPropagation(); cb.checked ? reviewed.add(f.path) : reviewed.delete(f.path); };
      el.appendChild(cb);
      el.appendChild(document.createTextNode(' ' + f.status + ' ' + f.path + (n ? ' (' + n + ')' : '')));
      el.onclick = () => { active = f.path; renderAll(); showWhy(f.path); };
      tree.appendChild(el);
    }
  }
  function renderDiff() {
    const box = document.getElementById('diff');
    box.innerHTML = '';
    const d = data.diffs[active]; if (!d) return;
    d.lines.forEach((line, i) => {
      const m = d.meta[i] || { kind: 'meta' };
      const row = document.createElement('div');
      row.className = 'row ' + m.kind;
      if (m.line !== undefined) {
        const plus = document.createElement('span');
        plus.className = 'plus'; plus.textContent = '+';
        plus.title = 'comment on this line';
        plus.onclick = () => addComment(active, m.line, m.side);
        row.appendChild(plus);
      }
      row.appendChild(document.createTextNode(line));
      box.appendChild(row);
    });
  }
  function renderSide() {
    document.getElementById('count').textContent = String(annotations.length);
    const box = document.getElementById('cmts');
    box.innerHTML = '';
    annotations.forEach((a, idx) => {
      const el = document.createElement('div');
      el.className = 'cmt';
      const where = a.line !== undefined ? a.file + ':' + a.line : a.file + ' (file)';
      el.appendChild(document.createTextNode(where + ': ' + a.body + ' '));
      const del = document.createElement('button');
      del.textContent = 'x'; del.onclick = () => { annotations.splice(idx, 1); renderAll(); };
      el.appendChild(del);
      box.appendChild(el);
    });
  }
  function renderAll() { renderTree(); renderDiff(); renderSide(); }
  function addComment(file, line, side) {
    const body = prompt('Comment on ' + file + (line !== undefined ? ':' + line : ''));
    if (body) { annotations.push({ file, line, side, body, severity: 'must-fix' }); renderAll(); }
  }
  async function submit(decision) {
    if (decision === 'reject' && annotations.length === 0) { alert('reject requires at least one comment'); return; }
    await fetch('/api/decision', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ decision, annotations, reviewedFiles: [...reviewed] }),
    });
    document.getElementById('done').hidden = false;
  }
  document.getElementById('approve').onclick = () => submit('approve');
  document.getElementById('reject').onclick = () => submit('reject');
  renderAll();
})();
</script>
</body></html>`;
}
