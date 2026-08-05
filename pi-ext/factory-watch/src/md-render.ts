export interface TocEntry {
  level: number;
  text: string;
  slug: string;
}

export interface Progress {
  done: number;
  total: number;
}

export interface RenderedDoc {
  html: string;
  toc: TocEntry[];
  progress: Progress | null;
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (ch) => ESCAPES[ch] ?? ch);
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

// Escaping happens first, so any markup in the source is inert by the time
// emphasis and links are applied.
function renderInline(text: string): string {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]*)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
}

function isTableSeparator(line: string | undefined): boolean {
  return line !== undefined && /^\s*\|?[\s:-]*-[\s|:-]*$/.test(line) && line.includes("-");
}

function splitRow(line: string): string[] {
  return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
}

export function stripDocFrontmatter(src: string): string {
  if (!src.startsWith("---\n")) return src;
  const end = src.indexOf("\n---", 3);
  if (end === -1) return src;
  const after = src.indexOf("\n", end + 1);
  return after === -1 ? "" : src.slice(after + 1);
}

export function renderMarkdown(src: string): RenderedDoc {
  const lines = stripDocFrontmatter(src).split("\n");
  const out: string[] = [];
  const toc: TocEntry[] = [];
  const seenSlugs = new Map<string, number>();
  let done = 0;
  let total = 0;
  let index = 0;

  const openLists: string[] = [];

  function closeLists(toDepth: number): void {
    while (openLists.length > toDepth) {
      out.push(`</${openLists.pop()}>`);
    }
  }

  function uniqueSlug(text: string): string {
    const base = slugify(text) || "section";
    const count = (seenSlugs.get(base) ?? 0) + 1;
    seenSlugs.set(base, count);
    return count === 1 ? base : `${base}-${count}`;
  }

  while (index < lines.length) {
    const line = lines[index] ?? "";

    const fence = /^```(\w*)/.exec(line);
    if (fence) {
      closeLists(0);
      const lang = fence[1] ?? "";
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").startsWith("```")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      index += 1; // consume the closing fence, or run off the end harmlessly
      const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      out.push(`<pre><code${cls}>${escapeHtml(body.join("\n"))}\n</code></pre>`);
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeLists(0);
      const level = (heading[1] ?? "#").length;
      const text = (heading[2] ?? "").trim();
      const slug = uniqueSlug(text);
      toc.push({ level, text, slug });
      out.push(`<h${level} id="${slug}">${renderInline(text)}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      closeLists(0);
      out.push("<hr>");
      index += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      closeLists(0);
      const body: string[] = [];
      while (index < lines.length && /^\s*>/.test(lines[index] ?? "")) {
        body.push((lines[index] ?? "").replace(/^\s*>\s?/, ""));
        index += 1;
      }
      out.push(`<blockquote>${renderInline(body.join(" "))}</blockquote>`);
      continue;
    }

    if (/^\s*\|/.test(line) && isTableSeparator(lines[index + 1])) {
      closeLists(0);
      const header = splitRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && /^\s*\|/.test(lines[index] ?? "")) {
        rows.push(splitRow(lines[index] ?? ""));
        index += 1;
      }
      const head = header.map((c) => `<th>${renderInline(c)}</th>`).join("");
      const body = rows
        .map((r) => `<tr>${r.map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
      continue;
    }

    const item = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (item) {
      const indent = (item[1] ?? "").length;
      const depth = Math.floor(indent / 2) + 1;
      const marker = item[2] ?? "-";
      const tag = marker === "-" || marker === "*" ? "ul" : "ol";
      let text = item[3] ?? "";

      closeLists(depth);
      while (openLists.length < depth) {
        openLists.push(tag);
        out.push(`<${tag}>`);
      }

      const checkbox = /^\[([ xX])\]\s*(.*)$/.exec(text);
      if (checkbox) {
        total += 1;
        const checked = (checkbox[1] ?? " ").toLowerCase() === "x";
        if (checked) done += 1;
        text = checkbox[2] ?? "";
        const attrs = checked ? "checked disabled" : "disabled";
        out.push(`<li><input type="checkbox" ${attrs}>${renderInline(text)}</li>`);
      } else {
        out.push(`<li>${renderInline(text)}</li>`);
      }
      index += 1;
      continue;
    }

    if (line.trim() === "") {
      closeLists(0);
      index += 1;
      continue;
    }

    closeLists(0);
    const paragraph: string[] = [];
    while (index < lines.length && (lines[index] ?? "").trim() !== "") {
      const next = lines[index] ?? "";
      if (/^(#{1,6}\s|```|\s*>|\s*\|)/.test(next) || /^(\s*)([-*]|\d+\.)\s/.test(next)) break;
      paragraph.push(next);
      index += 1;
    }
    if (paragraph.length > 0) {
      out.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    } else {
      // The break conditions above are broader than the block matchers, so a line
      // can reach here and immediately break -- e.g. "|" with no table separator
      // after it. Emitting it and advancing unconditionally is what guarantees
      // forward progress; without this the loop spins forever on such a line.
      out.push(`<p>${renderInline(line)}</p>`);
      index += 1;
    }
  }

  closeLists(0);
  return {
    html: out.join("\n"),
    toc,
    progress: total > 0 ? { done, total } : null,
  };
}
