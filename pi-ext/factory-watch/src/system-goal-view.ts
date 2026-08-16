// Inc 6 Task 3 -- the Goal/metric status widget.
//
// Pure data->DOM over query_goal's payload (the Inc 4 eng_get_goal
// projection): contract, current state, requirement/metric/target bindings,
// latest evidence (run + commit), and the append-only history (spec 9.3).
// The widget renders recorded values verbatim; a null/absent field renders
// an explicit "not recorded"/"none recorded" state, never a guess.

declare const refChip: (raw: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

function goalStateClass(state: string | null | undefined): string {
  // Inside a function on purpose: only functions are inlined into the page.
  const GOAL_STATE_CLASS: Record<string, string> = {
    REACHED: 'is-reached',
    REGRESSED: 'is-regressed',
    BLOCKED: 'is-blocked',
    NOT_REACHED: 'is-not-reached',
    ACTIVE: 'is-active',
    EVALUATING: 'is-evaluating',
    DECLARED: 'is-declared',
  };
  return GOAL_STATE_CLASS[state ?? ''] ?? 'is-neutral';
}

export function goalSection(title: string): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement('div');
  section.className = 'goal-section';
  const heading = document.createElement('h4');
  heading.className = 'goal-section-heading';
  heading.appendChild(document.createTextNode(title));
  section.appendChild(heading);
  const body = document.createElement('div');
  body.className = 'goal-section-body';
  section.appendChild(body);
  return { section, body };
}

export function refLine(refs: string[]): HTMLElement {
  const line = document.createElement('div');
  line.className = 'goal-ref-line';
  if (!refs.length) {
    const empty = document.createElement('span');
    empty.className = 'goal-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    line.appendChild(empty);
  } else {
    refs.forEach((ref) => line.appendChild(refChip(ref)));
  }
  return line;
}

function shortCommit(commit: string | null | undefined): string | null {
  return commit ? commit.slice(0, 8) : null;
}

export function renderGoal(el: HTMLElement, payload: any): void {
  clear(el);

  const header = document.createElement('div');
  header.className = 'goal-header';
  const id = document.createElement('div');
  id.className = 'goal-id';
  id.appendChild(document.createTextNode(payload.id));
  header.appendChild(id);
  const title = document.createElement('div');
  title.className = 'goal-title';
  title.appendChild(document.createTextNode(payload.title));
  header.appendChild(title);
  const state = document.createElement('span');
  state.className = 'goal-state ' + goalStateClass(payload.state);
  state.appendChild(document.createTextNode(payload.state));
  header.appendChild(state);
  el.appendChild(header);

  const { section: reqSection, body: reqBody } = goalSection('Requirements');
  reqBody.appendChild(refLine((payload.requirements ?? []).map((r: string) => `sr:${r}`)));
  el.appendChild(reqSection);

  const { section: featSection, body: featBody } = goalSection('Feature');
  featBody.appendChild(refLine((payload.feature ?? []).map((f: string) => `feat:${f}`)));
  el.appendChild(featSection);

  const { section: metricSection, body: metricBody } = goalSection('Metric');
  if (!payload.metric) {
    const empty = document.createElement('span');
    empty.className = 'goal-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    metricBody.appendChild(empty);
  } else {
    const metric = document.createElement('div');
    metric.className = 'goal-metric';
    metric.appendChild(refChip(`metric:${payload.metric.id}`));
    const spec = document.createElement('span');
    spec.className = 'goal-metric-spec';
    const operator = operatorSymbol(payload.metric.operator);
    const unit = payload.metric.unit ? ' ' + payload.metric.unit : '';
    const target = payload.target?.value ?? payload.metric.target ?? '?';
    spec.appendChild(document.createTextNode(`target ${operator} ${target}${unit}`));
    metric.appendChild(spec);
    metricBody.appendChild(metric);
  }
  el.appendChild(metricSection);

  const { section: evidenceSection, body: evidenceBody } = goalSection('Evidence');
  if (!payload.evidence) {
    const empty = document.createElement('span');
    empty.className = 'goal-empty';
    empty.appendChild(document.createTextNode('not recorded'));
    evidenceBody.appendChild(empty);
  } else {
    const evidence = document.createElement('div');
    evidence.className = 'goal-evidence';
    const value = document.createElement('span');
    value.className = 'goal-evidence-value';
    const valueText = payload.evidence.value != null ? String(payload.evidence.value) : 'not recorded';
    value.appendChild(document.createTextNode('latest ' + valueText));
    evidence.appendChild(value);
    if (payload.evidence.run) {
      const run = document.createElement('span');
      run.className = 'goal-evidence-run';
      run.appendChild(refChip(`sim:${payload.evidence.run}`));
      evidence.appendChild(run);
    }
    const commit = shortCommit(payload.evidence.commit);
    if (commit) {
      const commitNode = document.createElement('span');
      commitNode.className = 'goal-evidence-commit';
      commitNode.appendChild(document.createTextNode(commit));
      evidence.appendChild(commitNode);
    }
    evidenceBody.appendChild(evidence);
  }
  el.appendChild(evidenceSection);

  const { section: historySection, body: historyBody } = goalSection('History');
  const entries = payload.history ?? [];
  if (!entries.length) {
    const empty = document.createElement('span');
    empty.className = 'goal-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    historyBody.appendChild(empty);
  } else {
    const list = document.createElement('div');
    list.className = 'goal-history';
    entries.forEach((entry: any) => {
      const row = document.createElement('div');
      row.className = 'goal-history-row';
      const rowState = document.createElement('span');
      rowState.className = 'goal-history-state ' + goalStateClass(entry.state);
      rowState.appendChild(document.createTextNode(entry.state));
      row.appendChild(rowState);
      const when = document.createElement('span');
      when.className = 'goal-history-when';
      when.appendChild(document.createTextNode(entry.recorded_at ?? ''));
      row.appendChild(when);
      if (entry.run) {
        const run = document.createElement('span');
        run.className = 'goal-history-run';
        run.appendChild(document.createTextNode(entry.run));
        row.appendChild(run);
      }
      list.appendChild(row);
    });
    historyBody.appendChild(list);
  }
  el.appendChild(historySection);

  const errors = payload.scope_errors ?? [];
  if (errors.length) {
    const { section: errSection, body: errBody } = goalSection('Scope errors');
    errors.forEach((error: string) => {
      const line = document.createElement('div');
      line.className = 'goal-error';
      line.appendChild(document.createTextNode(error));
      errBody.appendChild(line);
    });
    el.appendChild(errSection);
  }
}

function operatorSymbol(operator: string | null | undefined): string {
  // Inside a function on purpose: only functions are inlined into the page.
  const symbols: Record<string, string> = { lte: '≤', gte: '≥', lt: '<', gt: '>', eq: '=' };
  return symbols[operator ?? 'eq'] ?? operator ?? '=';
}

export { shortCommit, operatorSymbol, goalStateClass };