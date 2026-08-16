// Inc 6 Task 5 -- the Simulation-run summaries widget.
//
// Pure data->DOM over query_simulation_run's payload: spec §20 fields
// (experiment, feature, requirements, goals, commit, result) plus the
// additive metrics map and the recording link. A failed run renders
// distinctly; a run whose recording is missing (or that carries
// scope_errors) degrades visibly -- "not recorded" + the recorded errors --
// never a blank.

declare const refChip: (raw: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

function resultClass(result: string | null | undefined): string {
  if (result === 'passed') return 'is-passed';
  if (result === 'failed') return 'is-failed';
  return 'is-neutral';
}

function refLine(refs: string[], chipKind: string): HTMLElement {
  const line = document.createElement('div');
  line.className = 'sim-ref-line';
  if (!refs.length) {
    const empty = document.createElement('span');
    empty.className = 'sim-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    line.appendChild(empty);
  } else {
    refs.forEach((ref) => line.appendChild(refChip(`${chipKind}:${ref}`)));
  }
  return line;
}

export function simSection(title: string): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement('div');
  section.className = 'sim-section';
  const heading = document.createElement('h4');
  heading.className = 'sim-section-heading';
  heading.appendChild(document.createTextNode(title));
  section.appendChild(heading);
  const body = document.createElement('div');
  body.className = 'sim-section-body';
  section.appendChild(body);
  return { section, body };
}

export function renderSim(el: HTMLElement, payload: any): void {
  clear(el);

  const header = document.createElement('div');
  header.className = 'sim-header';
  const id = document.createElement('div');
  id.className = 'sim-id';
  id.appendChild(document.createTextNode(payload.run));
  header.appendChild(id);
  const result = document.createElement('span');
  result.className = 'sim-result ' + resultClass(payload.result);
  result.appendChild(document.createTextNode(payload.result ?? 'not recorded'));
  header.appendChild(result);
  if (payload.recorded_ts) {
    const recorded = document.createElement('span');
    recorded.className = 'sim-recorded';
    recorded.appendChild(document.createTextNode(payload.recorded_ts));
    header.appendChild(recorded);
  }
  el.appendChild(header);

  const { section: experimentSection, body: experimentBody } = simSection('Experiment');
  experimentBody.appendChild(document.createTextNode(payload.experiment || 'not recorded'));
  el.appendChild(experimentSection);

  const { section: featureSection, body: featureBody } = simSection('Feature');
  featureBody.appendChild(refLine(payload.feature ? [payload.feature] : [], 'feat'));
  el.appendChild(featureSection);

  const { section: requirementsSection, body: requirementsBody } = simSection('Requirements');
  requirementsBody.appendChild(refLine(payload.requirements ?? [], 'sr'));
  el.appendChild(requirementsSection);

  const { section: goalsSection, body: goalsBody } = simSection('Goals');
  goalsBody.appendChild(refLine(payload.goals ?? [], 'goal'));
  el.appendChild(goalsSection);

  const { section: commitSection, body: commitBody } = simSection('Commit');
  if (!payload.commit) {
    const empty = document.createElement('span');
    empty.className = 'sim-empty';
    empty.appendChild(document.createTextNode('not recorded'));
    commitBody.appendChild(empty);
  } else {
    commitBody.appendChild(document.createTextNode(payload.commit.slice(0, 8)));
  }
  el.appendChild(commitSection);

  const { section: metricsSection, body: metricsBody } = simSection('Metrics');
  const metrics = payload.metrics ?? {};
  const entries = Object.entries(metrics);
  if (!entries.length) {
    const empty = document.createElement('span');
    empty.className = 'sim-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    metricsBody.appendChild(empty);
  } else {
    const list = document.createElement('div');
    list.className = 'sim-metrics';
    entries.forEach(([metric, value]) => {
      const row = document.createElement('div');
      row.className = 'sim-metric-row';
      const name = document.createElement('span');
      name.className = 'sim-metric-name';
      name.appendChild(document.createTextNode(metric));
      row.appendChild(name);
      const valueNode = document.createElement('span');
      valueNode.className = 'sim-metric-value';
      valueNode.appendChild(document.createTextNode(String(value)));
      row.appendChild(valueNode);
      list.appendChild(row);
    });
    metricsBody.appendChild(list);
  }
  el.appendChild(metricsSection);

  const { section: recordingSection, body: recordingBody } = simSection('Recording');
  if (!payload.recording) {
    const empty = document.createElement('span');
    empty.className = 'sim-empty';
    empty.appendChild(document.createTextNode('not recorded'));
    recordingBody.appendChild(empty);
  } else {
    const link = document.createElement('a');
    link.className = 'sim-recording';
    link.href = payload.recording;
    link.appendChild(document.createTextNode(payload.recording));
    recordingBody.appendChild(link);
  }
  el.appendChild(recordingSection);

  const errors = payload.scope_errors ?? [];
  if (errors.length) {
    const { section: errorSection, body: errorBody } = simSection('Errors');
    errors.forEach((error: string) => {
      const line = document.createElement('div');
      line.className = 'sim-error';
      line.appendChild(document.createTextNode(error));
      errorBody.appendChild(line);
    });
    el.appendChild(errorSection);
  }
}

export { resultClass, refLine };