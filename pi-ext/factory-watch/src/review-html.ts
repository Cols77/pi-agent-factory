// Human-code-review browser page (browser surface of /review and runReviewLoop).
//
// Everything inline: the page is served from node:http on a loopback port, so
// there are no external stylesheets, scripts, or fonts. The page fetches one
// JSON document (/api/review), POSTs the decision (/api/decision) and the pane
// layout (POST /api/layout), and lazily resolves per-file provenance
// (GET /api/why?file=).
//
// The diff is the review. Task, Plan, Spec and the verification/validation
// state are read-only references: four header buttons open each component as a
// standalone page in a new browser window (/reference/<kind>, served by
// review-server.ts, rendered by review-reference.ts). The page itself carries
// only the three panes a review actually needs -- Files, Diff, Actions.
//
// Layout constants and the column-template arithmetic are a three-pane subset
// of review-layout.ts on purpose: the reducer there stays unit-testable while
// this inline copy drives the DOM directly. Keep both in sync by hand if the
// pane set or sizes change.
//
// XSS discipline: this page's script performs NO innerHTML writes at all --
// every server value reaches the DOM through createTextNode or textContent,
// and the reference pages (review-reference.ts) escape all server text and
// splice only renderMarkdown output as trusted HTML.
//
// Visual language matches the System Navigator (system-shell.ts): the same
// deep-sea tokens (--bg/--surface/--line/--signal/--add/--warn/--danger) so
// the review instrument reads as part of the same product family.

const STYLE = `
:root {
  color-scheme: dark;
  --bg-deep: #04090c;
  --bg: #071015;
  --surface: #0d1a20;
  --raised: #12242c;
  --soft: #102028;
  --line: #26404a;
  --line-strong: #3a606c;
  --text: #e7f2f5;
  --muted: #91a8b0;
  --dim: #698089;
  --signal: #65d9ff;
  --signal-soft: rgba(101, 217, 255, .12);
  --add: #72e6a6;
  --add-soft: rgba(114, 230, 166, .09);
  --add-softer: rgba(114, 230, 166, .05);
  --warn: #ffc857;
  --warn-soft: rgba(255, 200, 87, .10);
  --danger: #ff6b6b;
  --danger-soft: rgba(255, 107, 107, .09);
  --font-display: "Bahnschrift", "Aptos Display", "Segoe UI Variable Display", sans-serif;
  --font-body: "Aptos", "Segoe UI Variable Text", sans-serif;
  --font-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
  --radius-sm: 6px;
  --radius-md: 9px;
  /* Pane column widths live in variables so the responsive breakpoints
     retune the grid without touching the inline column template. */
  --tree-w: 240px;
  --comments-w: 320px;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { height: 100%; }
body {
  margin: 0; min-width: 320px;
  height: 100vh; height: 100dvh;
  display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto;
  overflow: hidden;
  color: var(--text);
  background:
    radial-gradient(circle at 85% -12%, rgba(101, 217, 255, .10), transparent 34rem),
    linear-gradient(rgba(101, 217, 255, .02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(101, 217, 255, .02) 1px, transparent 1px),
    var(--bg);
  background-size: auto, 32px 32px, 32px 32px, auto;
  font: 14px/1.6 var(--font-body);
}
button { font: inherit; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }
::selection { background: rgba(101, 217, 255, .28); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #1d323c; border-radius: 5px; border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: var(--line-strong); }
::-webkit-scrollbar-corner { background: transparent; }

/* Explicit rows: the empty banner is display:none, so auto-placement would
   shift every section up one row and drop the panes into an auto-sized row
   (content-driven, blowing out) while the statusbar absorbs the free space.
   Naming the rows keeps each section in its intended track regardless. */
.banner { grid-row: 1; }
#verdict { grid-row: 2; }
#panes { grid-row: 3; }
#statusbar { grid-row: 4; }
.banner {
  color: #ffd3d3; background: rgba(255, 107, 107, .12);
  border-bottom: 1px solid rgba(255, 107, 107, .45);
  padding: 6px 20px; font: 12px/1.5 var(--font-mono); white-space: pre-wrap;
}
.banner:empty { display: none; }
.eyebrow {
  color: var(--signal);
  font: 650 11px/1.2 var(--font-mono);
  letter-spacing: .16em; text-transform: uppercase;
}
#verdict {
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px;
  align-items: center; padding: 13px 20px 11px;
  border-bottom: 1px solid var(--line);
  background: rgba(4, 9, 12, .85); backdrop-filter: blur(14px);
  position: relative; z-index: 2;
}
.verdict-left { min-width: 0; }
#taskTitle { margin: 4px 0 3px; font: 650 clamp(17px, 2vw, 23px)/1.15 var(--font-display); letter-spacing: -.015em; }
#taskTitle .id { color: var(--signal); }
.meta-row { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; color: var(--muted); font: 12px/1.4 var(--font-mono); }
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  border: 1px solid var(--line-strong); border-radius: 99px;
  padding: 1px 9px; font: 600 10.5px/1.7 var(--font-mono);
  letter-spacing: .05em; text-transform: uppercase;
  color: var(--muted); background: var(--soft); white-space: nowrap;
}
.chip.ok { color: var(--add); border-color: rgba(114, 230, 166, .45); background: var(--add-softer); }
.chip.warn { color: var(--warn); border-color: rgba(255, 200, 87, .45); background: var(--warn-soft); }
.chip.bad { color: var(--danger); border-color: rgba(255, 107, 107, .5); background: var(--danger-soft); }
.chip.sig { color: var(--signal); border-color: rgba(101, 217, 255, .45); background: var(--signal-soft); }
.chip.dim { color: var(--dim); }
.verdict-actions { display: flex; gap: 10px; align-items: center; justify-content: flex-end; flex-wrap: wrap; flex-shrink: 0; }
.refs { display: flex; gap: 6px; align-items: center; }
.refs .ref { padding: 6px 12px; font-size: 12px; }
.btn {
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--text);
  border-radius: 8px; padding: 8px 18px; cursor: pointer;
  font: 650 13px/1 var(--font-mono); letter-spacing: .02em; white-space: nowrap;
}
.btn:hover { border-color: var(--signal); color: var(--signal); background: var(--signal-soft); }
.btn.ref { color: var(--signal); border-color: rgba(101, 217, 255, .4); }
.btn.approve { color: var(--add); border-color: rgba(114, 230, 166, .5); }
.btn.approve:hover { background: var(--add-softer); box-shadow: 0 0 0 3px var(--add-softer); }
.btn.reject { color: var(--danger); border-color: rgba(255, 107, 107, .5); }
.btn.reject:hover { background: var(--danger-soft); }
.btn:disabled { opacity: .45; pointer-events: none; }
.done { color: var(--add); font: 600 12px/1.4 var(--font-mono); }
#panes {
  display: grid; grid-template-columns: var(--tree-w) minmax(0, 1fr) var(--comments-w);
  grid-template-rows: minmax(0, 1fr);
  overflow: hidden; min-height: 0; min-width: 0;
  transition: grid-template-columns .18s ease;
}
.pane {
  display: flex; flex-direction: column; overflow: hidden;
  border-left: 1px solid var(--line); min-width: 0; min-height: 0;
  background: rgba(7, 16, 21, .5);
}
.pane-head {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 8px 6px; border-bottom: 1px solid var(--line);
  background: var(--bg-deep); user-select: none;
}
.pane-label {
  flex: 1; min-width: 0; color: var(--signal);
  font: 650 11px/1 var(--font-mono); letter-spacing: .14em; text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pane-label .num {
  display: inline-block; min-width: 16px; height: 16px; line-height: 15px; text-align: center;
  margin-right: 6px; border: 1px solid rgba(101, 217, 255, .45); border-radius: 4px;
  font-size: 10px; color: var(--signal); vertical-align: 1px;
}
.pane-toggle, .pane-focus {
  border: 0; background: none; color: var(--dim); cursor: pointer;
  padding: 2px 5px; border-radius: 5px; line-height: 1.2;
}
.pane-toggle:hover, .pane-focus:hover { color: var(--signal); background: var(--signal-soft); }
.pane-focus { font: 600 11px var(--font-mono); }
.pane.focused .pane-focus { color: var(--bg-deep); background: var(--signal); }
.pane.focused .pane-head { background: var(--signal-soft); box-shadow: inset 0 -2px 0 var(--signal); }
.pane.collapsed .pane-body, .pane.zoomed-out { display: none; }
.pane.collapsed .pane-head { justify-content: center; padding: 4px 2px; }
.pane.collapsed .pane-label { writing-mode: vertical-rl; transform: rotate(180deg); letter-spacing: .18em; flex: 0; }
.pane.collapsed .pane-label .num { display: none; }
.pane-body { overflow: auto; padding: 10px 12px 26px; flex: 1; min-height: 0; }

/* 1 - Files */
.tree-stats { color: var(--dim); font: 11px var(--font-mono); margin-bottom: 6px; }
#tree .file {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  padding: 6px 8px; border-radius: 7px; margin: 1px 0; white-space: nowrap;
}
#tree .file:hover { background: var(--soft); }
#tree .file.active { background: var(--raised); box-shadow: inset 3px 0 0 var(--signal); }
#tree .file input { accent-color: var(--add); margin: 0; flex: 0 0 auto; }
.file-status {
  min-width: 18px; text-align: center; font: 700 10px/1.6 var(--font-mono);
  border-radius: 4px; padding: 0 4px; flex: 0 0 auto;
}
.file-status.A { color: var(--add); background: var(--add-soft); border: 1px solid rgba(114, 230, 166, .35); }
.file-status.M { color: var(--warn); background: var(--warn-soft); border: 1px solid rgba(255, 200, 87, .35); }
.file-status.D { color: var(--danger); background: var(--danger-soft); border: 1px solid rgba(255, 107, 107, .4); }
#tree .file .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; font: 12.5px var(--font-mono); color: var(--text); }
#tree .file.reviewed .name { color: var(--add); }
.file-counts { font: 10.5px var(--font-mono); color: var(--dim); flex: 0 0 auto; }
.file-counts .addn { color: var(--add); }
.file-counts .deln { color: var(--danger); }
.cmt-badge {
  flex: 0 0 auto; min-width: 15px; text-align: center;
  color: var(--warn); border: 1px solid rgba(255, 200, 87, .4); border-radius: 99px;
  font: 700 9.5px/1.5 var(--font-mono); padding: 0 3px;
}

/* 2 - Diff */
.diff-head { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line); background: var(--bg-deep); }
#diffFile { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 600 13px var(--font-mono); color: var(--text); }
#diffCounts { font: 11px var(--font-mono); color: var(--dim); white-space: nowrap; }
.why-line { padding: 4px 12px 6px; color: var(--dim); font: 11px/1.5 var(--font-mono); background: rgba(255, 200, 87, .05); border-bottom: 1px dashed var(--line); }
#diff { flex: 1; overflow: auto; padding: 6px 0 30px; }
.row { display: grid; grid-template-columns: 48px 48px 22px minmax(0, 1fr); align-items: baseline; font: 12.5px/1.6 var(--font-mono); }
.g-o, .g-n { padding: 0 6px; text-align: right; color: var(--dim); font-size: 10.5px; user-select: none; background: rgba(4, 9, 12, .4); border-right: 1px solid rgba(38, 64, 74, .4); }
.code { padding: 0 10px 0 4px; white-space: pre; overflow: hidden; min-width: 0; }
.plus {
  text-align: center; cursor: pointer; opacity: 0; color: var(--signal);
  font-weight: 700; border-radius: 3px; align-self: center; line-height: 1.2;
}
.row:hover .plus { opacity: .7; }
.plus:hover { opacity: 1; background: var(--signal-soft); }
.row.add { background: var(--add-soft); }
.row.add .code { color: #cdeeda; }
.row.del { background: var(--danger-soft); }
.row.del .code { color: #f4cfcf; }
.row.context .code { color: var(--muted); }
.row.hunk, .row.meta { grid-template-columns: minmax(0, 1fr); padding: 0 12px; }
.row.hunk { background: rgba(101, 217, 255, .07); color: var(--signal); font-size: 11.5px; }
.row.meta { color: var(--dim); font-size: 11px; }
.row.has-cmt .code { box-shadow: inset 3px 0 0 var(--warn); }
/* 3 - Actions */
.actions-summary { display: flex; align-items: center; gap: 6px; font: 650 12.5px var(--font-mono); }
#count { color: var(--text); font-weight: 700; }
.severity-split { display: flex; gap: 5px; margin: 6px 0 2px; }
.actions-hint { color: var(--dim); font: 11px/1.5 var(--font-mono); margin: 2px 0 10px; }
.actions-hint .plus-glyph { color: var(--signal); font-weight: 700; }
.cmt { border: 1px solid var(--line); background: var(--surface); border-radius: 8px; padding: 8px 10px; margin: 6px 0; }
.cmt-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cmt-where { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 11px var(--font-mono); color: var(--signal); }
.sev { font: 700 9.5px/1.5 var(--font-mono); letter-spacing: .07em; text-transform: uppercase; border-radius: 99px; padding: 1px 8px; cursor: pointer; border: 1px solid transparent; user-select: none; }
.sev.must-fix { color: var(--danger); border-color: rgba(255, 107, 107, .5); background: var(--danger-soft); }
.sev.suggestion { color: var(--warn); border-color: rgba(255, 200, 87, .5); background: var(--warn-soft); }
.cmt-body { font: 12.5px/1.6 var(--font-body); color: var(--text); white-space: pre-wrap; }
.cmt-x { border: 0; background: none; color: var(--dim); cursor: pointer; font: 13px; border-radius: 4px; padding: 0 5px; }
.cmt-x:hover { color: var(--danger); background: var(--danger-soft); }
.empty-state { color: var(--dim); font: 12px var(--font-mono); text-align: center; padding: 24px 10px; border: 1px dashed var(--line); border-radius: 8px; }
.decision-note { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--dim); font: 11.5px/1.5 var(--font-mono); }

/* Status bar */
#statusbar { display: flex; align-items: center; gap: 14px; padding: 4px 20px; border-top: 1px solid var(--line); background: var(--bg-deep); color: var(--dim); font: 11px/1.5 var(--font-mono); }
#statusbar .hints { flex: 1; display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }
kbd { border: 1px solid var(--line-strong); border-bottom-width: 2px; border-radius: 4px; padding: 0 5px; background: var(--surface); color: var(--muted); font: 10.5px var(--font-mono); }
#progress { white-space: nowrap; }
#layoutReset { border: 0; background: none; color: var(--dim); cursor: pointer; font: 10.5px var(--font-mono); text-transform: uppercase; letter-spacing: .08em; }
#layoutReset:hover { color: var(--signal); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }

/* Responsive: retune fixed widths, then go to a single stacked column on
   narrow windows. The verdict actions (Approve / Reject and the reference
   buttons) must stay on screen at every width -- the decision is the primary
   action and may never be pushed off the viewport. No tab mode: references
   open in their own windows via the header buttons. */
@media (max-width: 1280px) {
  :root { --tree-w: 200px; --comments-w: 270px; }
  #verdict { padding: 11px 16px 9px; }
  #statusbar { padding: 4px 14px; }
  body { font-size: 13px; }
}
@media (max-width: 980px) {
  /* The header flows to a single column so the actions never leave the
     viewport; the buttons land below the task identity. */
  #verdict { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .verdict-actions { justify-content: flex-start; }
  #statusbar .hints { display: none; }
  #statusbar { justify-content: flex-end; }
}
@media (max-width: 900px) {
  /* Narrow: panes stack into one column (the JS drives columns='1fr'); zoom
     is meaningless here so the per-pane focus numbers drop out, collapse
     still hides a pane's body. */
  .pane-focus, .pane-label .num { display: none; }
  .pane-body { padding: 8px 10px 20px; }
}
@media (max-width: 760px) {
  .refs { order: -1; flex-basis: 100%; }
  #statusbar { font-size: 10px; }
}
`;

const SCRIPT = `
(async () => {
  'use strict';
  const data = await (await fetch('/api/review')).json();
  const annotations = [];
  const reviewed = new Set();
  let active = (data.files && data.files[0] && data.files[0].path) || null;

  const statusChip = (status) => {
    const s = String(status || 'unknown');
    const low = s.toLowerCase();
    const cls = low.includes('done') || low.includes('pass') || low.includes('approv') ? 'ok'
      : low.includes('fail') || low.includes('block') || low.includes('reject') ? 'bad'
      : low.includes('review') || low.includes('in-progress') ? 'warn'
      : 'dim';
    const chip = document.createElement('span');
    chip.className = 'chip ' + cls;
    chip.appendChild(document.createTextNode(s));
    return chip;
  };

  // Sticky verdict band: identity + status + change statistics + reference
  // buttons (Task / Plan / Spec / Verify open read-only pages in new windows).
  const files = data.files || [];
  let addedTotal = 0;
  let removedTotal = 0;
  for (const f of files) {
    addedTotal += typeof f.added === 'number' ? f.added : 0;
    removedTotal += typeof f.removed === 'number' ? f.removed : 0;
  }
  document.title = 'Human review' + (data.taskId ? ' · ' + data.taskId : '');
  document.getElementById('taskEyebrow').textContent =
    data.implementing ? 'Human review · implementation' : 'Human review · change';
  const title = document.getElementById('taskTitle');
  if (data.task) {
    const idPart = document.createElement('span');
    idPart.className = 'id';
    idPart.appendChild(document.createTextNode(data.task.id));
    title.appendChild(idPart);
    title.appendChild(document.createTextNode(' — ' + data.task.title));
  } else if (data.taskId) {
    title.appendChild(document.createTextNode(data.taskId));
  }
  // Header status chip: the container's own classes carry the chip colour, so
  // the computed status is promoted onto the container element itself.
  {
    const box = document.getElementById('statusChip');
    const chip = statusChip((data.task && data.task.status) || 'unknown');
    box.className = chip.className;
    box.replaceChildren(...chip.childNodes);
  }
  document.getElementById('fileStats').textContent =
    files.length + ' file' + (files.length === 1 ? '' : 's') +
    (addedTotal || removedTotal ? ' · +' + addedTotal + ' −' + removedTotal : '');
  const banner = document.getElementById('banner');
  if (data.banner) banner.textContent = data.banner;

  // Reference pages open in a new browser window (same loopback server,
  // GET /reference/<kind>, rendered by review-reference.ts).
  const openRef = (kind) => {
    if (typeof window.open === 'function') window.open('/reference/' + kind, '_blank');
  };
  document.getElementById('refTask').onclick = () => openRef('task');
  document.getElementById('refPlan').onclick = () => openRef('plan');
  document.getElementById('refSpec').onclick = () => openRef('spec');
  document.getElementById('refVerify').onclick = () => openRef('verify');

  // Layout mirrors the three-pane subset of review-layout.ts: same pane set,
  // rail width and natural widths (kept in sync by hand -- see file header).
  // Tree/comments widths are CSS variables retuned by the responsive
  // breakpoints; the measured values are read once at load because pane
  // widths never change afterwards.
  const PANES = ['tree', 'diff', 'comments'];
  const RAIL = '28px';
  const paneWidth = (name, fallback) => {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  };
  const NATURAL = {
    tree: paneWidth('--tree-w', '240px'),
    diff: 'minmax(0,1fr)',
    comments: paneWidth('--comments-w', '320px'),
  };
  let layout = data.layout || { collapsed: [], zoomed: null };
  if (!Array.isArray(layout.collapsed)) layout.collapsed = [];
  // Narrow windows stack the panes into one column (no tab mode: references
  // open in their own windows). jsdom has no real media queries, so the
  // guard keeps the page testable there.
  const mqNarrow = typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 900px)') : null;
  let narrow = mqNarrow ? mqNarrow.matches : false;

  function el(tag, cls, text) {
    const d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text !== undefined && text !== null) d.appendChild(document.createTextNode(text));
    return d;
  }

  function applyLayout() {
    const grid = document.getElementById('panes');
    if (narrow) {
      grid.style.gridTemplateColumns = '1fr';
      grid.style.gridTemplateRows = '';
      for (const paneEl of document.querySelectorAll('.pane')) {
        const id = paneEl.dataset.pane;
        paneEl.classList.toggle('collapsed', layout.collapsed.includes(id));
        paneEl.classList.toggle('zoomed-out', false);
        paneEl.classList.toggle('focused', false);
      }
    } else {
      grid.style.gridTemplateRows = '';
      grid.style.gridTemplateColumns = layout.zoomed
        ? PANES.map(p => p === layout.zoomed ? '1fr' : '0px').join(' ')
        : PANES.map(p => layout.collapsed.includes(p) ? RAIL : NATURAL[p]).join(' ');
      for (const paneEl of document.querySelectorAll('.pane')) {
        const id = paneEl.dataset.pane;
        paneEl.classList.toggle('collapsed', !layout.zoomed && layout.collapsed.includes(id));
        paneEl.classList.toggle('zoomed-out', Boolean(layout.zoomed) && layout.zoomed !== id);
        paneEl.classList.toggle('focused', layout.zoomed === id);
      }
    }
    fetch('/api/layout', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(layout),
    }).catch(() => {}); // a failed write just means we don't remember it
    renderStatus();
  }

  function renderStatus() {
    const total = (data.files || []).length;
    document.getElementById('progress').textContent =
      annotations.length + ' comment' + (annotations.length === 1 ? '' : 's') +
      ' · ' + reviewed.size + '/' + total + ' files reviewed';
  }
  // 1 - Files: status chips, change counts, per-file comment badges; picking a
  // file opens its diff and lazily resolves provenance.
  function renderTree() {
    const tree = document.getElementById('tree');
    tree.replaceChildren();
    tree.appendChild(el('div', 'tree-stats', files.length + ' file' + (files.length === 1 ? '' : 's')));
    for (const f of files) {
      const rowEl = document.createElement('div');
      rowEl.className = 'file' + (f.path === active ? ' active' : '') + (reviewed.has(f.path) ? ' reviewed' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = reviewed.has(f.path);
      cb.onclick = (e) => {
        e.stopPropagation();
        if (cb.checked) reviewed.add(f.path); else reviewed.delete(f.path);
        rowEl.classList.toggle('reviewed', cb.checked);
        renderStatus();
      };
      rowEl.appendChild(cb);
      rowEl.appendChild(el('span', 'file-status ' + (f.status || 'M'), f.status || 'M'));
      rowEl.appendChild(el('span', 'name', f.path));
      const n = annotations.filter(a => a.file === f.path).length;
      const counts = el('span', 'file-counts', '');
      const added = typeof f.added === 'number' ? f.added : 0;
      const removed = typeof f.removed === 'number' ? f.removed : 0;
      if (added) counts.appendChild(el('span', 'addn', '+' + added));
      if (removed) counts.appendChild(el('span', 'deln', ' −' + removed));
      if (n) counts.appendChild(el('span', 'cmt-badge', String(n)));
      rowEl.appendChild(counts);
      rowEl.onclick = () => { active = f.path; renderAll(); showWhy(f.path); };
      tree.appendChild(rowEl);
    }
  }

  // 2 - Diff: gutter line numbers, hunk rules, row hover reveal of the '+'
  // comment affordance, and a warning notch on anchored rows.
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
    if (value.status === 'unknown') {
      // The system query failed (e.g. a CLI crash). Only the first line of the
      // error belongs in the UI -- a full traceback turns a one-line provenance
      // note into a wall the reviewer has no use for.
      const first = String(value.error || 'unknown error').split('\\n')[0] || 'unknown error';
      box.textContent = 'why this file: unknown (' + first.slice(0, 140) + (first.length > 140 ? '…' : '') + ')';
      return;
    }
    const paths = value.paths || [];
    box.textContent = paths.length === 0
      ? 'why this file: no recorded evidence names it'
      : 'why this file: ' + paths.map(p => (p.task_id || '?') + (p.stops_at ? ' (stops at ' + p.stops_at + ')' : '')).join(', ');
  }

  function renderDiff() {
    const box = document.getElementById('diff');
    box.replaceChildren();
    const d = data.diffs[active];
    document.getElementById('diffFile').textContent = active || '(no file selected)';
    const stat = files.find(f => f.path === active);
    const st = (stat && stat.status) || 'M';
    const stEl = document.getElementById('diffStatus');
    stEl.className = 'file-status ' + st;
    stEl.textContent = st;
    const added = stat && typeof stat.added === 'number' ? stat.added : 0;
    const removed = stat && typeof stat.removed === 'number' ? stat.removed : 0;
    document.getElementById('diffCounts').textContent =
      (added || removed) ? '+ ' + added + '  − ' + removed : '';
    if (!d) {
      box.appendChild(el('div', 'empty-state', 'No diff to show for this file.'));
      return;
    }
    d.lines.forEach((line, i) => {
      const m = d.meta[i] || { kind: 'meta' };
      const row = document.createElement('div');
      row.className = 'row ' + m.kind;
      if (m.kind === 'hunk' || m.kind === 'meta') {
        row.appendChild(document.createTextNode(line));
        box.appendChild(row);
        return;
      }
      row.appendChild(el('span', 'g-o', m.side === 'old' && m.line !== undefined ? String(m.line) : ''));
      row.appendChild(el('span', 'g-n', m.side === 'new' && m.line !== undefined ? String(m.line) : ''));
      if (m.line !== undefined) {
        const plus = document.createElement('span');
        plus.className = 'plus';
        plus.textContent = '+';
        plus.title = 'comment on this line';
        plus.onclick = () => addComment(active, m.line, m.side);
        row.appendChild(plus);
      } else {
        row.appendChild(el('span', 'plus', ''));
      }
      const code = el('span', 'code', line);
      row.appendChild(code);
      if (m.line !== undefined &&
          annotations.some(a => a.file === active && a.line === m.line && a.side === m.side)) {
        row.classList.add('has-cmt');
      }
      box.appendChild(row);
    });
  }

  // 3 - Actions: severity-split comment cards.
  function renderSide() {
    const box = document.getElementById('cmts');
    const mustFix = annotations.filter(a => a.severity !== 'suggestion').length;
    document.getElementById('count').textContent = String(annotations.length);
    const split = document.getElementById('severitySplit');
    split.replaceChildren();
    if (mustFix) split.appendChild(el('span', 'sev must-fix', 'must-fix ' + mustFix));
    if (annotations.length - mustFix) {
      split.appendChild(el('span', 'sev suggestion', 'suggestion ' + (annotations.length - mustFix)));
    }
    box.replaceChildren();
    if (annotations.length === 0) {
      box.appendChild(el('div', 'empty-state', 'No comments yet. Hover a diff line and click the + to add one.'));
    }
    annotations.forEach((a, idx) => {
      const card = el('div', 'cmt');
      const head = el('div', 'cmt-head');
      const where = a.line !== undefined ? a.file + ':' + a.line : a.file + ' (file)';
      head.appendChild(el('span', 'cmt-where', where));
      const sev = document.createElement('button');
      sev.type = 'button';
      const sevValue = a.severity === 'suggestion' ? 'suggestion' : 'must-fix';
      sev.className = 'sev ' + sevValue;
      sev.appendChild(document.createTextNode(sevValue));
      sev.title = 'switch severity';
      sev.setAttribute('aria-label', 'switch severity');
      sev.onclick = () => {
        a.severity = a.severity === 'suggestion' ? 'must-fix' : 'suggestion';
        renderSide();
      };
      head.appendChild(sev);
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'cmt-x';
      del.textContent = '✕';
      del.title = 'remove comment';
      del.setAttribute('aria-label', 'remove comment');
      del.onclick = () => { annotations.splice(idx, 1); renderAll(); };
      head.appendChild(del);
      card.appendChild(head);
      card.appendChild(el('div', 'cmt-body', a.body));
      box.appendChild(card);
    });
  }
  // Interactions: verdict, focus choreography, keyboard file walking.
  function renderAll() { renderTree(); renderDiff(); renderSide(); renderStatus(); }
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
    document.getElementById('approve').disabled = true;
    document.getElementById('reject').disabled = true;
    document.getElementById('progress').textContent =
      annotations.length + ' comment' + (annotations.length === 1 ? '' : 's') +
      ' · ' + (decision === 'approve' ? 'Approved' : 'Rejected');
  }
  function moveFile(dir) {
    if (!files.length) return;
    const i = files.findIndex(f => f.path === active);
    const cur = i < 0 ? 0 : i;
    const next = files[Math.max(0, Math.min(files.length - 1, cur + dir))];
    if (next && next.path !== active) { active = next.path; renderAll(); showWhy(next.path); }
  }

  document.getElementById('approve').onclick = () => submit('approve');
  document.getElementById('reject').onclick = () => submit('reject');
  document.getElementById('layoutReset').onclick = () => { layout = { collapsed: [], zoomed: null }; applyLayout(); };

  for (const paneEl of document.querySelectorAll('.pane')) {
    const id = paneEl.dataset.pane;
    paneEl.querySelector('.pane-toggle').onclick = () => {
      layout.collapsed = layout.collapsed.includes(id)
        ? layout.collapsed.filter(p => p !== id)
        : layout.collapsed.concat([id]);
      applyLayout();
    };
    const focusBtn = paneEl.querySelector('.pane-focus');
    if (focusBtn) focusBtn.onclick = () => { layout.zoomed = layout.zoomed === id ? null : id; applyLayout(); };
  }
  if (mqNarrow && typeof mqNarrow.addEventListener === 'function') {
    mqNarrow.addEventListener('change', () => {
      narrow = mqNarrow.matches;
      applyLayout();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const index = ['1', '2', '3'].indexOf(e.key);
    if (index >= 0 && !narrow) { const p = PANES[index]; layout.zoomed = layout.zoomed === p ? null : p; applyLayout(); }
    else if (e.key === 'Escape') { layout.zoomed = null; applyLayout(); }
    else if (e.key === '?') {
      alert('Focus: 1 Files · 2 Diff · 3 Actions. J/K: next/previous file. Esc: restore layout. Task / Plan / Spec / Verify open their reference pages in new windows.');
    }
    else if (e.key === 'j' || e.key === 'J') moveFile(1);
    else if (e.key === 'k' || e.key === 'K') moveFile(-1);
  });

  applyLayout();
  renderAll();
})();
`;

export function renderReviewHtml(): string {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human review</title>
<link rel="icon" href="data:,">
<style>${STYLE}</style></head>
<body>
  <div class="banner" id="banner"></div>

  <header id="verdict">
    <div class="verdict-left">
      <div class="eyebrow" id="taskEyebrow">Human review</div>
      <h1 id="taskTitle"></h1>
      <div class="meta-row">
        <span class="chip dim" id="statusChip"></span>
        <span id="fileStats"></span>
      </div>
    </div>
    <div class="verdict-actions">
      <div class="refs" role="group" aria-label="Open review references in a new window">
        <button class="btn ref" id="refTask" type="button" title="Open the task in a new window">Task</button>
        <button class="btn ref" id="refPlan" type="button" title="Open the plan section in a new window">Plan</button>
        <button class="btn ref" id="refSpec" type="button" title="Open the spec in a new window">Spec</button>
        <button class="btn ref" id="refVerify" type="button" title="Open verifications and validation state in a new window">Verify</button>
      </div>
      <button class="btn approve" id="approve" type="button">Approve</button>
      <button class="btn reject" id="reject" type="button">Reject</button>
      <span class="done" id="done" hidden>Decision sent — you can close this tab.</span>
    </div>
  </header>

  <main id="panes">
    <section class="pane" data-pane="tree" aria-label="Changed files">
      <div class="pane-head">
        <button class="pane-toggle" type="button" aria-label="Collapse file list">&#9662;</button>
        <button class="pane-focus" type="button" title="Focus this pane (1)">1</button>
        <span class="pane-label"><span class="num">1</span>Files</span>
      </div>
      <div class="pane-body" id="tree"></div>
    </section>
    <section class="pane" data-pane="diff" aria-label="Code changes">
      <div class="pane-head">
        <button class="pane-toggle" type="button" aria-label="Collapse diff">&#9662;</button>
        <button class="pane-focus" type="button" title="Focus this pane (2)">2</button>
        <span class="pane-label"><span class="num">2</span>Diff</span>
      </div>
      <div class="diff-head">
        <span id="diffStatus" class="file-status"></span>
        <span id="diffFile">(no file selected)</span>
        <span id="diffCounts"></span>
      </div>
      <div class="why-line" id="why"></div>
      <div class="pane-body" id="diff"></div>
    </section>
    <section class="pane" data-pane="comments" aria-label="Review actions">
      <div class="pane-head">
        <button class="pane-toggle" type="button" aria-label="Collapse review actions">&#9662;</button>
        <button class="pane-focus" type="button" title="Focus this pane (3)">3</button>
        <span class="pane-label"><span class="num">3</span>Actions</span>
      </div>
      <div class="pane-body">
        <div class="actions-summary">Comments (<span id="count">0</span>)</div>
        <div class="severity-split" id="severitySplit"></div>
        <div class="actions-hint">Hover a diff line, click the <span class="plus-glyph">+</span> to comment there. Click a comment's severity chip to switch between must-fix and suggestion.</div>
        <div id="cmts"></div>
        <div class="decision-note">Rejecting requires at least one comment — a rejection with no evidence is not reviewable.</div>
      </div>
    </section>
  </main>

  <footer id="statusbar">
    <div class="hints">
      <span><kbd>1</kbd>&ndash;<kbd>3</kbd> focus a pane</span>
      <span><kbd>J</kbd>/<kbd>K</kbd> next / previous file</span>
      <span><kbd>Esc</kbd> restore layout</span>
      <span><kbd>?</kbd> key map</span>
      <button id="layoutReset" type="button">reset layout</button>
    </div>
    <span id="progress"></span>
  </footer>
<script>${SCRIPT}</script>
</body></html>`;
}