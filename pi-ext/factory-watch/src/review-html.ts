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
  .row .plus { position: absolute; left: 2px; cursor: pointer; opacity: .5; }
  .row .plus:hover { opacity: 1; }
  .banner { color: #c80; padding: 4px 8px; grid-column: 1 / -1; }
  button { font: inherit; margin: 4px 4px 0 0; }
  .cmt { border: 1px solid #8884; padding: 4px; margin: 4px 0; }
</style></head>
<body>
  <div class="banner" id="banner"></div>
  <div id="tree"></div>
  <div id="diff"></div>
  <div id="side">
    <div><strong>Comments (<span id="count">0</span>)</strong></div>
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
