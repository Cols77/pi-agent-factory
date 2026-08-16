// Inc 6 Task 1 -- Feature Dossier widget.
//
// Renders `query_feature_context`'s dossier payload (served as
// `/api/system/brief?scope=feat:X`, the same route whose Python side
// dispatches feat: scopes to the dossier -- Inc 1 cmd_brief) into a
// container element. Pure data->DOM: every section, every state, and every
// missing note comes verbatim from the payload; nothing is derived,
// reordered, or guessed here (spec §9.2, "generated from canonical artifacts
// rather than manually duplicated").
//
// Like system-renderers.ts this is embedded into the page's inline <script>
// via Function.prototype.toString() (see system-shell.ts), so it must be a
// plain function body referencing only siblings (refChip/boundedList/badge,
// which the shell defines into the same scope first) and the page-scope
// bindings. `declare const` is type-only and erased at emit.
/* eslint-disable no-undef */

declare const refChip: (raw: string) => HTMLElement;
declare const boundedList: (refs: string[], limit?: number) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

// A dossier section with a heading and either a body or an explicit missing
// note. A section is never dropped and never blank: absent key / null value
// reads "not recorded", a present-but-empty list reads "none recorded".
export function dossierSection(el: HTMLElement, title: string, note: string, body?: HTMLElement): HTMLElement {
  const sec = document.createElement('section');
  sec.className = 'dossier-section';
  const head = document.createElement('h3');
  head.className = 'dossier-section-heading';
  head.appendChild(document.createTextNode(title));
  sec.appendChild(head);
  const content = document.createElement('div');
  content.className = 'dossier-section-body';
  if (body) {
    content.appendChild(body);
  } else {
    const missing = document.createElement('p');
    missing.className = 'empty presence-rail is-absent';
    missing.appendChild(document.createTextNode(note));
    content.appendChild(missing);
  }
  sec.appendChild(content);
  el.appendChild(sec);
  return sec;
}

// A ref list rendered through the shared chips. `toRef` maps a payload fact
// to its exact `kind:ref` string; unknown shapes stay raw (chips render the
// raw ref with an absent-index note -- never guessed).
export function refList(refs: unknown[], toRef: (item: any) => string, limit?: number): HTMLElement | undefined {
  if (!Array.isArray(refs)) return undefined;
  const mapped = refs.map(toRef).filter((ref: string) => typeof ref === 'string' && ref.length > 0);
  if (!mapped.length) return undefined;
  return boundedList(mapped, limit);
}

// The code section: the recorded implementation file paths, one per line in
// payload order (a mono list, never an innerHTML blob).
export function codeList(files: string[]): HTMLElement | undefined {
  if (!Array.isArray(files) || !files.length) return undefined;
  const list = document.createElement('div');
  list.className = 'dossier-code-list';
  files.forEach((file: string) => {
    const line = document.createElement('div');
    line.className = 'dossier-code-file';
    line.appendChild(document.createTextNode(file));
    list.appendChild(line);
  });
  return list;
}

// One task entry of the dossier's `implementation` list: task id/title/status
// plus each run's recorded id and outcome. Run outcome is payload text, never
// remapped.
export function taskCard(entry: any): HTMLElement {
  const card = document.createElement('div');
  card.className = 'dossier-task';
  const head = document.createElement('div');
  head.className = 'dossier-task-head';
  const task = entry && entry.task;
  if (task && task.id) {
    const id = document.createElement('span');
    id.className = 'dossier-task-id';
    id.appendChild(document.createTextNode(task.id));
    head.appendChild(id);
  }
  if (task && task.title) {
    const title = document.createElement('span');
    title.className = 'dossier-task-title';
    title.appendChild(document.createTextNode(task.title));
    head.appendChild(title);
  }
  if (task && task.status) {
    const status = document.createElement('span');
    status.className = 'task-status-text';
    status.appendChild(document.createTextNode(task.status));
    head.appendChild(status);
  }
  card.appendChild(head);
  const runs = Array.isArray(entry.runs) ? entry.runs : [];
  if (!runs.length) {
    const none = document.createElement('p');
    none.className = 'empty presence-rail is-absent';
    none.appendChild(document.createTextNode('no runs recorded'));
    card.appendChild(none);
    return card;
  }
  const list = document.createElement('div');
  list.className = 'dossier-run-list';
  runs.forEach((run: any) => {
    const line = document.createElement('div');
    line.className = 'dossier-run';
    line.appendChild(document.createTextNode(
      (run && run.run_id ? run.run_id : 'run') + ' · ' + (run && run.outcome ? run.outcome : 'outcome not recorded')
    ));
    list.appendChild(line);
  });
  card.appendChild(list);
  return card;
}

// Verification (spec §29 style): per-requirement recorded state + staleness,
// both rendered verbatim from the payload.
export function verificationRows(verification: unknown[]): HTMLElement | undefined {
  if (!Array.isArray(verification) || !verification.length) return undefined;
  const list = document.createElement('div');
  list.className = 'dossier-verification-list';
  verification.forEach((row: any) => {
    const line = document.createElement('div');
    line.className = 'dossier-verification-row' + (row && row.stale ? ' is-stale' : '');
    line.appendChild(document.createTextNode(
      (row && row.id ? row.id : '?') + ' · ' + (row && row.state ? row.state : 'state not recorded')
    ));
    if (row && row.stale) {
      const stale = document.createElement('span');
      stale.className = 'badge freshness-stale';
      stale.appendChild(document.createTextNode('stale'));
      line.appendChild(stale);
    }
    list.appendChild(line);
  });
  return list;
}

// Recent recorded changes: commit short hash + subject, in payload order.
export function changeList(changes: unknown[]): HTMLElement | undefined {
  if (!Array.isArray(changes) || !changes.length) return undefined;
  const list = document.createElement('div');
  list.className = 'dossier-changes-list';
  changes.forEach((change: any) => {
    const line = document.createElement('div');
    line.className = 'dossier-change';
    const commit = change && change.commit && typeof change.commit === 'string' ? change.commit.slice(0, 7) : null;
    line.appendChild(document.createTextNode(
      (commit ? commit + ' ' : '') + (change && change.subject ? change.subject : 'change not recorded')
    ));
    list.appendChild(line);
  });
  return list;
}

export function renderFeature(el: HTMLElement, payload: any): void {
  clear(el);
  const dossier = payload && payload.dossier;
  if (!dossier) {
    const missing = document.createElement('p');
    missing.className = 'empty presence-rail is-absent';
    missing.appendChild(document.createTextNode('Feature dossier not recorded.'));
    el.appendChild(missing);
    return;
  }

  const heading = document.createElement('div');
  heading.className = 'dossier-heading';
  if (dossier.id) {
    const id = document.createElement('div');
    id.className = 'dossier-id';
    id.appendChild(document.createTextNode(dossier.id));
    heading.appendChild(id);
  }
  if (dossier.title) {
    const title = document.createElement('h3');
    title.className = 'dossier-title';
    title.appendChild(document.createTextNode(dossier.title));
    heading.appendChild(title);
  }
  // Inc 6 Task 5b D8: an explicit, optional comprehension entry point.
  // Pure entry -- no quiz engine, no score surfaced: clicking reveals the
  // ready-made grill-understanding prompt for a pi session on this feature.
  if (dossier.id) {
    const verify = document.createElement('div');
    verify.className = 'dossier-verify';
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.feature = dossier.id;
    button.appendChild(document.createTextNode('Verify my understanding'));
    button.onclick = () => {
      const note = verify.querySelector('.dossier-verify-note');
      if (note) return;
      const prompt = document.createElement('div');
      prompt.className = 'dossier-verify-note';
      prompt.appendChild(document.createTextNode(
        'Prompt for a pi session: "Verify my understanding of ' + dossier.id + ' (grill-understanding)".'
      ));
      verify.appendChild(prompt);
    };
    verify.appendChild(button);
    heading.appendChild(verify);
  }
  if (heading.childNodes.length) el.appendChild(heading);

  dossierSection(el, 'Intent', 'not recorded', dossier.intent ? (() => {
    const p = document.createElement('p');
    p.className = 'dossier-intent';
    p.appendChild(document.createTextNode(dossier.intent));
    return p;
  })() : undefined);

  dossierSection(
    el,
    'Requirements',
    'none recorded',
    refList(dossier.requirements, (r: any) => (r && r.id ? (r.kind || 'sr') + ':' + r.id : ''))
  );

  dossierSection(
    el,
    'Design',
    'none recorded',
    refList(dossier.design_records, (r: any) => (r && r.id ? (r.kind || 'adr') + ':' + r.id : ''))
  );

  dossierSection(el, 'Code', 'none recorded', codeList(dossier.implementation_files));

  const tasks = Array.isArray(dossier.implementation) && dossier.implementation.length
    ? (() => {
        const list = document.createElement('div');
        list.className = 'dossier-tasks-list';
        dossier.implementation.forEach((entry: any) => list.appendChild(taskCard(entry)));
        return list;
      })()
    : undefined;
  dossierSection(el, 'Tasks', 'none recorded', tasks);

  dossierSection(el, 'Tests', 'none recorded', verificationRows(dossier.verification));

  const sim = dossier.latest_simulation_evidence;
  dossierSection(el, 'Simulations', 'not recorded', sim ? (() => {
    const p = document.createElement('p');
    p.className = 'dossier-sim';
    p.appendChild(document.createTextNode(
      (sim.run ? sim.run : '') + (sim.result ? ' · ' + sim.result : '')
    ));
    return p;
  })() : undefined);

  dossierSection(
    el,
    'Goals',
    'none recorded',
    refList(dossier.goal_ids, (g: any) => (typeof g === 'string' ? (g.indexOf(':') !== -1 ? g : 'goal:' + g) : ''))
  );

  dossierSection(el, 'Recent changes', 'none recorded', changeList(dossier.recent_changes));

  // spec §9.2 "unresolved questions": no recorded source exists for them in
  // the payload yet -- an honest, explicit note, never a dropped section.
  dossierSection(el, 'Open questions', 'not recorded');
}
