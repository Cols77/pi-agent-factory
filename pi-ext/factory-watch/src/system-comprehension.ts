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
declare const VOCABULARY: { terms: Record<string, VocabularyTerm> };
declare const badgeSpan: (text: string, extraClass: string) => HTMLElement;
declare const clear: (el: HTMLElement) => void;

export interface VocabularyTerm {
  term: string;
  group: string;
  label: string;
  gloss: string;
  definition: string;
  siblings: string[];
  computed_by: string[];
}

export interface InfoCardField {
  text?: string;
  className?: string;
  href?: string;
  node?: HTMLElement;
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
    if (!field || (!field.text && !field.node)) return;
    const line = document.createElement('div');
    line.className = 'info-card-line' + (field.className ? ' ' + field.className : '');
    if (field.node) {
      line.appendChild(field.node);
    } else if (field.href) {
      const link = document.createElement('a');
      link.href = field.href;
      link.appendChild(document.createTextNode(field.text as string));
      line.appendChild(link);
    } else {
      line.appendChild(document.createTextNode(field.text as string));
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

// A term with no VOCABULARY entry has nothing to gloss -- degrades silently
// (null), never a placeholder (visual addendum, "Badge with gloss").
export function glossFor(term: string): HTMLElement | null {
  const entry = VOCABULARY && VOCABULARY.terms ? VOCABULARY.terms[term] : null;
  if (!entry || !entry.gloss) return null;
  const el = document.createElement('div');
  el.className = 'gloss';
  el.appendChild(document.createTextNode(entry.gloss));
  return el;
}

// The real <button>, keyboard reachable, that opens the definition card for
// `term` (visual addendum, "Badge with gloss"). Absent VOCABULARY entry ->
// null, same silent-degrade rule as glossFor.
export function definitionTrigger(term: string): HTMLElement | null {
  const entry = VOCABULARY && VOCABULARY.terms ? VOCABULARY.terms[term] : null;
  if (!entry) return null;
  ensureCardController();
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'info-trigger';
  btn.dataset.term = term;
  btn.setAttribute('aria-label', 'What does ' + term + ' mean?');
  btn.setAttribute('aria-expanded', 'false');
  btn.appendChild(document.createTextNode('ⓘ'));
  return btn;
}

// The same real badge a vocabulary term renders as elsewhere in the
// interface -- a freshness pill for the `freshness` group (identical class
// naming to freshnessBadge), the plain `.badge` styling for every other
// group, since none of the remaining groups render as any other visible
// chrome today. Used by the definition card and the vocabulary panel so
// "the badge exactly as it appears in the interface" is literally the same
// markup, not a lookalike.
export function vocabularyBadgeFor(entry: VocabularyTerm): HTMLElement {
  if (entry.group === 'freshness') {
    const el = document.createElement('span');
    el.className = 'freshness freshness-' + String(entry.term).replace('/', '-');
    el.appendChild(document.createTextNode(entry.term));
    return el;
  }
  return badgeSpan(entry.term, '');
}

// Definition card contents, in the order the visual addendum specifies: the
// term as it actually renders as a badge, the definition, siblings, and
// computed_by module paths in mono.
export function definitionCardFields(entry: VocabularyTerm): InfoCardField[] {
  const fields: InfoCardField[] = [
    { node: vocabularyBadgeFor(entry), className: 'info-card-badge' },
    { text: entry.definition, className: 'info-card-definition' },
  ];
  if (entry.siblings && entry.siblings.length) {
    fields.push({ text: 'siblings: ' + entry.siblings.join(', '), className: 'info-card-siblings' });
  }
  if (entry.computed_by && entry.computed_by.length) {
    fields.push({ text: 'computed by: ' + entry.computed_by.join(', '), className: 'info-card-computed-by' });
  }
  return fields;
}

// The vocabulary panel (visual addendum, "Vocabulary panel"): a full
// workspace view, not a modal, grouped by `group`. Each entry renders the
// real badge beside its gloss, definition, siblings, and computed_by paths
// -- seeing the real badge beside its definition is what makes it a legend
// rather than a word list.
export function renderVocabularyPanel(): void {
  const root = document.getElementById('vocabularyGroups');
  if (!root) return;
  clear(root);
  const terms: VocabularyTerm[] = Object.keys(VOCABULARY.terms || {})
    .map((key) => VOCABULARY.terms[key])
    .filter((entry): entry is VocabularyTerm => !!entry);
  const groups: Record<string, VocabularyTerm[]> = {};
  const order: string[] = [];
  terms.forEach((entry) => {
    let bucket = groups[entry.group];
    if (!bucket) {
      bucket = [];
      groups[entry.group] = bucket;
      order.push(entry.group);
    }
    bucket.push(entry);
  });
  order.forEach((group) => {
    const section = document.createElement('section');
    section.className = 'vocab-group';
    const title = document.createElement('h3');
    title.className = 'vocab-group-title';
    title.appendChild(document.createTextNode(group));
    section.appendChild(title);
    const entries = document.createElement('div');
    entries.className = 'vocab-entries';
    (groups[group] || []).forEach((entry) => {
      const row = document.createElement('div');
      row.className = 'vocab-entry';
      row.appendChild(vocabularyBadgeFor(entry));
      const gloss = glossFor(entry.term);
      if (gloss) row.appendChild(gloss);
      const definition = document.createElement('div');
      definition.className = 'vocab-definition';
      definition.appendChild(document.createTextNode(entry.definition));
      row.appendChild(definition);
      if (entry.siblings && entry.siblings.length) {
        const siblings = document.createElement('div');
        siblings.className = 'vocab-siblings';
        siblings.appendChild(document.createTextNode('siblings: ' + entry.siblings.join(', ')));
        row.appendChild(siblings);
      }
      if (entry.computed_by && entry.computed_by.length) {
        const computedBy = document.createElement('div');
        computedBy.className = 'vocab-computed-by';
        computedBy.appendChild(document.createTextNode('computed by: ' + entry.computed_by.join(', ')));
        row.appendChild(computedBy);
      }
      entries.appendChild(row);
    });
    section.appendChild(entries);
    root.appendChild(section);
  });
}

// Single delegated controller for every ref-chip card on the page. Installed
// lazily (idempotently) the first time a resolved chip is rendered, so
// system-shell.ts needs no extra wiring beyond listing these functions.
//
// Behaviour (visual addendum, "Cards"): opens after a 120ms hover delay,
// immediately on keyboard focus, and on tap as a toggle; Escape closes and
// returns focus to the trigger; any other keystroke outside the card also
// closes it (without moving focus), so keyboard-only tab navigation can't
// orphan an open card; only one card is open at a time. Positioning is
// `position: fixed` off the trigger's own rect (#content clips absolute
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

  // One controller drives both card payloads (visual addendum, "Cards": "one
  // component, two payloads") -- a ref chip and a definition trigger are the
  // two trigger shapes it recognises.
  function closestTrigger(target: any): HTMLElement | null {
    return target && target.closest
      ? target.closest('.ref-chip[data-ref], .info-trigger[data-term]')
      : null;
  }

  function fieldsFor(trigger: HTMLElement): InfoCardField[] | null {
    const anyTrigger = trigger as any;
    if (anyTrigger.classList && anyTrigger.classList.contains('info-trigger')) {
      const term = anyTrigger.dataset ? anyTrigger.dataset.term : undefined;
      const entry = term && VOCABULARY.terms ? VOCABULARY.terms[term] : null;
      return entry ? definitionCardFields(entry) : null;
    }
    const ref = anyTrigger.dataset ? anyTrigger.dataset.ref : undefined;
    const entry = ref ? LABELS[ref] : null;
    return entry ? refCardFields(entry) : null;
  }

  function closeCard(): void {
    if (hoverTimer !== null) {
      window.clearTimeout(hoverTimer);
      hoverTimer = null;
    }
    if (openCardEl && openCardEl.parentNode) openCardEl.parentNode.removeChild(openCardEl);
    if (openTrigger) {
      openTrigger.setAttribute('aria-expanded', 'false');
      openTrigger.removeAttribute('aria-controls');
    }
    openCardEl = null;
    openTrigger = null;
  }
  anyDocument.__refCardClose = closeCard;

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
    const fields = fieldsFor(trigger);
    closeCard();
    if (!fields) return;
    const card = infoCard(fields);
    openCardEl = card;
    openTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    if (card.id) trigger.setAttribute('aria-controls', card.id);
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

  // Any keystroke that didn't originate inside the open card closes it. This
  // is what keeps the card from being orphaned by keyboard-only navigation
  // (Alt+[1-7] tab switches, arrow/Home/End tab traversal, Tab itself) that
  // never fires a click for the "click outside" branch above to catch --
  // mouse navigation self-heals via that branch, keyboard does not. Escape
  // keeps its existing behaviour of also returning focus to the trigger;
  // every other key just closes without stealing focus, since the user is
  // deliberately moving it elsewhere.
  document.addEventListener('keydown', (e: any) => {
    if (!openCardEl) return;
    if (e.key === 'Escape') {
      const trigger = openTrigger;
      closeCard();
      if (trigger) trigger.focus();
      return;
    }
    if (!openCardEl.contains(e.target)) closeCard();
  });
}

// Closes the currently open ref card, if any, without moving focus. Exposed
// for other modules (e.g. tab-navigation wiring) to call explicitly; reaches
// into the delegated controller's state via the document, since these
// functions share no module-scope closures.
export function closeOpenCard(): void {
  const anyDocument = document as any;
  if (typeof anyDocument.__refCardClose === 'function') anyDocument.__refCardClose();
}
