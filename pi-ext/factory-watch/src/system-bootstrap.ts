// SP-B Task 5 split — client bootstrap / controller.
//
// This module is the `/system` client controller: it grabs the shell's DOM
// handles, wires the tabs and the scope picker, loads scopes from the docs
// server, and runs the boot sequence. It is embedded into the page's inline
// <script> via `Function.prototype.toString()` (see system-shell.ts), so it
// must be authored as one plain function whose body references the renderers
// (and the shared `clear` helper) from the enclosing IIFE scope that the shell
// creates. "Python computes, this only renders" applies here too: none of the
// loaders decide freshness/ordering; they dispatch to already-built endpoints.
//
// The lazy trace loader (loadTrace) lives here rather than in system-renderers
// because it reads bootstrap state (scopeSrRefs / traceLoaded / traceData).

// The renderers (and the shared `clear` helper) are defined at the enclosing
// IIFE scope by system-shell.ts, so the embedded function body references them
// as free variables. The `declare const` lines below give TypeScript those
// definitions WITHOUT emitting any runtime import -- an import would make
// esbuild inject its `__name` helper into the function body, which the inline
// script (and its jsdom DOM tests) cannot resolve. `declare` is type-only and
// erased at emit, so `systemBootstrap.toString()` stays clean.
declare const clear: (el: HTMLElement) => void;
declare const invertTraceForScope: (graph: any, refs: string[]) => any[];
declare const renderBrief: (brief: any) => void;
declare const renderGuide: (guide: any) => void;
declare const renderGuideFallback: () => void;
declare const renderMatrix: (matrix: any) => void;
declare const renderNotApplicable: (panelId: string, note: string) => void;
declare const renderReverse: (reverse: any) => void;
declare const renderStory: (story: any) => void;
declare const renderTimeline: (timeline: any) => void;
declare const renderTrace: (trace: any[]) => void;

export async function systemBootstrap(): Promise<void> {
  const banner = document.getElementById('banner') as HTMLElement;
  const picker = document.getElementById('picker') as HTMLElement;
  const content = document.getElementById('content') as HTMLElement;

  function showBanner(text: string): void {
    banner.textContent = text || '';
  }

  // Task 3 (system nav): shows/hides the #loading status row. With ok=true the
  // #loadedAt timestamp is stamped via a text node -- never innerHTML.
  function setLoading(on: boolean, ok?: boolean): void {
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

  // Task B (system nav): the SR refs the current scope resolves to, the lazy
  // trace cache, and the full scope list captured for client-side filtering.
  let scopeSrRefs: string[] = [];
  let traceLoaded = false;
  let traceData: any = null;
  let scopeListData: any[] = [];

  // Task 2 (system nav): the currently loaded scope ref (null until one loads).
  let currentScope: string | null = null;

  // Task B (system nav): eager SR capture for an sr: scope opened at boot, read
  // synchronously before the first await so a Trace click has the SR to invert.
  const bootScope = new URLSearchParams(window.location.search).get('scope');
  if (bootScope && scopeKind(bootScope) === 'sr') scopeSrRefs = [bootScope];

  // Task 2 (system nav): records the active scope in the URL via pushState.
  function pushScope(ref: string): void {
    try {
      history.pushState({ scope: ref }, '', location.pathname + '?scope=' + encodeURIComponent(ref));
    } catch {
      /* ignore: SPA URL is best-effort */
    }
  }

  function setPickerClass(focused: boolean): void {
    document.body.classList.toggle('focus', !!focused);
    const toggle = document.getElementById('scopeToggle');
    if (toggle) toggle.setAttribute('aria-expanded', String(!focused));
  }

  function scopeHref(ref: string): string {
    return '/system?scope=' + encodeURIComponent(ref);
  }

  function renderScopeList(data: any): void {
    const list = document.getElementById('scopeList') as HTMLElement;
    clear(list);
    scopeListData = [];
    if (!data.scopes.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.appendChild(document.createTextNode('No scopes declared in this repository yet.'));
      list.appendChild(empty);
    } else {
      let lastKind: string | null = null;
      data.scopes.forEach((scope: any) => {
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
        // Stay in the SPA: clicking loads the scope in place (which also
        // pushState's the URL) instead of a full page reload.
        a.addEventListener('click', (clickEvent: Event) => {
          clickEvent.preventDefault();
          loadScope(scope.ref);
        });
        row.appendChild(a);
        list.appendChild(row);
      });
    }
    const errors = document.getElementById('scopeErrors') as HTMLElement;
    clear(errors);
    (data.errors || []).forEach((err: any) => {
      const p = document.createElement('p');
      p.className = 'scope-error';
      p.appendChild(document.createTextNode(
        'bundle load failed: ' + err.bundle_id + ' (' + err.path + '): ' + err.error
      ));
      errors.appendChild(p);
    });
  }

  async function loadScopes(): Promise<void> {
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

  // The search input filters the rendered list in place (visibility only, never
  // reorder). Group titles hide when every scope in their group is filtered out.
  const scopeFilter = document.getElementById('scopeFilter') as HTMLInputElement;
  const scopeList = document.getElementById('scopeList') as HTMLElement;
  const scopeToggle = document.getElementById('scopeToggle') as HTMLElement;

  function applyScopeFilter(): void {
    const q = scopeFilter.value.trim().toLowerCase();
    scopeList.querySelectorAll('.scope-row').forEach((row: Element) => {
      const item = row.querySelector('.scope-item') as HTMLElement;
      const matches = !q ||
        item.textContent.toLowerCase().includes(q) ||
        (item.dataset.kind || '').toLowerCase().includes(q);
      (row as HTMLElement).style.display = matches ? '' : 'none';
    });
    scopeList.querySelectorAll('.scope-group-title').forEach((title: Element) => {
      let sibling = title.nextElementSibling;
      let anyVisible = false;
      while (sibling && !sibling.classList.contains('scope-group-title')) {
        if ((sibling as HTMLElement).style.display !== 'none') { anyVisible = true; break; }
        sibling = sibling.nextElementSibling;
      }
      (title as HTMLElement).style.display = anyVisible ? '' : 'none';
    });
  }
  scopeFilter.addEventListener('input', applyScopeFilter);

  // The toggle re-opens the collapsed list (removes body.focus).
  if (scopeToggle) {
    scopeToggle.addEventListener('click', () => setPickerClass(false));
  }

  function showTab(name: string): void {
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace'].forEach((tab) => {
      (document.getElementById('tab' + tab) as HTMLElement).setAttribute('aria-selected', String(tab === name));
      (document.getElementById('panel' + tab) as HTMLElement).hidden = tab !== name;
    });
    // Keep the active tab in the URL hash (replaceState, not pushState, so tab
    // switching does not pad the back-stack).
    try {
      history.replaceState(null, '', location.pathname + location.search + '#' + name.toLowerCase());
    } catch {
      /* ignore: hash update is best-effort */
    }
  }

  // Picks the boot tab from the URL hash when it names a valid tab, else the
  // scope kind's default tab.
  function selectInitialTab(kindDefault: string): void {
    const hash = (location.hash || '').replace('#', '').toLowerCase();
    const names: Record<string, string> = { brief: 'Brief', matrix: 'Matrix', timeline: 'Timeline', guide: 'Guide', story: 'Story', reverse: 'Reverse', trace: 'Trace' };
    showTab(names[hash] || kindDefault);
  }

  (document.getElementById('tabBrief') as HTMLElement).onclick = () => showTab('Brief');
  (document.getElementById('tabMatrix') as HTMLElement).onclick = () => showTab('Matrix');
  (document.getElementById('tabTimeline') as HTMLElement).onclick = () => showTab('Timeline');
  (document.getElementById('tabGuide') as HTMLElement).onclick = () => showTab('Guide');
  (document.getElementById('tabStory') as HTMLElement).onclick = () => showTab('Story');
  (document.getElementById('tabReverse') as HTMLElement).onclick = () => showTab('Reverse');
  (document.getElementById('tabTrace') as HTMLElement).onclick = () => { showTab('Trace'); if (scopeSrRefs.length) loadTrace(); };

  // The Refresh button re-runs the current scope's load in place.
  (document.getElementById('refresh') as HTMLElement).onclick = () => { if (currentScope) loadScope(currentScope); };

  // Task 4 (system nav): keyboard shortcuts + scope-list arrow navigation.
  const TAB_ORDER = ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace'];
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && /^[1-7]$/.test(e.key)) {
      showTab(TAB_ORDER[Number(e.key) - 1]!);
      e.preventDefault();
      return;
    }
    const el = (e.target instanceof HTMLElement && e.target.closest('.scope-item')) ? e.target : null;
    if (el && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      const items = Array.from(scopeList.querySelectorAll('.scope-item'))
        .filter((item) => (item as HTMLElement).style.display !== 'none');
      const idx = items.indexOf(el);
      if (idx === -1) return;
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      const next = items[(idx + delta + items.length) % items.length];
      (next as HTMLElement).focus();
    }
  });

  // Dispatch, not interpretation: reads the same kind: prefix Python parses to
  // pick which of Python's own endpoints to call.
  function scopeKind(ref: string): string {
    const idx = ref.indexOf(':');
    return idx === -1 ? '' : ref.slice(0, idx);
  }

  async function loadStoryScope(scopeRef: string): Promise<void> {
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
    (document.getElementById('scopeHeader') as HTMLElement).textContent = scopeRef;
    scopeSrRefs = [];
    renderStory(await res.json());
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Reverse', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a task: scope. See the Story tab.'
    ));
    selectInitialTab('Story');
    setLoading(false, true);
  }

  async function loadReverseScope(scopeRef: string): Promise<void> {
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
    (document.getElementById('scopeHeader') as HTMLElement).textContent = scopeRef;
    scopeSrRefs = [];
    renderReverse(await res.json());
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a file: scope. See the Reverse tab.'
    ));
    selectInitialTab('Reverse');
    setLoading(false, true);
  }

  async function loadBundleScope(scopeRef: string): Promise<void> {
    const scopeParam = encodeURIComponent(scopeRef);
    // The guide fetch is intentionally not in the failure gate below: a
    // failed/unavailable guide degrades only its own tab.
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
    (document.getElementById('scopeHeader') as HTMLElement).textContent = scopeRef;
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
    // Record the trace-able SR refs for this scope so the lazy Trace tab knows
    // what to invert. An sr: scope is its own single SR; a bundle: scope's SRs
    // come from the matrix rows, in payload order.
    if (scopeKind(scopeRef) === 'sr') {
      scopeSrRefs = [scopeRef];
    } else {
      scopeSrRefs = [];
      (matrix.rows || []).forEach((row: any) => {
        if (row.subject && row.subject.kind === 'sr') scopeSrRefs.push(row.subject.ref);
      });
    }
    traceLoaded = false;
    traceData = null;
    selectInitialTab('Brief');
    setLoading(false, true);
  }

  async function loadScope(scopeRef: string): Promise<void> {
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

  // Task B (system nav): the lazy trace loader. Fetches /api/graph only on the
  // first click of the Trace tab (never during scope load). Lives here because
  // it reads bootstrap state.
  async function loadTrace(): Promise<void> {
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

  // Task 6 (SP-B): the landing page health summary + bundle list, rendered
  // straight from the composed `health` projection (factory.system health
  // --json). Python computed every number; this only renders it via text
  // nodes -- a denominator-of-one ratio ("SR validated 1/1") stays a real
  // ratio, never a green checkmark.
  function renderHealthSummary(payload: any): void {
    const summary = document.getElementById('healthSummary') as HTMLElement;
    clear(summary);
    const h = payload.health || {};
    const pct = document.createElement('div');
    pct.className = 'health-line';
    pct.appendChild(document.createTextNode('Overall ' + h.satisfied + '/' + h.expected + ' satisfied (' + h.percent + '%)'));
    summary.appendChild(pct);
    (h.classes || []).forEach((c: any) => {
      const line = document.createElement('div');
      line.className = 'health-line';
      line.appendChild(document.createTextNode(c.name + ' ' + c.satisfied + '/' + c.expected));
      summary.appendChild(line);
    });
  }

  // Minimal Task 6 bundle list (label per bundle). The feature-first grouping
  // and readiness counts are Task 7; this only establishes the container.
  function renderBundleList(payload: any): void {
    let list = document.getElementById('bundleList') as HTMLElement;
    if (!list) {
      list = document.createElement('div');
      list.id = 'bundleList';
      const scopeHeader = document.getElementById('scopeHeader');
      if (scopeHeader) {
        scopeHeader.parentElement!.insertBefore(list, scopeHeader);
      } else {
        content.appendChild(list);
      }
    }
    clear(list);
    (payload.bundles || []).forEach((b: any) => {
      const row = document.createElement('div');
      row.className = 'bundle-row';
      row.appendChild(document.createTextNode(b.label || b.id));
      list.appendChild(row);
    });
  }

  async function loadHealth(): Promise<void> {
    try {
      const res = await fetch('/api/system/health');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showBanner('could not load project health: ' + (body.error || res.status));
        return;
      }
      const payload = await res.json();
      renderHealthSummary(payload);
      renderBundleList(payload);
    } catch (err) {
      showBanner('could not load project health: ' + String(err));
    }
  }

  // Boot sequence.
  await loadScopes();
  setPickerClass(false);
  await loadHealth();
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
  } else {
    // Landing: no scope chosen, so the health summary + bundle list + the
    // existing tabs are the page. Python composes the projection; this only
    // renders it.
    content.hidden = false;
  }
}
