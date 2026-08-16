// Inc 7 Task 3 -- the "Catch me up" widget.
//
// Pure data->DOM over query_catchup's payload: the deterministic
// "since your last review" delta (spec §31 / §9.4). It renders the
// *computed* ContextDelta fields only -- never an LLM summary of the past.
// A feature with no recorded review renders the honest "no review recorded"
// state; a delta with no changes renders "no changes".

declare const refChip: (raw: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;
declare const openAnchor: (ref: string, tab?: string) => HTMLElement;

function catchupSection(title: string): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement('div');
  section.className = 'catchup-section';
  const heading = document.createElement('h4');
  heading.className = 'catchup-section-heading';
  heading.appendChild(document.createTextNode(title));
  section.appendChild(heading);
  const body = document.createElement('div');
  body.className = 'catchup-section-body';
  section.appendChild(body);
  return { section, body };
}

function catchupRow(label: string, value: string, extraClass?: string): HTMLElement {
  const row = document.createElement('div');
  row.className = 'catchup-row' + (extraClass ? ' ' + extraClass : '');
  const name = document.createElement('span');
  name.className = 'catchup-row-label';
  name.appendChild(document.createTextNode(label));
  row.appendChild(name);
  const valueNode = document.createElement('span');
  valueNode.className = 'catchup-row-value';
  valueNode.appendChild(document.createTextNode(value));
  row.appendChild(valueNode);
  return row;
}

function refLine(refs: string[], kind: string, openTab?: string): HTMLElement {
  const line = document.createElement('div');
  line.className = 'catchup-ref-line';
  if (!refs.length) {
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('none'));
    line.appendChild(empty);
    return line;
  }
  refs.forEach((ref) => {
    line.appendChild(refChip(`${kind}:${ref}`));
    if (openTab) line.appendChild(openAnchor(`${kind}:${ref}`, openTab));
  });
  return line;
}

function textList(items: string[]): HTMLElement {
  const list = document.createElement('div');
  list.className = 'catchup-list';
  if (!items.length) {
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('none'));
    list.appendChild(empty);
    return list;
  }
  items.forEach((item) => {
    const line = document.createElement('div');
    line.className = 'catchup-item';
    line.appendChild(document.createTextNode(item));
    list.appendChild(line);
  });
  return list;
}

function metricRows(metricChanges: any[]): HTMLElement {
  const list = document.createElement('div');
  list.className = 'catchup-list';
  if (!metricChanges.length) {
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('none'));
    list.appendChild(empty);
    return list;
  }
  metricChanges.forEach((change) => {
    const row = document.createElement('div');
    row.className = 'catchup-metric-row' + (change.regression ? ' is-regression' : '');
    const name = document.createElement('span');
    name.className = 'catchup-metric-name';
    name.appendChild(document.createTextNode(change.metric));
    row.appendChild(name);
    const from = change.from === null || change.from === undefined ? '—' : String(change.from);
    const to = change.to === null || change.to === undefined ? '—' : String(change.to);
    const arrow = document.createElement('span');
    arrow.className = 'catchup-metric-arrow';
    arrow.appendChild(document.createTextNode(`${from} -> ${to}`));
    row.appendChild(arrow);
    if (change.regression) {
      const flag = document.createElement('span');
      flag.className = 'catchup-regression-flag';
      flag.appendChild(document.createTextNode('REGRESSED'));
      row.appendChild(flag);
    }
    list.appendChild(row);
  });
  return list;
}

export function renderCatchup(el: HTMLElement, payload: any): void {
  clear(el);

  const header = document.createElement('div');
  header.className = 'catchup-header';
  const id = document.createElement('div');
  id.className = 'catchup-id';
  id.appendChild(document.createTextNode(payload.feature));
  header.appendChild(id);
  if (payload.reviewed) {
    const since = document.createElement('span');
    since.className = 'catchup-since';
    const short = payload.since_commit ? payload.since_commit.slice(0, 8) : 'unknown';
    since.appendChild(document.createTextNode(`since ${short}`));
    header.appendChild(since);
  }
  el.appendChild(header);

  if (!payload.reviewed) {
    const { section: noneSection, body: noneBody } = catchupSection('Review');
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('no review recorded yet for this feature'));
    noneBody.appendChild(empty);
    el.appendChild(noneSection);
    return;
  }

  const delta = payload.delta ?? {};
  const changed =
    (delta.prs_merged?.length ?? 0) +
    (delta.requirements_changed?.length ?? 0) +
    (delta.adrs_added?.length ?? 0) +
    (delta.scenarios_added?.length ?? 0) +
    (delta.goals_reached?.length ?? 0) +
    (delta.goals_regressed?.length ?? 0) +
    (delta.metric_changes?.length ?? 0) +
    (delta.new_open_items?.length ?? 0);

  if (changed === 0) {
    const { section: noneSection, body: noneBody } = catchupSection('Delta');
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('no changes since your last review'));
    noneBody.appendChild(empty);
    el.appendChild(noneSection);
    return;
  }

  const { section: reqSection, body: reqBody } = catchupSection('Requirements');
  const reqChanged = delta.requirements_changed ?? [];
  reqBody.appendChild(refLine(reqChanged, 'sr', 'vcycle'));
  if (reqChanged.length) {
    reqBody.appendChild(catchupRow('changed', String(reqChanged.length)));
  }
  el.appendChild(reqSection);

  const { section: designSection, body: designBody } = catchupSection('Design decisions');
  const adrs = delta.adrs_added ?? [];
  designBody.appendChild(textList(adrs));
  if (adrs.length) {
    designBody.appendChild(catchupRow('added', String(adrs.length)));
  }
  el.appendChild(designSection);

  const { section: implSection, body: implBody } = catchupSection('Implementation');
  const prs = delta.prs_merged ?? [];
  implBody.appendChild(textList(prs));
  if (prs.length) {
    implBody.appendChild(catchupRow('PRs merged', String(prs.length)));
  }
  el.appendChild(implSection);

  const { section: scenariosSection, body: scenariosBody } = catchupSection('New experiments');
  scenariosBody.appendChild(textList(delta.scenarios_added ?? []));
  el.appendChild(scenariosSection);

  const { section: goalsSection, body: goalsBody } = catchupSection('Goals');
  const reached = delta.goals_reached ?? [];
  const regressed = delta.goals_regressed ?? [];
  if (reached.length) {
    goalsBody.appendChild(catchupRow('reached', String(reached.length)));
    goalsBody.appendChild(refLine(reached, 'goal'));
  }
  if (regressed.length) {
    goalsBody.appendChild(catchupRow('regressed', String(regressed.length), 'is-regression'));
    goalsBody.appendChild(refLine(regressed, 'goal'));
  }
  if (!reached.length && !regressed.length) {
    const empty = document.createElement('span');
    empty.className = 'catchup-empty';
    empty.appendChild(document.createTextNode('none'));
    goalsBody.appendChild(empty);
  }
  el.appendChild(goalsSection);

  const { section: metricsSection, body: metricsBody } = catchupSection('Metrics');
  metricsBody.appendChild(metricRows(delta.metric_changes ?? []));
  el.appendChild(metricsSection);

  const { section: openSection, body: openBody } = catchupSection('New open items');
  openBody.appendChild(textList(delta.new_open_items ?? []));
  el.appendChild(openSection);
}

export { catchupRow, metricRows, refLine as catchupRefLine, textList as catchupTextList, catchupSection };
