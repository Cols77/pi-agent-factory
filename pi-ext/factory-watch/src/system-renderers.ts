// SP-B Task 5 split — per-tab renderers.
//
// This module holds the pure DOM renderer functions that the `/system` client
// script uses. Each function builds DOM nodes from a payload it is handed; none
// of them reads fetch/state, none of them sorts, filters by freshness, or
// decides ordering — "Python computes, this only renders" applies to every
// function here. The document is reached through the global `document` (these
// run inside the page's inline <script>), and `clear` is the page helper that
// empties a panel before the renderer repopulates it.
//
// NOTE: these are embedded into the page's inline <script> via
// `Function.prototype.toString()` (see system-shell.ts), so they must be plain
// function declarations/expressions with no reliance on module-scoped imports
// except each other (which the shell defines into the same scope first).

/* eslint-disable no-undef */

export function clear(el: HTMLElement): void {
  el.innerHTML = '';
}

export function badge(text: string, extraClass: string): HTMLElement {
  const el = document.createElement('span');
  el.className = 'badge' + (extraClass ? ' ' + extraClass : '');
  el.appendChild(document.createTextNode(text));
  return el;
}

// Freshness is always rendered as its own literal state word (fresh / stale /
// degraded / n/a) -- the CSS class only adds colour on top of that text, it
// never stands in for it (design section 6.3).
export function freshnessBadge(freshness: any): HTMLElement {
  const el = document.createElement('span');
  el.className = 'freshness freshness-' + freshness.state.replace('/', '-');
  el.appendChild(document.createTextNode(freshness.state));
  if (freshness.reason) el.title = freshness.reason;
  return el;
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
    member.appendChild(document.createTextNode('member of bundles: ' + brief.member_of.join(', ')));
    panel.appendChild(member);
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
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No claims recorded for this scope.'));
    panel.appendChild(empty);
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
  subject.appendChild(document.createTextNode(row.subject.ref));
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
  return el;
}

export function renderMatrix(matrix: any): void {
  const panel = document.getElementById('panelMatrix') as HTMLElement;
  clear(panel);
  if (!matrix.rows.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No validation rows recorded for this scope.'));
    panel.appendChild(empty);
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
  subject.appendChild(document.createTextNode(event.subject.ref));
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
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No recorded decisions for this scope.'));
    panel.appendChild(empty);
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
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No guide sections recorded for this scope.'));
    panel.appendChild(empty);
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
    const empty = document.createElement('div');
    empty.className = 'changed-file empty';
    empty.appendChild(document.createTextNode('no changed files recorded'));
    el.appendChild(empty);
    return el;
  }
  changedFiles.forEach((path: string) => {
    const item = document.createElement('div');
    item.className = 'changed-file';
    item.appendChild(document.createTextNode(path));
    el.appendChild(item);
  });
  return el;
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
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No recorded runs for this task.'));
    panel.appendChild(empty);
  } else {
    story.runs.forEach((run: any) => panel.appendChild(renderStoryRun(run)));
  }
  const reqs = document.createElement('div');
  reqs.className = 'requirements';
  if (story.requirements.length) {
    const label = document.createElement('div');
    label.appendChild(document.createTextNode('requirements:'));
    reqs.appendChild(label);
    story.requirements.forEach((ref: string) => {
      const item = document.createElement('div');
      item.className = 'requirement';
      item.appendChild(document.createTextNode(ref));
      reqs.appendChild(item);
    });
  } else {
    reqs.appendChild(document.createTextNode('no requirements recorded'));
  }
  panel.appendChild(reqs);
}

export function renderReversePath(path: any): HTMLElement {
  const el = document.createElement('div');
  el.className = 'path';
  const chain = document.createElement('div');
  chain.className = 'path-chain';
  function hop(text: string): HTMLElement {
    const span = document.createElement('span');
    span.className = 'hop';
    span.appendChild(document.createTextNode(text));
    return span;
  }
  function arrow(): HTMLElement {
    const span = document.createElement('span');
    span.className = 'arrow';
    span.appendChild(document.createTextNode('→'));
    return span;
  }
  chain.appendChild(hop(path.file));
  chain.appendChild(arrow());
  chain.appendChild(hop(path.run.run_id));
  chain.appendChild(arrow());
  chain.appendChild(hop(path.task ? path.task.id : 'unresolved'));
  chain.appendChild(arrow());
  chain.appendChild(hop(path.requirements.length ? path.requirements.join(', ') : 'unresolved'));
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
    empty.className = 'empty';
    empty.appendChild(document.createTextNode('No recorded run touches this file.'));
    panel.appendChild(empty);
    return;
  }
  reverse.paths.forEach((path: any) => panel.appendChild(renderReversePath(path)));
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
      upstream.appendChild(document.createTextNode(
        'upstream: ' + entry.br.id + (entry.br.title ? ' — ' + entry.br.title : '')
      ));
      srBox.appendChild(upstream);
    }
    if (!entry.tasks.length) {
      const none = document.createElement('div');
      none.className = 'empty';
      none.appendChild(document.createTextNode('no satisfying tasks recorded'));
      srBox.appendChild(none);
    }
    entry.tasks.forEach((t: any) => {
      const taskBox = document.createElement('div');
      taskBox.className = 'trace-task';
      const chain = document.createElement('div');
      chain.className = 'trace-chain';
      function hop(text: string): HTMLElement {
        const span = document.createElement('span');
        span.className = 'trace-hop';
        span.appendChild(document.createTextNode(text));
        return span;
      }
      function arrow(): HTMLElement {
        const span = document.createElement('span');
        span.className = 'trace-arrow';
        span.appendChild(document.createTextNode('→'));
        return span;
      }
      const planLabel = t.plan
        ? 'plan: ' + t.plan + (t.planTitle ? ' (' + t.planTitle + ')' : '')
        : 'plan: (plan: unresolved)';
      const specLabel = t.spec
        ? 'spec: ' + t.spec + (t.specTitle ? ' (' + t.specTitle + ')' : '')
        : 'spec: (spec: unresolved)';
      chain.appendChild(hop(t.task));
      chain.appendChild(arrow());
      chain.appendChild(hop(planLabel));
      chain.appendChild(arrow());
      chain.appendChild(hop(specLabel));
      taskBox.appendChild(chain);
      srBox.appendChild(taskBox);
    });
    panel.appendChild(srBox);
  });
}
