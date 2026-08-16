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
declare const renderFeature: (el: HTMLElement, payload: any) => void;
declare const renderVcycle: (el: HTMLElement, payload: any) => void;
declare const renderGoal: (el: HTMLElement, payload: any) => void;
declare const renderValidation: (el: HTMLElement, payload: any) => void;
declare const renderSim: (el: HTMLElement, payload: any) => void;
declare const renderNotApplicable: (panelId: string, note: string) => void;
declare const renderTabError: (panelId: string, note: string) => void;
declare const renderGuide: (guide: any) => void;
declare const renderGuideFallback: () => void;
declare const renderMatrix: (matrix: any) => void;
declare const renderReverse: (reverse: any) => void;
declare const renderStory: (story: any) => void;
declare const renderTimeline: (timeline: any) => void;
declare const renderTrace: (trace: any[]) => void;
declare const refChip: (raw: string) => HTMLElement;
declare const boundedList: (refs: string[], limit?: number) => HTMLElement;
declare const VOCABULARY: { terms: Record<string, any> };
declare const renderVocabularyPanel: () => void;
// Task 12: the label index (resolveLabel/setLabels) and the Next step block,
// both defined in system-comprehension.ts and embedded into the same
// page-scope IIFE, for the same declare-only reason as the bindings above.
declare const resolveLabel: (raw: string) => any | null;
declare const setLabels: (payload: any) => void;
declare const nextStepBlock: (state: string, subject?: string) => HTMLElement;

export async function systemBootstrap(): Promise<void> {
  const banner = document.getElementById('banner') as HTMLElement;
  const picker = document.getElementById('picker') as HTMLElement;
  const content = document.getElementById('content') as HTMLElement;
  const landingPanel = document.getElementById('landingPanel') as HTMLElement;
  const scopeWorkspace = document.getElementById('scopeWorkspace') as HTMLElement;
  const vocabularyPanel = document.getElementById('vocabularyPanel') as HTMLElement;
  const healthStatus = document.getElementById('healthStatus') as HTMLElement;
  const retryHealth = document.getElementById('retryHealth') as HTMLButtonElement;

  function showBanner(text: string): void {
    banner.textContent = text || '';
  }

  // Task 3 (system nav): shows/hides the #loading status row. With ok=true the
  // #loadedAt timestamp is stamped via a text node -- never innerHTML.
  function setLoading(on: boolean, ok?: boolean): void {
    const loading = document.getElementById('loading');
    if (loading) loading.hidden = !on;
    content.setAttribute('aria-busy', String(on));
    if (ok) {
      const loadedAt = document.getElementById('loadedAt');
      if (loadedAt) {
        loadedAt.textContent = '';
        loadedAt.appendChild(document.createTextNode(new Date().toLocaleTimeString()));
      }
    }
  }

  // Task B (system nav): the SR refs the current scope resolves to, the lazy
  // trace cache, and (SP-B Task 7) the health-payload bundles the sidebar
  // renders, captured for search's exact bundle-id/label match.
  let scopeSrRefs: string[] = [];
  let traceLoaded = false;
  let traceData: any = null;
  let healthBundles: any[] = [];
  let healthController: AbortController | null = null;
  let healthGeneration = 0;
  let scopeController: AbortController | null = null;
  let navigationGeneration = 0;
  const HEALTH_TIMEOUT_MS = 15_000;
  const TRAVERSAL_TIMEOUT_MS = 8_000;

  // Task 2 (system nav): the currently loaded scope ref (null until one loads).
  let currentScope: string | null = null;

  // Task 2 (system nav): records the active scope in the URL via pushState.
  function pushScope(ref: string): void {
    try {
      history.pushState({ scope: ref, tab: null }, '', location.pathname + '?scope=' + encodeURIComponent(ref));
    } catch {
      /* ignore: SPA URL is best-effort */
    }
  }

  function setPickerClass(focused: boolean): void {
    document.body.classList.toggle('focus', !!focused);
    document.body.classList.remove('picker-open');
    const toggle = document.getElementById('scopeToggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = 'Browse scopes';
    }
  }

  function setPickerOpen(open: boolean): void {
    document.body.classList.toggle('picker-open', open);
    const toggle = document.getElementById('scopeToggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? 'Close scopes' : 'Browse scopes';
    }
  }

  function showLanding(): void {
    landingPanel.hidden = false;
    scopeWorkspace.hidden = true;
    vocabularyPanel.hidden = true;
    setVocabularyPressed(false);
    content.setAttribute('aria-busy', 'false');
    currentScope = null;
    document.querySelectorAll('.scope-item, .feature-row').forEach((item: Element) => {
      item.classList.remove('is-active');
      item.removeAttribute('aria-current');
    });
    setPickerClass(false);
  }

  function showWorkspace(): void {
    landingPanel.hidden = true;
    scopeWorkspace.hidden = false;
    vocabularyPanel.hidden = true;
    setVocabularyPressed(false);
    setPickerClass(true);
  }

  // The vocabulary panel (visual addendum, "Vocabulary panel"): a full
  // workspace view, not a modal, wired to a header control so it's reachable
  // from anywhere. It replaces whichever of landing/workspace was showing;
  // toggling the control again (or navigating elsewhere) restores it.
  function setVocabularyPressed(pressed: boolean): void {
    const toggle = document.getElementById('vocabularyToggle');
    if (toggle) toggle.setAttribute('aria-pressed', String(pressed));
  }

  function showVocabulary(): void {
    landingPanel.hidden = true;
    scopeWorkspace.hidden = true;
    vocabularyPanel.hidden = false;
    setVocabularyPressed(true);
  }

  function isCurrentNavigation(generation: number, scopeRef: string): boolean {
    return generation === navigationGeneration && currentScope === scopeRef;
  }

  function invalidateHealth(): void {
    healthGeneration += 1;
    healthController?.abort();
    healthController = null;
  }

  function setHealthStatus(message: string, retry: boolean): void {
    healthStatus.textContent = message;
    healthStatus.hidden = message === '';
    retryHealth.hidden = !retry;
  }

  function scopeHref(ref: string): string {
    return '/system?scope=' + encodeURIComponent(ref);
  }

  function markActiveScope(scopeRef: string): void {
    document.querySelectorAll('.scope-item, .feature-row').forEach((item: Element) => {
      const active = item.getAttribute('href') === scopeHref(scopeRef);
      item.classList.toggle('is-active', active);
      if (active) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    });
  }

  // Task 12: the heading inversion. The page used to render the raw ref
  // (`task:T-001`) as the 40px headline with the real title buried in 14px
  // body text; this makes the label-index title the headline and moves the
  // ref down to monospace metadata, falling back to the raw ref only when
  // the index has nothing recorded for it. A bundle: scope keeps its
  // existing health-payload label as a fallback source (the label index may
  // not carry a bundle's `label` field in every deployment), so a bundle
  // scope never regresses to its raw ref while the index has the answer.
  function setScopeHeading(scopeRef: string): void {
    const kind = scopeKind(scopeRef);
    const bundle = kind === 'bundle'
      ? healthBundles.find((candidate) => candidate.id === scopeRef.slice('bundle:'.length))
      : null;
    const entry = resolveLabel(scopeRef);
    const title = (entry && entry.title) || bundle?.label || scopeRef;
    (document.getElementById('scopeKind') as HTMLElement).textContent = kind + ' scope';
    (document.getElementById('scopeHeader') as HTMLElement).textContent = title;
    (document.getElementById('scopeRef') as HTMLElement).textContent = scopeRef;
    renderScopeDescription(entry && entry.description ? entry.description : null);
    markActiveScope(scopeRef);
  }

  // The recorded description renders as a lead paragraph under the ref
  // metadata when present, and is removed (not left as an empty node) when
  // absent -- created on demand rather than reserved as static markup, the
  // same pattern traversalNode() below uses for its own optional element.
  function renderScopeDescription(description: string | null): void {
    let node = document.getElementById('scopeDescription') as HTMLElement | null;
    if (!description) {
      if (node) node.remove();
      return;
    }
    if (!node) {
      node = document.createElement('p');
      node.id = 'scopeDescription';
      node.className = 'scope-description';
      const ref = document.getElementById('scopeRef');
      if (ref) ref.after(node);
      else document.querySelector('.scope-heading')?.appendChild(node);
    }
    node.textContent = '';
    node.appendChild(document.createTextNode(description));
  }

  // SP-B Task 7: the feature-first sidebar. Python's `health` projection owns
  // bundle order, readiness, and counts; this only groups the rendered rows
  // under Weak/Medium/Strong headers (payload order within each group -- never
  // a client-side sort), with Weak expanded by default and Medium/Strong
  // collapsed but count-bearing, then the unbundled remainder at the bottom,
  // visible. Every readiness label sits beside the counts that produced it.
  function countsText(counts: any): string {
    const parts: string[] = [];
    if (counts && counts.sr_total !== undefined) {
      parts.push(String(counts.sr_total) + ' SR');
    }
    ['bound', 'covered', 'current', 'deferred', 'validated'].forEach((key: string) => {
      if (counts && counts[key] !== undefined) parts.push(String(counts[key]) + ' ' + key);
    });
    return parts.join(' · ');
  }

  function renderFeatureSidebar(payload: any): void {
    const list = document.getElementById('scopeList') as HTMLElement;
    clear(list);
    healthBundles = [];
    const bundles = payload.bundles || [];
    const groups: Record<string, any[]> = { weak: [], medium: [], strong: [] };
    bundles.forEach((b: any) => {
      healthBundles.push({ id: b.id, label: b.label });
      const bucket = groups[b.readiness];
      if (bucket) bucket.push(b);
    });
    ['weak', 'medium', 'strong'].forEach((readiness: string) => {
      const rows = groups[readiness] || [];
      if (!rows.length) return;
      const expanded = readiness === 'weak';
      const group = document.createElement('div');
      group.className = 'scope-group';
      group.dataset.readiness = readiness;
      group.dataset.expanded = String(expanded);
      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'scope-group-title';
      title.setAttribute('aria-expanded', String(expanded));
      title.appendChild(document.createTextNode(readiness.charAt(0).toUpperCase() + readiness.slice(1)));
      const groupCount = document.createElement('span');
      groupCount.className = 'readiness-counts';
      groupCount.appendChild(document.createTextNode('· ' + rows.length));
      title.appendChild(groupCount);
      group.appendChild(title);
      const rowEls: HTMLElement[] = [];
      rows.forEach((b: any) => {
        const row = document.createElement('div');
        row.className = 'scope-row';
        const a = document.createElement('a');
        a.className = 'scope-item';
        a.dataset.kind = 'bundle';
        a.href = scopeHref('bundle:' + b.id);
        // Two blocks, never one wrapping paragraph: the label on its own
        // line, the counts beneath it in mono (Task 12).
        const label = document.createElement('span');
        label.className = 'scope-label';
        label.appendChild(document.createTextNode(b.label || b.id));
        a.appendChild(label);
        const counts = document.createElement('span');
        counts.className = 'readiness-counts';
        counts.appendChild(document.createTextNode(countsText(b.readiness_counts)));
        a.appendChild(counts);
        a.addEventListener('click', (clickEvent: Event) => {
          clickEvent.preventDefault();
          void loadScope('bundle:' + b.id);
        });
        row.appendChild(a);
        group.appendChild(row);
        rowEls.push(row);
      });
      if (!expanded) {
        rowEls.forEach((row: HTMLElement) => { row.style.display = 'none'; });
      }
      title.addEventListener('click', () => {
        const nowExpanded = group.dataset.expanded !== 'true';
        group.dataset.expanded = String(nowExpanded);
        title.setAttribute('aria-expanded', String(nowExpanded));
        rowEls.forEach((row: HTMLElement) => { row.style.display = nowExpanded ? '' : 'none'; });
      });
      list.appendChild(group);
    });
    // The unbundled remainder: exactly the artifacts unreachable by browsing.
    // Shown, never hidden -- it is the reason the coverage gate exists.
    const unbundled = payload.unbundled || {};
    const unbundledRefs: string[] = [];
    Object.keys(unbundled).forEach((kind: string) => {
      (unbundled[kind] || []).forEach((ref: string) => unbundledRefs.push(ref));
    });
    if (unbundledRefs.length) {
      const group = document.createElement('div');
      group.className = 'scope-group';
      group.dataset.group = 'unbundled';
      group.dataset.expanded = 'true';
      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'scope-group-title';
      title.setAttribute('aria-expanded', 'true');
      title.appendChild(document.createTextNode('Unbundled'));
      group.appendChild(title);
      const rowEls: HTMLElement[] = [];
      unbundledRefs.forEach((ref: string) => {
        const row = document.createElement('div');
        row.className = 'scope-row';
        const a = document.createElement('a');
        a.className = 'scope-item';
        a.href = scopeHref(ref);
        a.appendChild(refChip(ref));
        a.addEventListener('click', (clickEvent: Event) => {
          clickEvent.preventDefault();
          void loadScope(ref);
        });
        row.appendChild(a);
        group.appendChild(row);
        rowEls.push(row);
      });
      title.addEventListener('click', () => {
        const nowExpanded = group.dataset.expanded !== 'true';
        group.dataset.expanded = String(nowExpanded);
        title.setAttribute('aria-expanded', String(nowExpanded));
        rowEls.forEach((row: HTMLElement) => { row.style.display = nowExpanded ? '' : 'none'; });
      });
      list.appendChild(group);
    }
  }

  // Search filters the rendered sidebar in place (visibility only, never
  // reorder): a typed query reveals matching rows in any group (search is the
  // primary control), hides non-matching rows, and hides groups with no match.
  // With an empty query the groups go back to their disclosure state.
  const scopeFilter = document.getElementById('scopeFilter') as HTMLInputElement;
  const scopeList = document.getElementById('scopeList') as HTMLElement;
  const scopeToggle = document.getElementById('scopeToggle') as HTMLElement;

  function applyScopeFilter(): void {
    const q = scopeFilter.value.trim().toLowerCase();
    scopeList.querySelectorAll('.scope-group').forEach((group: Element) => {
      const expanded = (group as HTMLElement).dataset.expanded === 'true';
      let anyVisible = false;
      group.querySelectorAll('.scope-row').forEach((row: Element) => {
        const matches = !q || !!(row.textContent && row.textContent.toLowerCase().includes(q));
        const show = q ? matches : expanded;
        (row as HTMLElement).style.display = show ? '' : 'none';
        if (show) anyVisible = true;
      });
      (group as HTMLElement).style.display = q ? (anyVisible ? '' : 'none') : '';
    });
  }
  scopeFilter.addEventListener('input', applyScopeFilter);

  // SP-B Task 7: the Go button resolves the search term to a scope and opens
  // it. Resolution is exact/case-sensitive, matching `parse_scope_ref`: a
  // bundle id/label match opens that bundle straight from the payload (a
  // filter over the payload, no matching logic of its own); a bare artifact
  // id gets the right kind prefix (`SR-137` -> `sr:SR-137`); a typed
  // `kind:ref` is posted verbatim. No fuzzy matching.
  async function searchGo(): Promise<void> {
    const q = scopeFilter.value.trim();
    if (!q) return;
    // A bundle id/label match in the health payload opens that bundle (the
    // payload is the only matching surface the browser is allowed to filter).
    const bundle = healthBundles.find((b) => b.id === q || b.label === q);
    if (bundle) {
      await loadScope('bundle:' + bundle.id);
      return;
    }
    // Otherwise the term is an artifact ref: a bare id gets its kind prefix,
    // a typed ref is posted verbatim -- both as the exact ref.
    const ref = q.indexOf(':') !== -1 ? q : 'sr:' + q;
    await loadScope(ref);
  }
  (document.getElementById('searchGo') as HTMLElement).onclick = () => {
    searchGo();
  };
  scopeFilter.addEventListener('keydown', (event: KeyboardEvent) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    void searchGo();
  });

  // The toggle re-opens the collapsed list (removes body.focus).
  if (scopeToggle) {
    scopeToggle.addEventListener('click', () => {
      setPickerOpen(!document.body.classList.contains('picker-open'));
    });
  }

  // VOCABULARY is static page-scope data (Task 8), so the panel content can
  // be rendered once up front rather than on first open.
  renderVocabularyPanel();
  const vocabularyToggle = document.getElementById('vocabularyToggle');
  if (vocabularyToggle) {
    vocabularyToggle.addEventListener('click', () => {
      if (vocabularyPanel.hidden) {
        showVocabulary();
      } else if (currentScope) {
        showWorkspace();
      } else {
        showLanding();
      }
    });
  }

  const TAB_ORDER = ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace', 'Feature', 'Vcycle', 'Goal', 'Validation', 'Sim'];
  const TABS_BY_KIND: Record<string, string[]> = {
    bundle: ['Brief', 'Matrix', 'Timeline', 'Guide', 'Trace'],
    sr: ['Brief', 'Vcycle', 'Validation', 'Matrix', 'Timeline', 'Guide', 'Trace'],
    feat: ['Feature', 'Vcycle', 'Matrix', 'Timeline', 'Guide', 'Trace'],
    task: ['Story'],
    file: ['Reverse'],
    goal: ['Goal'],
    sim: ['Sim'],
  };

  function configureTabs(kind: string): void {
    const available = TABS_BY_KIND[kind] || TABS_BY_KIND.bundle!;
    TAB_ORDER.forEach((name: string) => {
      const tab = document.getElementById('tab' + name) as HTMLElement;
      const panel = document.getElementById('panel' + name) as HTMLElement;
      const included = available.includes(name);
      tab.hidden = !included;
      tab.setAttribute('aria-hidden', String(!included));
      if (!included) {
        tab.setAttribute('aria-selected', 'false');
        tab.setAttribute('tabindex', '-1');
        panel.hidden = true;
      }
    });
  }

  function showTab(name: string, updateUrl = true): void {
    const selected = document.getElementById('tab' + name) as HTMLElement | null;
    if (!selected || selected.hidden) return;
    TAB_ORDER.forEach((tab) => {
      const tabNode = document.getElementById('tab' + tab) as HTMLElement;
      const active = tab === name && !tabNode.hidden;
      tabNode.setAttribute('aria-selected', String(active));
      tabNode.setAttribute('tabindex', active ? '0' : '-1');
      (document.getElementById('panel' + tab) as HTMLElement).hidden = !active;
    });
    // Keep the active tab in the URL hash (replaceState, not pushState, so tab
    // switching does not pad the back-stack).
    if (updateUrl) {
      try {
        history.replaceState(
          { scope: currentScope, tab: name.toLowerCase() },
          '',
          location.pathname + location.search + '#' + name.toLowerCase()
        );
      } catch {
        /* ignore: hash update is best-effort */
      }
    }
  }

  // Picks the boot tab from the URL hash when it names a valid tab, else the
  // scope kind's default tab.
  function selectInitialTab(kindDefault: string, updateUrl = true): string {
    const hash = (location.hash || '').replace('#', '').toLowerCase();
    const names: Record<string, string> = { brief: 'Brief', feature: 'Feature', vcycle: 'Vcycle', goal: 'Goal', validation: 'Validation', sim: 'Sim', matrix: 'Matrix', timeline: 'Timeline', guide: 'Guide', story: 'Story', reverse: 'Reverse', trace: 'Trace' };
    const requested = names[hash];
    const requestedTab = requested ? document.getElementById('tab' + requested) as HTMLElement : null;
    const selected = requestedTab && !requestedTab.hidden ? requested! : kindDefault;
    showTab(selected, updateUrl);
    return selected;
  }

  (document.getElementById('tabBrief') as HTMLElement).onclick = () => showTab('Brief');
  (document.getElementById('tabFeature') as HTMLElement).onclick = () => showTab('Feature');
  (document.getElementById('tabVcycle') as HTMLElement).onclick = () => showTab('Vcycle');
  (document.getElementById('tabGoal') as HTMLElement).onclick = () => showTab('Goal');
  (document.getElementById('tabValidation') as HTMLElement).onclick = () => showTab('Validation');
  (document.getElementById('tabSim') as HTMLElement).onclick = () => showTab('Sim');
  (document.getElementById('tabMatrix') as HTMLElement).onclick = () => showTab('Matrix');
  (document.getElementById('tabTimeline') as HTMLElement).onclick = () => showTab('Timeline');
  (document.getElementById('tabGuide') as HTMLElement).onclick = () => showTab('Guide');
  (document.getElementById('tabStory') as HTMLElement).onclick = () => showTab('Story');
  (document.getElementById('tabReverse') as HTMLElement).onclick = () => showTab('Reverse');
  (document.getElementById('tabTrace') as HTMLElement).onclick = () => {
    showTab('Trace');
    if (currentScope) void loadTrace(navigationGeneration, currentScope, scopeController?.signal);
  };

  // The Refresh button re-runs the current scope's load in place.
  (document.getElementById('refresh') as HTMLElement).onclick = () => {
    if (currentScope) void loadScope(currentScope, false, false);
  };

  // Task 4 (system nav): keyboard shortcuts + scope-list arrow navigation.
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && /^[0-9]$/.test(e.key)) {
      showTab(TAB_ORDER[Number(e.key) - 1]!);
      e.preventDefault();
      return;
    }
    const tabTarget = e.target instanceof HTMLElement ? e.target.closest('.tab') as HTMLElement | null : null;
    if (tabTarget && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
      const visibleTabs = TAB_ORDER
        .map((name) => document.getElementById('tab' + name) as HTMLElement)
        .filter((tab) => !tab.hidden);
      const current = visibleTabs.indexOf(tabTarget);
      if (current === -1 || !visibleTabs.length) return;
      e.preventDefault();
      let nextIndex = current;
      if (e.key === 'Home') nextIndex = 0;
      else if (e.key === 'End') nextIndex = visibleTabs.length - 1;
      else nextIndex = (current + (e.key === 'ArrowRight' ? 1 : -1) + visibleTabs.length) % visibleTabs.length;
      const next = visibleTabs[nextIndex]!;
      next.focus();
      showTab(next.getAttribute('aria-label') || next.textContent || '');
      return;
    }
    const el = (e.target instanceof HTMLElement && e.target.closest('.scope-item')) ? e.target : null;
    if (el && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      const items = Array.from(scopeList.querySelectorAll('.scope-item'))
        .filter((item) => {
          const node = item as HTMLElement;
          const row = node.closest('.scope-row') as HTMLElement | null;
          const group = node.closest('.scope-group') as HTMLElement | null;
          return !node.hidden && node.style.display !== 'none' &&
            row?.style.display !== 'none' && group?.style.display !== 'none';
        });
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

  function defaultTab(kind: string): string {
    if (kind === 'task') return 'Story';
    if (kind === 'file') return 'Reverse';
    if (kind === 'goal') return 'Goal';
    if (kind === 'sim') return 'Sim';
    if (kind === 'feat') return 'Feature';
    return 'Brief';
  }

  function resetScopeEvidence(scopeRef: string): void {
    const kind = scopeKind(scopeRef);
    scopeSrRefs = kind === 'sr' ? [scopeRef] : [];
    traceLoaded = false;
    traceData = null;
    TAB_ORDER.forEach((tab) => clear(document.getElementById('panel' + tab) as HTMLElement));
    if (kind === 'task' || kind === 'file') {
      renderTraversalStatus('Traversal is not applicable for this scope.');
      renderNotApplicable(
        'panelTrace',
        'Not applicable for this scope. See the Story or Reverse tab.'
      );
    } else {
      renderTraversalStatus('Loading traversal for this scope…');
      renderNotApplicable('panelTrace', 'Trace map has not been loaded for this scope.');
    }
  }

  async function responseFailure(res: Response): Promise<string> {
    const body = await res.json().catch(() => ({}));
    return String(body.error || res.status);
  }

  async function loadStoryScope(
    scopeRef: string,
    generation: number,
    signal: AbortSignal,
    updateUrl: boolean
  ): Promise<void> {
    const res = await fetch('/api/system/story?scope=' + encodeURIComponent(scopeRef), { signal });
    if (!res.ok) throw new Error(await responseFailure(res));
    const story = await res.json();
    if (!isCurrentNavigation(generation, scopeRef)) return;
    renderStory(story);
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Reverse', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a task: scope. See the Story tab.'
    ));
    configureTabs('task');
    selectInitialTab('Story', updateUrl);
    setLoading(false, true);
  }

  async function loadReverseScope(
    scopeRef: string,
    generation: number,
    signal: AbortSignal,
    updateUrl: boolean
  ): Promise<void> {
    const res = await fetch('/api/system/reverse?scope=' + encodeURIComponent(scopeRef), { signal });
    if (!res.ok) throw new Error(await responseFailure(res));
    const reverse = await res.json();
    if (!isCurrentNavigation(generation, scopeRef)) return;
    renderReverse(reverse);
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Trace'].forEach((tab) => renderNotApplicable(
      'panel' + tab, 'Not applicable for a file: scope. See the Reverse tab.'
    ));
    configureTabs('file');
    selectInitialTab('Reverse', updateUrl);
    setLoading(false, true);
  }

  async function loadBundleScope(
    scopeRef: string,
    generation: number,
    signal: AbortSignal,
    updateUrl: boolean
  ): Promise<void> {
    const scopeParam = encodeURIComponent(scopeRef);
    // The guide fetch is intentionally not in the failure gate below: a
    // failed/unavailable guide degrades only its own tab.
    const [briefRes, matrixRes, timelineRes, guideRes] = await Promise.all([
      fetch('/api/system/brief?scope=' + scopeParam, { signal }),
      fetch('/api/system/matrix?scope=' + scopeParam, { signal }),
      fetch('/api/system/timeline?scope=' + scopeParam, { signal }),
      fetch('/api/system/guide?scope=' + scopeParam, { signal }),
    ]);
    const failed = [briefRes, matrixRes, timelineRes].find((r) => !r.ok);
    if (failed) throw new Error(await responseFailure(failed));
    const [brief, matrix, timeline, guide] = await Promise.all([
      briefRes.json(), matrixRes.json(), timelineRes.json(),
      guideRes.ok ? guideRes.json() : Promise.resolve(null),
    ]);
    if (!isCurrentNavigation(generation, scopeRef)) return;
    // Inc 6 Task 1: a feat: scope's brief IS the trace-backed dossier
    // (factory.system cmd_brief dispatches feat: to query_feature_context),
    // so the same payload renders the Feature tab -- the dossier hub. The
    // claim-based brief panel does not apply to a feat: scope (the payload
    // carries no claims), so it is never rendered for one.
    if (scopeKind(scopeRef) === 'feat') {
      renderFeature(document.getElementById('panelFeature') as HTMLElement, brief);
    } else {
      renderBrief(brief);
    }
    renderMatrix(matrix);
    renderTimeline(timeline);
    if (guide) renderGuide(guide);
    else renderGuideFallback();
    renderNotApplicable('panelStory', 'Not applicable for a bundle:/sr: scope. See the Story tab for a task: scope.');
    renderNotApplicable('panelReverse', 'Not applicable for a bundle:/sr: scope. See the Reverse tab for a file: scope.');
    // Inc 6 Task 2: the interactive V-cycle for feat:/sr: scopes. Best-effort
    // like the guide -- a failure degrades only the V-cycle tab, never the
    // scope load.
    if (scopeKind(scopeRef) === 'feat' || scopeKind(scopeRef) === 'sr') {
      try {
        const vcycleRes = await fetch('/api/system/vcycle?scope=' + scopeParam, { signal });
        if (!vcycleRes.ok) throw new Error(String(vcycleRes.status));
        const vcycle = await vcycleRes.json();
        if (isCurrentNavigation(generation, scopeRef)) {
          renderVcycle(document.getElementById('panelVcycle') as HTMLElement, vcycle);
        }
      } catch {
        if (isCurrentNavigation(generation, scopeRef)) {
          renderTabError('panelVcycle', 'The V-cycle view is unavailable for this scope.');
        }
      }
    } else {
      renderNotApplicable('panelVcycle', 'The V-cycle tab applies to feat: and sr: scopes only.');
    }
    // Inc 6 Task 4: the validation evidence tab for sr: scopes. Best-effort
    // like the vcycle fetch -- a failure degrades only its own tab.
    if (scopeKind(scopeRef) === 'sr') {
      try {
        const validationRes = await fetch('/api/system/validation?scope=' + scopeParam, { signal });
        if (!validationRes.ok) throw new Error(String(validationRes.status));
        const validation = await validationRes.json();
        if (isCurrentNavigation(generation, scopeRef)) {
          renderValidation(document.getElementById('panelValidation') as HTMLElement, validation);
        }
      } catch {
        if (isCurrentNavigation(generation, scopeRef)) {
          renderTabError('panelValidation', 'The validation evidence view is unavailable for this scope.');
        }
      }
    } else {
      renderNotApplicable('panelValidation', 'The Validation tab applies to sr: scopes only.');
    }
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
    // SP-B Task 9: working traversal for this sr:/bundle: scope (best-effort;
    // a missing/unavailable endpoint degrades only the #traversalPath node).
    const traversalController = new AbortController();
    const cancelTraversal = () => traversalController.abort();
    signal.addEventListener('abort', cancelTraversal, { once: true });
    const traversalTimeout = window.setTimeout(
      () => traversalController.abort(),
      TRAVERSAL_TIMEOUT_MS
    );
    try {
      const travRes = await fetch('/api/system/traversal?scope=' + scopeParam, {
        signal: traversalController.signal,
      });
      if (!travRes.ok) throw new Error(String(travRes.status));
      const traversal = await travRes.json();
      if (isCurrentNavigation(generation, scopeRef)) renderTraversal(traversal);
    } catch {
      if (isCurrentNavigation(generation, scopeRef)) {
        renderTraversalStatus('Traversal is unavailable for this scope.');
      }
    } finally {
      window.clearTimeout(traversalTimeout);
      signal.removeEventListener('abort', cancelTraversal);
    }
    if (!isCurrentNavigation(generation, scopeRef)) return;
    const selectedTab = selectInitialTab(defaultTab(scopeKind(scopeRef)), updateUrl);
    if (selectedTab === 'Trace') await loadTrace(generation, scopeRef, signal);
    if (!isCurrentNavigation(generation, scopeRef)) return;
    setLoading(false, true);
  }

  async function loadGoalScope(
    scopeRef: string,
    generation: number,
    signal: AbortSignal,
    updateUrl: boolean
  ): Promise<void> {
    // Inc 6 Task 3: goal: scopes present the eng_get_goal projection on the
    // Goal tab. A goal id that no file declares is a scope error, surfaced
    // by the loadScope catch like any other unresolved scope.
    const goalId = scopeRef.split(':', 2)[1] ?? scopeRef;
    const res = await fetch('/api/system/goal?id=' + encodeURIComponent(goalId), { signal });
    if (!res.ok) throw new Error(await responseFailure(res));
    const goal = await res.json();
    if (!isCurrentNavigation(generation, scopeRef)) return;
    renderGoal(document.getElementById('panelGoal') as HTMLElement, goal);
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace', 'Feature', 'Vcycle'].forEach(
      (tab) => renderNotApplicable(
        'panel' + tab, 'Not applicable for a goal: scope. See the Goal tab.'
      )
    );
    configureTabs('goal');
    selectInitialTab('Goal', updateUrl);
    setLoading(false, true);
  }

  async function loadSimScope(
    scopeRef: string,
    generation: number,
    signal: AbortSignal,
    updateUrl: boolean
  ): Promise<void> {
    // Inc 6 Task 5: sim:RUN-... scopes present the run's summary on the
    // Simulation tab. Runs are evidence, not listed scopes, so they are
    // reached by URL or by navigation from the dossier/goal evidence.
    const runId = scopeRef.split(':', 2)[1] ?? scopeRef;
    const res = await fetch('/api/system/sim/run?id=' + encodeURIComponent(runId), { signal });
    if (!res.ok) throw new Error(await responseFailure(res));
    const run = await res.json();
    if (!isCurrentNavigation(generation, scopeRef)) return;
    renderSim(document.getElementById('panelSim') as HTMLElement, run);
    ['Brief', 'Matrix', 'Timeline', 'Guide', 'Story', 'Reverse', 'Trace', 'Feature', 'Vcycle', 'Goal', 'Validation'].forEach(
      (tab) => renderNotApplicable(
        'panel' + tab, 'Not applicable for a sim: scope. See the Simulation tab.'
      )
    );
    configureTabs('sim');
    selectInitialTab('Sim', updateUrl);
    setLoading(false, true);
  }

  async function loadScope(scopeRef: string, pushHistory = true, updateUrl = true): Promise<void> {
    invalidateHealth();
    const generation = ++navigationGeneration;
    scopeController?.abort();
    const controller = new AbortController();
    scopeController = controller;
    currentScope = scopeRef;
    if (pushHistory) pushScope(scopeRef);
    const kind = scopeKind(scopeRef);
    showBanner('');
    configureTabs(kind);
    resetScopeEvidence(scopeRef);
    showWorkspace();
    setScopeHeading(scopeRef);
    selectInitialTab(defaultTab(kind), updateUrl);
    setLoading(true);
    try {
      if (kind === 'task') {
        await loadStoryScope(scopeRef, generation, controller.signal, updateUrl);
        return;
      }
      if (kind === 'file') {
        await loadReverseScope(scopeRef, generation, controller.signal, updateUrl);
        return;
      }
      if (kind === 'goal') {
        await loadGoalScope(scopeRef, generation, controller.signal, updateUrl);
        return;
      }
      if (kind === 'sim') {
        await loadSimScope(scopeRef, generation, controller.signal, updateUrl);
        return;
      }
      await loadBundleScope(scopeRef, generation, controller.signal, updateUrl);
    } catch (err) {
      if (!isCurrentNavigation(generation, scopeRef)) return;
      showBanner('could not resolve scope ' + scopeRef + ': ' + String(err));
      picker.hidden = false;
      showLanding();
      setLoading(false);
    }
  }

  // Task B (system nav): the lazy trace loader. Fetches /api/graph only on the
  // first click of the Trace tab (never during scope load). Lives here because
  // it reads bootstrap state.
  async function loadTrace(
    generation: number,
    scopeRef: string,
    signal?: AbortSignal
  ): Promise<void> {
    if (!isCurrentNavigation(generation, scopeRef)) return;
    if (!scopeSrRefs.length) {
      const pending = content.getAttribute('aria-busy') === 'true';
      renderNotApplicable(
        'panelTrace',
        pending
          ? 'Trace will load after current-scope evidence resolves.'
          : 'No trace recorded for this scope. See the Brief, Story, or Reverse tabs.'
      );
      return;
    }
    if (traceLoaded) {
      renderTrace(invertTraceForScope(traceData, scopeSrRefs));
      return;
    }
    const refs = scopeSrRefs.slice();
    try {
      const res = await fetch('/api/graph', signal ? { signal } : undefined);
      if (!res.ok) throw new Error('graph fetch failed');
      const graph = await res.json();
      if (!isCurrentNavigation(generation, scopeRef)) return;
      traceData = graph;
      traceLoaded = true;
      renderTrace(invertTraceForScope(traceData, refs));
    } catch (err) {
      if (isCurrentNavigation(generation, scopeRef)) {
        renderNotApplicable('panelTrace', 'Trace map is unavailable for this scope. See the Brief, Story, or Reverse tabs.');
      }
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
    const overall = document.createElement('div');
    overall.className = 'health-overall';
    if (h.expected === 0) {
      overall.appendChild(document.createTextNode('No measurable evidence · 0 / 0'));
    } else {
      overall.appendChild(document.createTextNode(
        'Overall ' + h.satisfied + '/' + h.expected + ' satisfied · ' + h.percent + '%'
      ));
    }
    summary.appendChild(overall);
    const metrics = document.createElement('div');
    metrics.className = 'health-metrics';
    (h.classes || []).forEach((c: any) => {
      const line = document.createElement('div');
      line.className = 'health-metric';
      const term = VOCABULARY && VOCABULARY.terms ? VOCABULARY.terms[c.name] : null;
      const label = document.createElement('span');
      label.className = 'health-metric-label';
      label.appendChild(document.createTextNode(term ? term.label : c.name));
      const raw = document.createElement('span');
      raw.className = 'health-metric-raw';
      raw.appendChild(document.createTextNode(c.name));
      const ratio = document.createElement('strong');
      ratio.appendChild(document.createTextNode(c.satisfied + '/' + c.expected));
      line.appendChild(label);
      line.appendChild(raw);
      line.appendChild(ratio);
      metrics.appendChild(line);
    });
    summary.appendChild(metrics);
  }

  // Minimal Task 6 bundle list (label per bundle). The feature-first grouping
  // and readiness counts are Task 7; this only establishes the container.
  // SP-B Task 9: working traversal -- requirement -> satisfying tasks -> design
  // decisions -> changed files, rendered from `factory.system traversal --json`
  // (non-fatal: a failure degrades only this node). Text nodes only.
  function traversalNode(): HTMLElement {
    let node = document.getElementById('traversalPath') as HTMLElement | null;
    if (!node) {
      node = document.createElement('div');
      node.id = 'traversalPath';
      node.className = 'traversal-path';
      const meta = document.querySelector('.scope-meta');
      if (meta) {
        meta.after(node);
      } else {
        document.getElementById('content')?.appendChild(node);
      }
    }
    return node;
  }

  function renderTraversalStatus(message: string): void {
    const node = traversalNode();
    clear(node);
    const status = document.createElement('div');
    status.className = 'empty traversal-status';
    status.appendChild(document.createTextNode(message));
    node.appendChild(status);
  }

  function renderTraversal(trav: any): void {
    const node = traversalNode();
    clear(node);
    function addStep(label: string, values: string[]): void {
      const step = document.createElement('div');
      step.className = 'trace-spine-step';
      const stepLabel = document.createElement('div');
      stepLabel.className = 'trace-spine-label';
      stepLabel.appendChild(document.createTextNode(label));
      const stepValue = document.createElement('div');
      stepValue.className = 'trace-spine-value';
      if (values && values.length) {
        stepValue.appendChild(boundedList(values));
      } else {
        stepValue.appendChild(document.createTextNode('Not recorded'));
      }
      step.appendChild(stepLabel);
      step.appendChild(stepValue);
      node.appendChild(step);
    }
    addStep('Requirement', trav.requirement);
    addStep('Tasks', trav.tasks);
    addStep('Design', trav.design);
    addStep('Files', trav.files);
  }

  // Task 12: a brand-new project has zero bundles, and an empty directory
  // gives it nothing to read. The first-run card names what a bundle is and
  // why the directory is empty, followed by its one Next step (visual
  // addendum, "Empty states and first run").
  function renderBundleList(payload: any): void {
    const list = document.getElementById('bundleList') as HTMLElement;
    clear(list);
    const bundles = payload.bundles || [];
    if (!bundles.length) {
      const card = document.createElement('div');
      card.className = 'first-run-card presence-rail is-absent';
      const heading = document.createElement('p');
      heading.className = 'first-run-heading';
      heading.appendChild(document.createTextNode('No features defined yet.'));
      card.appendChild(heading);
      const body = document.createElement('p');
      body.appendChild(document.createTextNode(
        'A feature bundle groups the requirements, tasks, and decisions you read '
        + 'together to understand one part of the system. Bundles are how this '
        + 'project is browsed, so until one exists the directory stays empty.'
      ));
      card.appendChild(body);
      card.appendChild(nextStepBlock('no_bundles'));
      list.appendChild(card);
      return;
    }
    bundles.forEach((b: any) => {
      const row = document.createElement('a');
      row.className = 'feature-row readiness-' + b.readiness;
      row.href = scopeHref('bundle:' + b.id);
      row.dataset.readiness = b.readiness;
      const heading = document.createElement('strong');
      heading.appendChild(document.createTextNode(b.label || b.id));
      const readiness = document.createElement('span');
      readiness.className = 'feature-readiness';
      readiness.appendChild(document.createTextNode(b.readiness));
      const members = document.createElement('span');
      members.className = 'feature-members';
      members.appendChild(document.createTextNode(String(b.members) + ' artifacts'));
      const counts = document.createElement('span');
      counts.className = 'readiness-counts';
      counts.appendChild(document.createTextNode(countsText(b.readiness_counts)));
      row.appendChild(heading);
      row.appendChild(readiness);
      row.appendChild(members);
      row.appendChild(counts);
      row.addEventListener('click', (clickEvent: Event) => {
        clickEvent.preventDefault();
        void loadScope('bundle:' + b.id);
      });
      list.appendChild(row);
    });
  }

  async function loadHealth(): Promise<boolean> {
    healthController?.abort();
    const controller = new AbortController();
    const generation = ++healthGeneration;
    healthController = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, HEALTH_TIMEOUT_MS);
    content.setAttribute('aria-busy', 'true');
    setHealthStatus('Reading project evidence…', false);
    try {
      const res = await fetch('/api/system/health', { signal: controller.signal });
      if (!res.ok) {
        throw new Error(String(res.status));
      }
      const payload = await res.json();
      if (generation !== healthGeneration || healthController !== controller) return false;
      renderHealthSummary(payload);
      renderBundleList(payload);
      renderFeatureSidebar(payload);
      setHealthStatus('', false);
      showBanner('');
      showLanding();
    } catch (err) {
      if (generation !== healthGeneration || healthController !== controller) return false;
      showLanding();
      if (timedOut) {
        setHealthStatus(
          'Project evidence is taking longer than expected. The scan was stopped; retry when ready.',
          true
        );
      } else {
        setHealthStatus(
          'Project evidence is unavailable. The navigator is still running; retry the health scan.',
          true
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (healthController === controller) healthController = null;
    }
    return generation === healthGeneration;
  }

  retryHealth.addEventListener('click', () => { void loadHealth(); });

  function restoreLocation(): void {
    const scopeRef = new URLSearchParams(window.location.search).get('scope');
    if (scopeRef) {
      void loadScope(scopeRef, false, false);
      return;
    }
    navigationGeneration += 1;
    scopeController?.abort();
    scopeController = null;
    showBanner('');
    showLanding();
    setLoading(false);
  }

  window.addEventListener('popstate', restoreLocation);

  // Task 12: the dismissible landing orientation strip, one localStorage key.
  // Read is best-effort -- a browser with storage disabled just keeps showing
  // the strip rather than throwing.
  const ORIENTATION_DISMISSED_KEY = 'system-nav-orientation-dismissed';
  const orientationStrip = document.getElementById('orientationStrip') as HTMLElement | null;
  const orientationDismiss = document.getElementById('orientationDismiss') as HTMLElement | null;
  if (orientationStrip) {
    let dismissed = false;
    try {
      dismissed = window.localStorage.getItem(ORIENTATION_DISMISSED_KEY) === '1';
    } catch {
      /* storage unavailable -- default to showing it */
    }
    orientationStrip.hidden = dismissed;
  }
  if (orientationDismiss) {
    orientationDismiss.addEventListener('click', () => {
      if (orientationStrip) orientationStrip.hidden = true;
      try {
        window.localStorage.setItem(ORIENTATION_DISMISSED_KEY, '1');
      } catch {
        /* best-effort persistence only */
      }
    });
  }

  // Boot sequence: the landing page opens on the health projection (summary,
  // bundle list, feature-first sidebar); scope choice navigates into focus
  // mode. The sidebar renders from the health payload -- `list_scopes` is no
  // longer fetched by the client.
  //
  // Task 12: the label index is fetched and awaited BEFORE health, so
  // renderFeatureSidebar (which resolves refs via LABELS/ALIASES) never
  // renders bare and then reflows once labels arrive. A failed/absent fetch
  // resolves to null; setLabels(null) leaves LABELS/ALIASES empty and marks
  // the index unavailable -- the surface degrades (every chip's absent-ref
  // treatment), it never blanks.
  setPickerClass(false);
  const labelsPromise = fetch('/api/system/labels')
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  setLabels(await labelsPromise);
  const healthOwnsLanding = await loadHealth();
  if (!healthOwnsLanding) return;
  const requestedScope = new URLSearchParams(window.location.search).get('scope');
  if (requestedScope) {
    try {
      await loadScope(requestedScope, false, false);
    } catch (err) {
      showBanner('could not resolve scope ' + requestedScope + ': ' + String(err));
      picker.hidden = false;
      showLanding();
      setLoading(false);
    }
  } else {
    // Landing: no scope chosen, so the health summary + bundle list + the
    // existing tabs are the page. Python composes the projection; this only
    // renders it.
    showLanding();
  }
}
