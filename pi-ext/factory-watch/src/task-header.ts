export interface ParsedTask {
  id: string;
  title: string;
  status: string;
  dod: string[];
  body: string;
}

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function parseTaskFrontmatter(content: string): ParsedTask | null {
  const match = content.match(FRONTMATTER_RE);
  if (!match) {
    return null;
  }
  const frontmatter = match[1] ?? "";
  const body = (match[2] ?? "").trim();

  let id: string | undefined;
  let title: string | undefined;
  let status: string | undefined;
  const dod: string[] = [];
  let inDodList = false;

  for (const line of frontmatter.split(/\r?\n/)) {
    // Leading whitespace is optional: python-frontmatter/PyYAML's default
    // dumper (used by ledger.py's set_status, the actual writer of every
    // real task file) puts list items at the SAME indentation as their
    // parent key ("dod:\n- item"), not indented under it ("dod:\n  - item").
    // Both are valid YAML; only requiring \s+ here silently failed to parse
    // dod on every real task file, masked everywhere except /factory-run
    // (the only caller that treats a parse failure as a hard error instead
    // of falling back to raw text).
    const listItem = line.match(/^\s*-\s+(.*)$/);
    if (inDodList && listItem) {
      dod.push(unquote(listItem[1] ?? ""));
      continue;
    }
    inDodList = false;

    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (!kv) {
      continue;
    }
    const key = kv[1];
    const rawValue = kv[2] ?? "";
    if (key === "id") {
      id = unquote(rawValue);
    } else if (key === "title") {
      title = unquote(rawValue);
    } else if (key === "status") {
      status = unquote(rawValue);
    } else if (key === "dod") {
      if (rawValue.trim() === "") {
        inDodList = true;
      } else {
        dod.push(unquote(rawValue));
      }
    }
  }

  if (!id || !title || !status || dod.length === 0) {
    return null;
  }
  return { id, title, status, dod, body };
}

export function formatTaskHeader(parsed: ParsedTask): string {
  const dodLines = parsed.dod.map((d) => `- ${d}`).join("\n");
  return `Task ${parsed.id} -- ${parsed.title}\nStatus: ${parsed.status}\nDoD:\n${dodLines}`;
}
