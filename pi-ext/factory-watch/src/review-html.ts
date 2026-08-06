export function renderReviewHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly).
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Review</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.5 ui-monospace, monospace; margin: 0; display: grid; grid-template-columns: 240px 1fr 320px; height: 100vh; }
  #tree { overflow: auto; border-right: 1px solid #8884; padding: 8px; }
  #tree .file { cursor: pointer; padding: 2px 4px; white-space: nowrap; }
  #tree .file.active { background: #8884; }
  #diff { overflow: auto; padding: 8px; }
  #side { overflow: auto; border-left: 1px solid #8884; padding: 8px; }
  .row { white-space: pre-wrap; padding-left: 18px; position: relative; }
  .row.add { background: rgba(0,200,0,.12); }
  .row.del { background: rgba(220,0,0,.12); }
  .row.hunk { color: #6ab; }
  .row .plus { position: absolute; left: 2px; cursor: pointer; opacity: 0; }
  .row:hover .plus { opacity: .6; }
  .row .plus:hover { opacity: 1; }
  .banner { color: #c80; padding: 4px 8px; grid-column: 1 / -1; }
  .guide { grid-column: 1 / -1; padding: 4px 8px; border-bottom: 1px solid #8884; white-space: pre-wrap; font-size: 12px; opacity: .9; }
  .guide:empty { display: none; }
  #task { grid-column: 1 / -1; overflow: auto; max-height: 35vh; border-bottom: 1px solid #8884; padding: 6px 8px; }
  #task details { max-width: 100ch; }
  #task summary { cursor: pointer; font-weight: bold; }
  #task .meta { opacity: .75; font-size: 12px; margin: 3px 0; }
  #task h1, #task h2, #task h3 { line-height: 1.2; }
  #task pre { overflow: auto; padding: 6px; background: #8882; }
  #task code { background: #8882; }
  #task .dod { margin: 6px 0; }
  #task .task-body { border-top: 1px solid #8884; margin-top: 8px; padding-top: 2px; }
  button { font: inherit; margin: 4px 4px 0 0; }
  .cmt { border: 1px solid #8884; padding: 4px; margin: 4px 0; }
</style></head>
<body>
  <div class="banner" id="banner"></div>
  <div class="guide" id="guide"></div>
  <div id="task" hidden></div>
  <div id="tree"></div>
  <div id="diff"></div>
  <div id="side">
    <div><strong>Comments (<span id="count">0</span>)</strong></div>
    <div style="opacity:.7;font-size:11px;margin:2px 0 8px;">hover a diff line, click + to comment</div>
    <div id="cmts"></div>
    <hr>
    <button id="approve">Approve</button>
    <button id="reject">Reject</button>
    <div id="done" hidden>Decision sent — you can close this tab.</div>
  </div>
<script>
(async () => {
  const data = await (await fetch('/api/review')).json();
  const annotations = [];
  const reviewed = new Set();
  let active = data.files[0] && data.files[0].path;
  document.getElementById('banner').textContent = data.banner || '';

  // The task is first-class review context, not merely an id in the guide.
  // Its HTML originates exclusively in renderMarkdown(), which escapes source
  // markdown before emitting it (the same trusted renderer as /review-plans).
  function renderTask() {
    const box = document.getElementById('task');
    box.innerHTML = '';
    if (!data.task) { box.hidden = true; return; }
    box.hidden = false;
    const details = document.createElement('details');
    details.open = true;
    const summary = document.createElement('summary');
    summary.appendChild(document.createTextNode('Task under review · ' + data.task.id + ' — ' + data.task.title));
    details.appendChild(summary);
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.appendChild(document.createTextNode(data.task.path + ' · status: ' + data.task.status));
    details.appendChild(meta);
    const dod = document.createElement('div');
    dod.className = 'dod';
    dod.appendChild(document.createTextNode('Definition of done:'));
    const list = document.createElement('ul');
    data.task.dod.forEach((item) => {
      const row = document.createElement('li');
      row.appendChild(document.createTextNode(item));
      list.appendChild(row);
    });
    dod.appendChild(list);
    details.appendChild(dod);
    const body = document.createElement('div');
    body.className = 'task-body';
    body.innerHTML = data.task.html;
    details.appendChild(body);
    box.appendChild(details);
  }
  renderTask();

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
      el.onclick = () => { active = f.path; renderAll(); };
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
