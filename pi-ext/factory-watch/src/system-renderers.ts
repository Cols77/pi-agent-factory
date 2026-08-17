// SP-B Task 5 split — per-tab renderers.
//
// This module holds the pure DOM renderer functions that the `/system` client
// script uses. Each function builds DOM nodes from a payload it is handed; none
// of them fetches, sorts, filters by freshness, or decides ordering —
// "Python computes, this only renders" applies to every function here. They
// MAY read the frozen page-scope lookups (LABELS, ALIASES, VOCABULARY,
// REMEDIATION), which are data Python computed, not state this file owns.
// The document is reached through the global `document` (these run inside
// the page's inline <script>), and `clear` is the page helper that empties a
// panel before the renderer repopulates it.
//
// NOTE: these are embedded into the page's inline <script> via
// `Function.prototype.toString()` (see system-shell.ts), so they must be plain
// function declarations/expressions with no reliance on module-scoped imports
// except each other (which the shell defines into the same scope first).

/* eslint-disable no-undef */

// refChip/boundedList are defined by system-comprehension.ts and embedded
// into the same page-scope IIFE as these renderers (see system-shell.ts's
// clientSource()); referenced here as free variables, the same convention
// system-bootstrap.ts uses for its cross-file renderer calls, so that
// Function.prototype.toString() keeps emitting a plain, import-free function
// body for the inline <script>.
declare const refChip: (raw: string) => HTMLElement;
declare const boundedList: (refs: string[], limit?: number) => HTMLElement;
// glossFor/definitionTrigger are defined by system-comprehension.ts and
// embedded into the same page-scope IIFE as these renderers (see
// system-shell.ts's clientSource()); referenced here as free variables for
// the same reason refChip/boundedList are above.
declare const glossFor: (term: string) => HTMLElement | null;
declare const definitionTrigger: (term: string) => HTMLElement | null;
// REMEDIATION/nextStepBlock are Task 12 additions from system-comprehension.ts,
// embedded into the same page-scope IIFE for the same reason as the others
// above. Severity styling (`presence-rail is-absent`) applies only to the
// browser-decided empty states below -- the explicit `if (!x.length)`
// branches -- never to the free-text `degraded:` banner, which the browser
// cannot classify without interpreting its reasons.
declare const nextStepBlock: (state: string, subject?: string) => HTMLElement;

export function clear(el: HTMLElement): void {
  el.innerHTML = '';
}

// The plain badge, exactly as it always rendered -- no gloss, no trigger.
// badge() wraps this; the definition card and vocabulary panel also reuse it
// directly so "the real badge" they show is this literal element, not a
// lookalike.
export function badgeSpan(text: string, extraClass: string): HTMLElement {
  const el = document.createElement('span');
  el.className = 'badge' + (extraClass ? ' ' + extraClass : '');
  el.appendChild(document.createTextNode(text));
  return el;
}

// Wraps a badge/freshness element in a `.badge-wrap` that adds the inline
// gloss line and the ⓘ definition trigger when `term` has a VOCABULARY entry
// (visual addendum, "Badge with gloss"). A term with no entry is returned
// completely unchanged -- same element, same class, no wrapper -- so a badge
// callers already depend on structurally (renderClaim/renderMatrixRow/
// renderTimelineEvent/renderStoryRun all `appendChild` this return value
// directly) never regresses when the vocabulary has nothing to say.
export function withGloss(el: HTMLElement, term: string): HTMLElement {
  const gloss = glossFor(term);
  if (!gloss) return el;
  const wrap = document.createElement('span');
  wrap.className = 'badge-wrap';
  wrap.appendChild(el);
  const trigger = definitionTrigger(term);
  if (trigger) wrap.appendChild(trigger);
  wrap.appendChild(gloss);
  return wrap;
}

// badge() keeps its exact contract word as the text of a pristine
// `<span class="badge">` -- every existing caller and every existing test
// that asserts `.badge` structure/text directly keeps working unchanged,
// because that span is always present at the same depth relative to itself.
// It only grows a `.badge-wrap` ancestor when VOCABULARY has a gloss for the
// word, which `.querySelector('.badge')` sees straight through.
export function badge(text: string, extraClass: string): HTMLElement {
  return withGloss(badgeSpan(text, extraClass), text);
}

// Freshness is always rendered as its own literal state word (fresh / stale /
// degraded / n/a) -- the CSS class only adds colour on top of that text, it
// never stands in for it (design section 6.3). Same wrap-only-when-glossed
// rule as badge() above.
export function freshnessBadge(freshness: any): HTMLElement {
  const el = document.createElement('span');
  el.className = 'freshness freshness-' + freshness.state.replace('/', '-');
  el.appendChild(document.createTextNode(freshness.state));
  if (freshness.reason) el.title = freshness.reason;
  return withGloss(el, freshness.state);
}

export function citationLine(citation: any): HTMLElement {
  const el = document.createElement('div');
  el.className = 'citation';
  let text = citation.kind + ': ' + citation.path;
  if (citation.anchor) text += ' #' + citation.anchor;
  el.appendChild(document.createTextNode(text));
  return el;
}

// Renders the implementation_summary: run count, latest outcome, changed-file
// count, latest validation -- attached only to a bundle task: member claim.
// Every field is rendered plainly, including null (never a blank cell or a
// zero). latest_validation's three real verdicts each get their own colour.
export function renderImplementationSummary(summary: any): HTMLElement {
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

// Renders one SystemClaim exactly as Python emitted it. claim.kind is the
// badge text verbatim (recorded/derived/synthesized/missing) -- a 'missing'
// claim renders through this same path, plainly, never dropped.
export function renderClaim(claim: any): HTMLElement {
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
  const evidenceCount = (claim.citations?.length || 0) + (claim.spans?.length || 0);
  if (evidenceCount === 0) return row;
  const details = document.createElement('details');
  details.className = 'evidence-disclosure';
  const summary = document.createElement('summary');
  summary.appendChild(document.createTextNode('Evidence · ' + evidenceCount));
  details.appendChild(summary);
  if (claim.citations && claim.citations.length) {
    const cites = document.createElement('div');
    cites.className = 'citations';
    claim.citations.forEach((c: any) => cites.appendChild(citationLine(c)));
    details.appendChild(cites);
  }
  if (claim.spans && claim.spans.length) {
    const spans = document.createElement('div');
    spans.className = 'spans';
    claim.spans.forEach((s: any) => {
      const sp = document.createElement('div');
      sp.className = 'span';
      const cited = (claim.citations || [])[s.citation_index];
      const source = cited ? cited.path + (cited.anchor ? ' #' + cited.anchor : '') : 'unknown source';
      sp.appendChild(document.createTextNode('quoted from ' + source + ': "' + s.text + '"'));
      spans.appendChild(sp);
    });
    details.appendChild(spans);
  }
  row.appendChild(details);
  return row;
}

export function renderBrief(brief: any): void {
  const panel = document.getElementById('panelBrief') as HTMLElement;
  clear(panel);
  // Member-of affordance (Task 8): every bundle that declares this sr:/task: as
  // a member, so a shared requirement reads as shared on its own page. Rendered
  // as a text node when present (multi-membership stays visible, in payload
  // order); absent -> no node.
  if (brief.member_of && brief.member_of.length) {
    const member = document.createElement('div');
    member.id = 'memberOf';
    member.className = 'member-of';
    member.appendChild(document.createTextNode('member of bundles:'));
    member.appendChild(boundedList(brief.member_of));
    panel.appendChild(member);
  } else if (brief.member_of) {
    // `member_of` is present (an array, even empty) only for an sr: scope
    // (queries.py:1049) -- an empty one means this requirement is not a
    // member of any bundle declaration. Per-artifact, like matrix_never_run's
    // per-row next step: not gated by the "one Next step per panel" cap,
    // which scopes only to the browser-decided `if (!x.length)` panel
    // empties (Component 3, "Severity, narrowed").
    panel.appendChild(nextStepBlock('unbundled_artifact', brief.scope?.ref));
  }
  if (brief.degraded) {
    const banner2 = document.createElement('div');
    banner2.className = 'degraded-banner';
    const label = document.createElement('div');
    label.appendChild(document.createTextNode('degraded:'));
    banner2.appendChild(label);
    const reasons = document.createElement('ul');
    (brief.degraded_reasons || []).forEach((reason: string) => {
      const li = document.createElement('li');
      li.appendChild(document.createTextNode(reason));
      reasons.appendChild(li);
    });
    banner2.appendChild(reasons);
    panel.appendChild(banner2);
  }
  if (!brief.claims.length) {
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No claims recorded for this scope.'));
    panel.appendChild(empty);
    // M10: no Next step block here -- the context rail's own
    // `renderContextRailNextStep` (system-bootstrap.ts) already renders the
    // identical `no_claims` block, and the rail is a persistent surface at
    // every viewport width (it reflows above the panel below 1200px, it is
    // never removed), not just >=1200px. Rendering it here too would show
    // the same command twice, simultaneously visible.
    return;
  }
  // Rendered in the payload's own order -- no client-side sort.
  brief.claims.forEach((claim: any) => panel.appendChild(renderClaim(claim)));
}

export function renderMatrixRow(row: any): HTMLElement {
  const el = document.createElement('div');
  el.className = 'matrix-row';
  const head = document.createElement('div');
  head.className = 'row-head';
  const subject = document.createElement('span');
  subject.className = 'matrix-subject';
  subject.appendChild(refChip(row.subject.ref));
  head.appendChild(subject);
  const status = document.createElement('span');
  status.className = 'matrix-status';
  status.appendChild(badge(row.status, 'status-' + row.status));
  status.appendChild(freshnessBadge(row.freshness));
  head.appendChild(status);
  el.appendChild(head);
  const summary = document.createElement('div');
  summary.className = 'claim-text matrix-summary';
  summary.appendChild(document.createTextNode(row.summary));
  el.appendChild(summary);
  if (row.evidence && row.evidence.length) {
    const evidence = document.createElement('div');
    evidence.className = 'evidence';
    row.evidence.forEach((path: string) => {
      const item = document.createElement('div');
      item.className = 'evidence-item';
      item.appendChild(document.createTextNode(path));
      evidence.appendChild(item);
    });
    el.appendChild(evidence);
  }
  // I5: "every never-run matrix row contributes a Next step block" (spec's
  // Rendering section). A per-row concern, not a panel-level empty state --
  // the "one Next step per panel" cap (Component 3, "Severity, narrowed")
  // scopes only to the browser-decided `if (!x.length)` empty states, which
  // this is not.
  if (row.status === 'never-run') {
    el.appendChild(nextStepBlock('matrix_never_run', row.subject.ref));
  }
  return el;
}

export function renderMatrix(matrix: any): void {
  const panel = document.getElementById('panelMatrix') as HTMLElement;
  clear(panel);
  if (!matrix.rows.length) {
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No validation rows recorded for this scope.'));
    panel.appendChild(empty);
    panel.appendChild(nextStepBlock('no_matrix_rows', matrix.scope?.ref));
    return;
  }
  matrix.rows.forEach((row: any) => panel.appendChild(renderMatrixRow(row)));
}

export function renderTimelineEvent(event: any): HTMLElement {
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
  subject.appendChild(refChip(event.subject.ref));
  el.appendChild(subject);
  const cite = citationLine(event.citation);
  el.appendChild(cite);
  return el;
}

export function renderTimeline(timeline: any): void {
  const panel = document.getElementById('panelTimeline') as HTMLElement;
  clear(panel);
  if (timeline.degraded) {
    const banner2 = document.createElement('div');
    banner2.className = 'degraded-banner';
    const label = document.createElement('div');
    label.appendChild(document.createTextNode('degraded:'));
    banner2.appendChild(label);
    const reasons = document.createElement('ul');
    timeline.degraded_reasons.forEach((reason: string) => {
      const li = document.createElement('li');
      li.appendChild(document.createTextNode(reason));
      reasons.appendChild(li);
    });
    banner2.appendChild(reasons);
    panel.appendChild(banner2);
  }
  if (!timeline.events.length) {
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No recorded decisions for this scope.'));
    panel.appendChild(empty);
    panel.appendChild(nextStepBlock('no_timeline_events', timeline.scope?.ref));
    return;
  }
  // events already arrives chronologically ordered by Python -- rendered as-is.
  timeline.events.forEach((event: any) => panel.appendChild(renderTimelineEvent(event)));
}

// A guide section is exactly a SystemClaim -- synthesized prose with verbatim
// spans (when every dependency is fresh) or recorded bullets otherwise. Reuses
// renderClaim verbatim: there is no second rendering rule for a guide section.
export function renderGuide(guide: any): void {
  const panel = document.getElementById('panelGuide') as HTMLElement;
  clear(panel);
  if (!guide.sections.length) {
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No guide sections recorded for this scope.'));
    panel.appendChild(empty);
    panel.appendChild(nextStepBlock('no_guide_sections', guide.scope?.ref));
    return;
  }
  guide.sections.forEach((section: any) => panel.appendChild(renderClaim(section)));
}

// design section 8: "If synthesis fails, the browser falls back to the brief +
// matrix + timeline views with no prose guide."
export function renderGuideFallback(): void {
  const panel = document.getElementById('panelGuide') as HTMLElement;
  clear(panel);
  const note = document.createElement('p');
  note.className = 'empty';
  note.appendChild(document.createTextNode(
    'Guide synthesis is unavailable for this scope. See the Brief, Matrix, and Timeline tabs for the same recorded facts.'
  ));
  panel.appendChild(note);
}

export function renderDegradedBanner(reasons: string[]): HTMLElement {
  const banner2 = document.createElement('div');
  banner2.className = 'degraded-banner';
  const label = document.createElement('div');
  label.appendChild(document.createTextNode('degraded:'));
  banner2.appendChild(label);
  const reasonList = document.createElement('ul');
  (reasons || []).forEach((reason: string) => {
    const li = document.createElement('li');
    li.appendChild(document.createTextNode(reason));
    reasonList.appendChild(li);
  });
  banner2.appendChild(reasonList);
  return banner2;
}

export function renderCommitRange(startCommit: string, resultCommit: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'commit-range';
  el.appendChild(document.createTextNode(
    startCommit && resultCommit
      ? 'commits ' + startCommit + '..' + resultCommit
      : 'commit range not recorded'
  ));
  return el;
}

export function renderChangedFiles(changedFiles: string[] | null): HTMLElement | null {
  if (changedFiles === null) return null;
  const el = document.createElement('div');
  el.className = 'changed-files';
  if (!changedFiles.length) {
    // Child-level (one run's own list can be empty while sibling runs in the
    // same panel are not) -- styled, but no Next step block here: "one Next
    // step per panel, never one per empty child."
    const empty = document.createElement('div');
    empty.className = 'changed-file empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('no changed files recorded'));
    el.appendChild(empty);
    return el;
  }
  changedFiles.forEach((path: string) => {
    const item = document.createElement('div');
    item.className = 'changed-file';
    item.appendChild(refChip(path));
    el.appendChild(item);
  });
  return el;
}

// Rolls up no_changed_files/no_commit_range to ONE panel-level Next step
// each, only when EVERY run in the panel lacks the data -- renderChangedFiles'
// own comment above ("no Next step block here: one Next step per panel,
// never one per empty child") applies here too: wiring these naively at the
// per-run box (inside renderRunDetail) would reintroduce exactly what that
// rule prevents. Shared by renderStory and renderReverse -- both render a
// list of runs through renderRunDetail (story.runs / reverse.paths[].run),
// and both need the identical rollup. A run "lacks" changed files when its
// implementation carries none at all (a session-only run's null) or an
// empty recorded list -- either way there is nothing to show; commit range
// is absent when either commit is falsy, mirroring renderCommitRange's own
// check. No-op when `runs` is empty: that panel already has its own
// no_runs/"no recorded run" empty state, which this must never duplicate.
export function appendRunAbsenceNextSteps(panel: HTMLElement, runs: any[], scopeRef?: string): void {
  if (!runs.length) return;
  if (runs.every((run: any) => !run.implementation.changed_files || !run.implementation.changed_files.length)) {
    panel.appendChild(nextStepBlock('no_changed_files', scopeRef));
  }
  if (runs.every((run: any) => !run.start_commit || !run.result_commit)) {
    panel.appendChild(nextStepBlock('no_commit_range', scopeRef));
  }
}

// One storyRun/reverseRun's implementation + changed files + citation -- shared
// by renderStoryRun and renderReversePath.
export function renderRunDetail(el: HTMLElement, run: any): void {
  el.appendChild(renderCommitRange(run.start_commit, run.result_commit));
  el.appendChild(renderClaim(run.implementation));
  const files = renderChangedFiles(run.implementation.changed_files);
  if (files) el.appendChild(files);
  el.appendChild(citationLine(run.citation));
}

export function renderStoryRun(run: any): HTMLElement {
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

export function renderStory(story: any): void {
  const panel = document.getElementById('panelStory') as HTMLElement;
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
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No recorded runs for this task.'));
    panel.appendChild(empty);
    panel.appendChild(nextStepBlock('no_runs', story.scope?.ref));
  } else {
    story.runs.forEach((run: any) => panel.appendChild(renderStoryRun(run)));
    appendRunAbsenceNextSteps(panel, story.runs, story.scope?.ref);
  }
  const reqs = document.createElement('div');
  reqs.className = 'requirements';
  if (story.requirements.length) {
    const label = document.createElement('div');
    label.appendChild(document.createTextNode('requirements:'));
    reqs.appendChild(label);
    reqs.appendChild(boundedList(story.requirements));
  } else {
    // Panel-level empty, wired the same way as the other browser-decided
    // empties above (no_matrix_rows/no_timeline_events/no_guide_sections/
    // no_runs): styled with the dashed presence rail, then its Next step.
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('no requirements recorded'));
    reqs.appendChild(empty);
    reqs.appendChild(nextStepBlock('no_requirements', story.scope?.ref));
  }
  panel.appendChild(reqs);
}

export function renderReversePath(path: any): HTMLElement {
  const el = document.createElement('div');
  el.className = 'path';
  const chain = document.createElement('div');
  chain.className = 'path-chain';
  function hop(content: string | HTMLElement): HTMLElement {
    const span = document.createElement('span');
    span.className = 'hop';
    span.appendChild(typeof content === 'string' ? document.createTextNode(content) : content);
    return span;
  }
  function arrow(): HTMLElement {
    const span = document.createElement('span');
    span.className = 'arrow';
    span.appendChild(document.createTextNode('→'));
    return span;
  }
  chain.appendChild(hop(refChip(path.file)));
  chain.appendChild(arrow());
  // path.run.run_id is a run id, not a ref (trace/model.py:102 creates no run
  // nodes) -- stays a plain identifier.
  chain.appendChild(hop(path.run.run_id));
  chain.appendChild(arrow());
  chain.appendChild(hop(path.task ? refChip(path.task.id) : 'unresolved'));
  chain.appendChild(arrow());
  chain.appendChild(hop(path.requirements.length ? boundedList(path.requirements) : 'unresolved'));
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

export function renderReverse(reverse: any): void {
  const panel = document.getElementById('panelReverse') as HTMLElement;
  clear(panel);
  if (reverse.degraded) panel.appendChild(renderDegradedBanner(reverse.degraded_reasons));
  if (!reverse.paths.length) {
    const empty = document.createElement('p');
    empty.className = 'empty presence-rail is-absent';
    empty.appendChild(document.createTextNode('No recorded run touches this file.'));
    panel.appendChild(empty);
    return;
  }
  reverse.paths.forEach((path: any) => panel.appendChild(renderReversePath(path)));
  appendRunAbsenceNextSteps(panel, reverse.paths.map((path: any) => path.run), reverse.scope?.ref);
}

// A plain, visible notice for a panel whose view does not apply to the current
// scope's kind -- rendered rather than left blank.
export function renderNotApplicable(panelId: string, note: string): void {
  const panel = document.getElementById(panelId) as HTMLElement;
  clear(panel);
  const p = document.createElement('p');
  p.className = 'empty';
  p.appendChild(document.createTextNode(note));
  panel.appendChild(p);
}

// Wires REMEDIATION.states.traversal_not_applicable: the working-traversal
// spine for a task:/file: scope, where traversal (which only walks
// bundle:/sr: scopes) genuinely does not apply. Unlike renderNotApplicable
// above -- the plain, next-step-free path no_trace deliberately keeps -- this
// IS one of "the existing ones", styled with the dashed presence rail and
// followed by its Next step, exactly like the panel-level empties in this
// file. Takes the traversal node directly (system-bootstrap.ts's
// resetScopeEvidence owns locating/creating #traversalPath; this only fills
// it) rather than a panel id, since the traversal spine is not one of the
// tab panels renderNotApplicable's `panelId` lookup addresses.
export function renderTraversalNotApplicable(node: HTMLElement, scopeRef: string): void {
  clear(node);
  const status = document.createElement('div');
  status.className = 'empty presence-rail is-absent';
  status.appendChild(document.createTextNode('Traversal is not applicable for this scope.'));
  node.appendChild(status);
  node.appendChild(nextStepBlock('traversal_not_applicable', scopeRef));
}

// Inc 6 Task 2: a tab whose projection failed to load states the failure
// explicitly (honest degradation, never a blank).
export function renderTabError(panelId: string, note: string): void {
  const panel = document.getElementById(panelId) as HTMLElement;
  clear(panel);
  const p = document.createElement('p');
  p.className = 'empty tab-error';
  p.appendChild(document.createTextNode(note));
  panel.appendChild(p);
}

// Inc 6 Task 6: an SPA navigation affordance for the Inc 6 widgets. The
// anchor carries the exact scope ref (data-scope) and, for requirements, the
// V-cycle tab intent (data-tab) so 'show me where this requirement fits'
// (AC-09) lands on the V-cycle view. The page's delegated click handler owns
// navigation; this only renders the anchor.
export function openAnchor(ref: string, tab?: string): HTMLElement {
  const a = document.createElement('a');
  a.className = 'scope-open';
  a.href = '?scope=' + encodeURIComponent(ref) + (tab ? '#' + tab.toLowerCase() : '');
  a.setAttribute('data-scope', ref);
  if (tab) a.setAttribute('data-tab', tab);
  a.setAttribute('aria-label', 'Open ' + ref);
  a.appendChild(document.createTextNode('open'));
  return a;
}

// Pure inversion of the /api/graph trace graph for the current scope's SR refs.
// No .sort, no payload remap: walk graph.edges in the order factory.trace emits
// them. An unresolved hop stays null (never guessed) -- the renderer names it
// plainly.
export function invertTraceForScope(graph: any, refs: string[]): any[] {
  const nodes = new Map();
  (graph.nodes || []).forEach((n: any) => nodes.set(n.id, n));
  const edges = graph.edges || [];
  const result: any[] = [];
  refs.forEach((ref: string) => {
    const srId = ref.replace(/^sr:/, '');
    const srNode = nodes.get(srId) || null;
    const entry = {
      sr: ref,
      srTitle: srNode ? (srNode.title || null) : null,
      br: null,
      tasks: [] as any[],
    };
    edges.forEach((e: any) => {
      if (e.kind === 'upstream' && e.src === srId) {
        if (!entry.br) entry.br = nodes.get(e.dst) || null;
      }
    });
    edges.forEach((e: any) => {
      if (e.kind === 'satisfies' && e.dst === srId) {
        const taskId = e.src;
        const taskNode = nodes.get(taskId) || null;
        const task: any = {
          task: taskId,
          plan: null,
          planTitle: null,
          spec: null,
          specTitle: null,
        };
        edges.forEach((e2: any) => {
          if (e2.kind === 'source_plan' && e2.src === taskId) {
            const planNode = nodes.get(e2.dst) || null;
            if (planNode && !task.plan) {
              task.plan = planNode.id;
              task.planTitle = planNode.title || null;
              edges.forEach((e3: any) => {
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

// Renders one inverted trace entry's chain per SR. The plan/spec hops name the
// graph node id (and title when present) verbatim, so an unresolved hop is
// never guessed.
export function renderTrace(trace: any[]): void {
  const panel = document.getElementById('panelTrace') as HTMLElement;
  clear(panel);
  if (!trace.length) {
    renderNotApplicable('panelTrace', 'No trace recorded for this scope. See the Story or Reverse tabs.');
    return;
  }
  trace.forEach((entry: any) => {
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
      upstream.appendChild(document.createTextNode('upstream:'));
      upstream.appendChild(refChip(entry.br.id));
      srBox.appendChild(upstream);
    }
    if (!entry.tasks.length) {
      // Per-SR (child-level, one of possibly several per panel) -- styled,
      // no Next step block for the same reason renderChangedFiles has none.
      const none = document.createElement('div');
      none.className = 'empty presence-rail is-absent';
      none.appendChild(document.createTextNode('no satisfying tasks recorded'));
      srBox.appendChild(none);
    }
    entry.tasks.forEach((t: any) => {
      const taskBox = document.createElement('div');
      taskBox.className = 'trace-task';
      const chain = document.createElement('div');
      chain.className = 'trace-chain';
      function hop(content: string | HTMLElement): HTMLElement {
        const span = document.createElement('span');
        span.className = 'trace-hop';
        span.appendChild(typeof content === 'string' ? document.createTextNode(content) : content);
        return span;
      }
      function arrow(): HTMLElement {
        const span = document.createElement('span');
        span.className = 'trace-arrow';
        span.appendChild(document.createTextNode('→'));
        return span;
      }
      chain.appendChild(hop(refChip(t.task)));
      chain.appendChild(arrow());
      chain.appendChild(t.plan ? hop(refChip(t.plan)) : hop('unresolved'));
      chain.appendChild(arrow());
      chain.appendChild(t.spec ? hop(refChip(t.spec)) : hop('unresolved'));
      taskBox.appendChild(chain);
      srBox.appendChild(taskBox);
    });
    panel.appendChild(srBox);
  });
}
