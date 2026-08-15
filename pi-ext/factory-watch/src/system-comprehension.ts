// Comprehension layer renderers: ref chips, info cards and bounded ref lists.
//
// Like system-renderers.ts these are embedded into the page's inline <script>
// via Function.prototype.toString() (see system-shell.ts), so they must be
// plain function declarations referencing only siblings and the page-scope
// bindings LABELS / ALIASES / VOCABULARY / REMEDIATION that system-shell.ts's
// preamble defines ahead of them.
//
// This file never parses a ref. Resolution is ALIASES then LABELS, both
// computed in Python by factory.system.labels.build_alias_map/build_labels.
// An input with no recorded artifact behind it renders the raw string plus a
// plain "not in the label index" note -- never blank, never guessed.

/* eslint-disable no-undef */

declare const LABELS: Record<string, any>;
declare const ALIASES: Record<string, string>;

export interface InfoCardField {
  text: string;
  className?: string;
  href?: string;
}

export function resolveLabel(raw: string): any | null {
  const canonical = ALIASES[raw];
  return canonical ? LABELS[canonical] || null : null;
}

export function refChip(raw: string): HTMLElement {
  const entry = resolveLabel(raw);
  const el = document.createElement('span');
  el.className = 'ref-chip';
  const id = document.createElement('span');
  id.className = 'chip-id';
  id.appendChild(document.createTextNode(entry ? entry.id : raw));
  el.appendChild(id);
  if (!entry) {
    el.className = 'ref-chip presence-rail is-absent';
    const note = document.createElement('span');
    note.className = 'chip-title';
    note.appendChild(document.createTextNode('not in the label index'));
    el.appendChild(note);
    return el;
  }
  const sep = document.createElement('span');
  sep.className = 'chip-sep';
  sep.appendChild(document.createTextNode('·'));
  el.appendChild(sep);
  const title = document.createElement('span');
  title.className = 'chip-title';
  title.appendChild(document.createTextNode(entry.title));
  el.appendChild(title);
  el.tabIndex = 0;
  el.dataset.ref = entry.ref;
  el.setAttribute('role', 'button');
  el.setAttribute('aria-expanded', 'false');
  ensureCardController();
  return el;
}

export function boundedList(refs: string[], limit?: number): HTMLElement {
  const max = limit || 5;
  const el = document.createElement('div');
  el.className = 'bounded-list';
  refs.slice(0, max).forEach((ref: string) => el.appendChild(refChip(ref)));
  if (refs.length <= max) return el;
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.appendChild(document.createTextNode('+ ' + (refs.length - max) + ' more'));
  details.appendChild(summary);
  refs.slice(max).forEach((ref: string) => details.appendChild(refChip(ref)));
  el.appendChild(details);
  return el;
}

// One component, two payloads (visual addendum, "Cards"): a ref card and a
// definition card both render through this builder, each supplying its own
// ordered list of fields. infoCard never fetches and never decides content --
// it only turns a field list into the card's DOM.
export function infoCard(fields: InfoCardField[]): HTMLElement {
  const el = document.createElement('div');
  el.className = 'info-card';
  fields.forEach((field) => {
    if (!field || !field.text) return;
    const line = document.createElement('div');
    line.className = 'info-card-line' + (field.className ? ' ' + field.className : '');
    if (field.href) {
      const link = document.createElement('a');
      link.href = field.href;
      link.appendChild(document.createTextNode(field.text));
      line.appendChild(link);
    } else {
      line.appendChild(document.createTextNode(field.text));
    }
    el.appendChild(line);
  });
  return el;
}

// Ref card contents, in the order the visual addendum specifies: id/kind/
// status on one line, title, description clamped to three lines, the
// `from:` field naming the recorded source, path, and an Open link when the
// ref is an openable scope. Every field is rendered plainly, including a
// missing description -- never blank, never guessed.
export function refCardFields(entry: any): InfoCardField[] {
  const meta = [entry.id, entry.kind];
  if (entry.status) meta.push(entry.status);
  const fields: InfoCardField[] = [
    { text: meta.join(' · '), className: 'info-card-meta' },
    { text: entry.title, className: 'info-card-title' },
    {
      text: entry.description || 'No description recorded.',
      className: 'info-card-description' + (entry.description ? '' : ' info-card-empty'),
    },
  ];
  if (entry.description_source) {
    fields.push({ text: 'from: ' + entry.description_source, className: 'info-card-from' });
  }
  fields.push({ text: entry.path, className: 'info-card-path' });
  if (entry.scope_href) {
    fields.push({ text: 'Open', href: entry.scope_href, className: 'info-card-open' });
  }
  return fields;
}

// Single delegated controller for every ref-chip card on the page. Installed
// lazily (idempotently) the first time a resolved chip is rendered, so
// system-shell.ts needs no extra wiring beyond listing these functions.
//
// Behaviour (visual addendum, "Cards"): opens after a 120ms hover delay,
// immediately on keyboard focus, and on tap as a toggle; Escape closes and
// returns focus to the trigger; only one card is open at a time. Positioning
// is `position: fixed` off the trigger's own rect (#content clips absolute
// positioning and has no positioned ancestor to escape through), offset 6px
// and flipped to stay in the viewport.
export function ensureCardController(): void {
  const anyDocument = document as any;
  if (anyDocument.__refCardControllerInstalled) return;
  anyDocument.__refCardControllerInstalled = true;

  let openCardEl: HTMLElement | null = null;
  let openTrigger: HTMLElement | null = null;
  let hoverTimer: number | null = null;
  let pointerDownOnTrigger = false;

  function closestTrigger(target: any): HTMLElement | null {
    return target && target.closest ? target.closest('.ref-chip[data-ref]') : null;
  }

  function closeCard(): void {
    if (hoverTimer !== null) {
      window.clearTimeout(hoverTimer);
      hoverTimer = null;
    }
    if (openCardEl && openCardEl.parentNode) openCardEl.parentNode.removeChild(openCardEl);
    openCardEl = null;
    openTrigger = null;
  }

  function positionCard(card: HTMLElement, trigger: HTMLElement): void {
    document.body.appendChild(card);
    const rect = trigger.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const vw = window.innerWidth || 0;
    const vh = window.innerHeight || 0;
    let left = rect.left;
    if (left + cardRect.width > vw - 8) left = Math.max(8, vw - cardRect.width - 8);
    let top = rect.bottom + 6;
    const overflowsBelow = top + cardRect.height > vh - 8;
    const flippedTop = rect.top - cardRect.height - 6;
    if (overflowsBelow && flippedTop >= 8) top = flippedTop;
    if (top < 8) top = 8;
    card.style.left = left + 'px';
    card.style.top = top + 'px';
  }

  function openCardFor(trigger: HTMLElement): void {
    if (openTrigger === trigger) return;
    const ref = trigger.dataset ? trigger.dataset.ref : undefined;
    const entry = ref ? LABELS[ref] : null;
    closeCard();
    if (!entry) return;
    const card = infoCard(refCardFields(entry));
    openCardEl = card;
    openTrigger = trigger;
    positionCard(card, trigger);
  }

  document.addEventListener('mousedown', (e: any) => {
    pointerDownOnTrigger = !!closestTrigger(e.target);
  });

  document.addEventListener('mouseover', (e: any) => {
    const trigger = closestTrigger(e.target);
    if (!trigger) return;
    if (hoverTimer !== null) window.clearTimeout(hoverTimer);
    hoverTimer = window.setTimeout(() => openCardFor(trigger), 120);
  });

  document.addEventListener('mouseout', (e: any) => {
    if (hoverTimer !== null && closestTrigger(e.target)) {
      window.clearTimeout(hoverTimer);
      hoverTimer = null;
    }
  });

  // Keyboard focus opens immediately -- but a mouse click also focuses its
  // target, and that click's own handler already toggles the card, so a
  // focus caused by a pointer press is skipped here to avoid opening then
  // instantly closing on the same click.
  document.addEventListener('focusin', (e: any) => {
    const trigger = closestTrigger(e.target);
    if (!trigger || pointerDownOnTrigger) return;
    openCardFor(trigger);
  });

  document.addEventListener('click', (e: any) => {
    const trigger = closestTrigger(e.target);
    pointerDownOnTrigger = false;
    if (trigger) {
      if (openTrigger === trigger) closeCard();
      else openCardFor(trigger);
      return;
    }
    if (openCardEl && !openCardEl.contains(e.target)) closeCard();
  });

  document.addEventListener('keydown', (e: any) => {
    if (e.key !== 'Escape' || !openCardEl) return;
    const trigger = openTrigger;
    closeCard();
    if (trigger) trigger.focus();
  });
}
