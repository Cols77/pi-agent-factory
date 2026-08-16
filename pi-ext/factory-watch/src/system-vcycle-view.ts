// Inc 6 Task 2 -- the interactive V-cycle widget.
//
// Pure data->DOM: the payload is Python's query_vcycle projection verbatim:
//   { scope, vcycle: { anchor, definition[], verification[], goals[],
//       metrics[], runs[] }, statuses: { id: {kind,state,stale|...} } }.
// The widget never re-derives order, status or names:
//   * band order comes from the payload's side list;
//   * each node chip reuses SP-B's refChip click/card affordance and the
//     labels index for titles;
//   * colours and state text come only from the recorded `statuses` entry;
//     a node with no status entry renders neutral (never guessed).
// Empty bands render the explicit missing state (spec 9.1): "none recorded",
// never a blank. States map one-to-one onto classes so the skin can colour
// failed/stale distinctly without TS logic.
// The node shape from the Python payload: id + kind + title + path.
interface VcycleNode {
  id: string;
  kind: string;
  title: string;
  path: string;
  exempt: boolean;
  deferred: string | null;
  proposed: boolean;
  diagram_file: string | null;
}

declare const refChip: (raw: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

export function bandLabel(raw: string): string {
  // Kept inside a function on purpose: only functions are inlined into the
  // page script, so a module-level const would be a dangling reference there.
  const LABELS: Record<string, string> = {
    NEEDS: 'Needs',
    SYSTEM_REQUIREMENTS: 'System requirements',
    SUBSYSTEM_REQUIREMENTS: 'Subsystem requirements',
    ARCHITECTURE_DESIGN: 'Architecture design',
    DETAILED_DESIGN: 'Detailed design',
    CODE: 'Code',
    UNIT_VERIFICATION: 'Unit verification',
    INTEGRATION_VERIFICATION: 'Integration verification',
    SIMULATION_VERIFICATION: 'Simulation verification',
    SYSTEM_VALIDATION: 'System validation',
  };
  return LABELS[raw] ?? raw;
}

function stateClass(status: any): { cls: string; text: string | null } {
  const GOAL_STATE_CLASS: Record<string, string> = {
    REACHED: 'is-reached',
    REGRESSED: 'is-regressed',
    BLOCKED: 'is-blocked',
    NOT_REACHED: 'is-not-reached',
  };
  if (!status) return { cls: 'is-neutral', text: null };
  if (status.kind === 'validation') {
    if (status.state === 'passed') return { cls: 'is-passed', text: null };
    if (status.state === 'failed') return { cls: 'is-failed', text: 'failed' };
    if (status.state === 'error') return { cls: 'is-error', text: 'error' };
    return { cls: 'is-never-validated', text: 'not validated' };
  }
  if (status.kind === 'goal') {
    const cls = GOAL_STATE_CLASS[status.state];
    return { cls: cls ?? 'is-neutral', text: status.state };
  }
  if (status.kind === 'task') {
    const cls = status.state === 'done' ? 'is-done' : status.state === 'todo' ? 'is-todo' : 'is-active';
    return { cls, text: status.state };
  }
  return { cls: 'is-neutral', text: status.state };
}

function nodeCard(node: VcycleNode, status: any): HTMLElement {
  const { cls, text } = stateClass(status);
  const card = document.createElement('div');
  card.className =
    'vcycle-node ' + cls + (status?.kind === 'validation' && status.stale ? ' is-stale' : '');
  card.appendChild(refChip(`${node.kind}:${node.id}`));
  if (text) {
    const state = document.createElement('span');
    state.className = 'vcycle-node-state';
    state.appendChild(document.createTextNode(text));
    card.appendChild(state);
  }
  if (status?.kind === 'validation' && status.stale) {
    const stale = document.createElement('span');
    stale.className = 'vcycle-node-state is-stale-text';
    stale.appendChild(document.createTextNode('stale'));
    card.appendChild(stale);
  }
  return card;
}

function sideSection(prefix: string, title: string, side: { label: string; nodes: VcycleNode[] }, statuses: any): HTMLElement {
  const band = document.createElement('div');
  band.className = side.nodes.length ? 'vcycle-band' : 'vcycle-band is-missing';
  const label = document.createElement('h4');
  label.className = 'vcycle-band-label';
  label.appendChild(document.createTextNode(prefix + (bandLabel(side.label))));
  band.appendChild(label);
  const nodes = document.createElement('div');
  nodes.className = 'vcycle-band-nodes';
  if (!side.nodes.length) {
    const empty = document.createElement('span');
    empty.className = 'vcycle-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    nodes.appendChild(empty);
  } else {
    side.nodes.forEach((node) => nodes.appendChild(nodeCard(node, statuses[node.id])));
  }
  band.appendChild(nodes);
  return band;
}

function groupSection(title: string, nodes: VcycleNode[], statuses: any): HTMLElement {
  const section = document.createElement('div');
  section.className = 'vcycle-group';
  const heading = document.createElement('h4');
  heading.className = 'vcycle-group-heading';
  heading.appendChild(document.createTextNode(title));
  section.appendChild(heading);
  const items = document.createElement('div');
  items.className = 'vcycle-group-items';
  if (!nodes.length) {
    const empty = document.createElement('span');
    empty.className = 'vcycle-empty';
    empty.appendChild(document.createTextNode('none recorded'));
    items.appendChild(empty);
  } else {
    nodes.forEach((node) => items.appendChild(nodeCard(node, statuses[node.id])));
  }
  section.appendChild(items);
  return section;
}

export function renderVcycle(el: HTMLElement, payload: any): void {
  clear(el);
  const slice = payload.vcycle;
  const statuses = payload.statuses ?? {};

  const header = document.createElement('div');
  header.className = 'vcycle-header';
  const anchor = document.createElement('div');
  anchor.className = 'vcycle-anchor';
  anchor.appendChild(refChip(slice.anchor));
  header.appendChild(anchor);
  const sideNote = document.createElement('div');
  sideNote.className = 'vcycle-side-note';
  sideNote.appendChild(document.createTextNode(
    'Definition → verification (left to right). Click any chip for its record.'
  ));
  header.appendChild(sideNote);
  el.appendChild(header);

  const definition = document.createElement('div');
  definition.className = 'vcycle-side definition';
  slice.definition.forEach((side: { label: string; nodes: VcycleNode[] }) =>
    definition.appendChild(sideSection('', '', side, statuses)),
  );
  el.appendChild(definition);

  const verification = document.createElement('div');
  verification.className = 'vcycle-side verification';
  slice.verification.forEach((side: { label: string; nodes: VcycleNode[] }) =>
    verification.appendChild(sideSection('', '', side, statuses)),
  );
  el.appendChild(verification);

  el.appendChild(groupSection('Goals', slice.goals ?? [], statuses));
  el.appendChild(groupSection('Metrics', slice.metrics ?? [], statuses));
  el.appendChild(groupSection('Runs', slice.runs ?? [], statuses));
}

export { stateClass, nodeCard, sideSection, groupSection };