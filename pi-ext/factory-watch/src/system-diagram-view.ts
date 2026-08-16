// Inc 6 Task 5b -- the Diagram view widget.
//
// Pure data->DOM over query_diagram's payload (Inc 5 D7): the diagram stub
// plus the canonical committed HTML path. The widget embeds/link-targets
// that path only and never re-derives a graph (D7). A stub whose HTML is
// missing renders an explicit "missing diagram" state with the recorded
// errors; an optional recorded focus (navigation intent) surfaces which
// node to look at first. Text nodes only for content.

declare const clear: (el: HTMLElement) => void;

export function renderDiagram(el: HTMLElement, payload: any, focus?: string | null): void {  clear(el);

  const header = document.createElement('div');
  header.className = 'diagram-header';
  const id = document.createElement('div');
  id.className = 'diagram-id';
  id.appendChild(document.createTextNode(payload.id));
  header.appendChild(id);
  const title = document.createElement('div');
  title.className = 'diagram-title';
  title.appendChild(document.createTextNode(payload.title));
  header.appendChild(title);
  el.appendChild(header);

  if (payload.diagram_path) {
    const embed = document.createElement('iframe');
    embed.className = 'diagram-embed';
    embed.setAttribute('src', payload.diagram_path);
    embed.setAttribute('title', payload.title);
    embed.setAttribute('aria-label', `Diagram ${payload.id}`);
    el.appendChild(embed);
    const open = document.createElement('a');
    open.className = 'diagram-open';
    open.href = payload.diagram_path;
    open.appendChild(document.createTextNode('Open diagram (' + payload.diagram_path + ')'));
    el.appendChild(open);
  } else {
    const missing = document.createElement('div');
    missing.className = 'diagram-missing';
    missing.appendChild(document.createTextNode('missing diagram'));
    el.appendChild(missing);
    (payload.errors ?? []).forEach((error: string) => {
      const line = document.createElement('div');
      line.className = 'diagram-error';
      line.appendChild(document.createTextNode(error));
      el.appendChild(line);
    });
  }

  if (focus) {
    const note = document.createElement('div');
    note.className = 'diagram-focus';
    const label = document.createElement('span');
    label.className = 'diagram-focus-label';
    label.appendChild(document.createTextNode('Focus:'));
    note.appendChild(label);
    const value = document.createElement('span');
    value.className = 'diagram-focus-value';
    value.appendChild(document.createTextNode(focus));
    note.appendChild(value);
    el.appendChild(note);
  }
}