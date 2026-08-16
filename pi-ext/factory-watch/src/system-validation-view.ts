// Inc 6 Task 4 -- the Validation evidence widget.
//
// Pure data->DOM over query_validation's projection: a requirement's
// recorded validation state (raw + stale), its D5 goal-aware status, the
// goals that produced the state, the validating simulation runs and the
// metrics they evaluate (spec 9.3 + validation status rules). The widget
// renders recorded values verbatim; absent lists render "none recorded" and
// a missing goal-aware status renders "not recorded" -- never a guess.

declare const refChip: (raw: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

function rawStateClass(rawState: string): string {
  // Inside a function on purpose: only functions are inlined into the page.
  if (rawState === 'passed') return 'is-passed';
  if (rawState === 'failed') return 'is-failed';
  if (rawState === 'error') return 'is-error';
  return 'is-never-validated';
}

function goalStateClass(goalState: string | null | undefined): string {
  if (goalState === 'VALIDATED') return 'is-validated';
  if (goalState === 'REGRESSED') return 'is-regressed';
  if (goalState === 'VERIFICATION_PENDING') return 'is-pending';
  return 'is-neutral';
}

function refLine(refs: string[], chipKind: string, emptyText: string): HTMLElement {
  const line = document.createElement('div');
  line.className = 'validation-ref-line';
  if (!refs.length) {
    const empty = document.createElement('span');
    empty.className = 'validation-empty';
    empty.appendChild(document.createTextNode(emptyText));
    line.appendChild(empty);
  } else {
    refs.forEach((ref) => line.appendChild(refChip(`${chipKind}:${ref}`)));
  }
  return line;
}

export function validationSection(title: string): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement('div');
  section.className = 'validation-section';
  const heading = document.createElement('h4');
  heading.className = 'validation-section-heading';
  heading.appendChild(document.createTextNode(title));
  section.appendChild(heading);
  const body = document.createElement('div');
  body.className = 'validation-section-body';
  section.appendChild(body);
  return { section, body };
}

export function renderValidation(el: HTMLElement, payload: any): void {
  clear(el);
  const validation = payload.validation;

  const header = document.createElement('div');
  header.className = 'validation-header';
  const id = document.createElement('div');
  id.className = 'validation-id';
  id.appendChild(document.createTextNode(validation.id));
  header.appendChild(id);
  const raw = document.createElement('span');
  raw.className = 'validation-raw ' + rawStateClass(validation.raw_state);
  raw.appendChild(document.createTextNode(
    validation.raw_state === 'never_validated' ? 'not validated' : validation.raw_state
  ));
  if (validation.stale) {
    const stale = document.createElement('span');
    stale.className = 'validation-stale';
    stale.appendChild(document.createTextNode('stale'));
    raw.appendChild(stale);
  }
  header.appendChild(raw);
  const goalState = document.createElement('span');
  goalState.className = 'validation-goal-state ' + goalStateClass(validation.goal_state);
  goalState.appendChild(document.createTextNode(validation.goal_state ?? 'not recorded'));
  header.appendChild(goalState);
  el.appendChild(header);

  const { section: goalSection, body: goalBody } = validationSection('Goals');
  const goalLine = document.createElement('div');
  goalLine.className = 'validation-goals';
  const goals = validation.goals ?? [];
  if (!goals.length) {
    const empty = document.createElement('span');
    empty.className = 'validation-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    goalLine.appendChild(empty);
  } else {
    goals.forEach((goal: any) => {
      const chip = document.createElement('span');
      chip.className = 'validation-goal-chip';
      chip.appendChild(refChip(`goal:${goal.id}`));
      const state = document.createElement('span');
      state.className = 'validation-goal-state-text';
      state.appendChild(document.createTextNode(goal.state));
      chip.appendChild(state);
      goalLine.appendChild(chip);
    });
  }
  goalBody.appendChild(goalLine);
  el.appendChild(goalSection);

  const { section: runSection, body: runBody } = validationSection('Validating runs');
  runBody.appendChild(refLine(validation.runs ?? [], 'sim', 'none recorded'));
  el.appendChild(runSection);

  const { section: metricSection, body: metricBody } = validationSection('Metrics');
  metricBody.appendChild(refLine(validation.metrics ?? [], 'metric', 'none recorded'));
  el.appendChild(metricSection);

  if (validation.error) {
    const { section: errorSection, body: errorBody } = validationSection('Validation error');
    const error = document.createElement('div');
    error.className = 'validation-error';
    error.appendChild(document.createTextNode(validation.error));
    errorBody.appendChild(error);
    el.appendChild(errorSection);
  }
}

export { rawStateClass, goalStateClass, refLine };