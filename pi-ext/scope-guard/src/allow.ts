import { minimatch } from "minimatch";

/**
 * Split raw on commas that are NOT inside a `{...}` brace-expansion group,
 * so minimatch brace-expansion globs like "src/{a,b}/**" survive parsing intact.
 * Only one level of `{...}` grouping is supported (matches minimatch's own syntax).
 */
function splitAllowList(raw: string): string[] {
  const parts: string[] = [];
  let current = "";
  let braceDepth = 0;
  for (const ch of raw) {
    if (ch === "{") {
      braceDepth++;
      current += ch;
    } else if (ch === "}") {
      braceDepth = Math.max(0, braceDepth - 1);
      current += ch;
    } else if (ch === "," && braceDepth === 0) {
      parts.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  parts.push(current);
  return parts;
}

export function parseAllow(raw: string | undefined): string[] {
  if (!raw) return [];
  return splitAllowList(raw)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function normalize(p: string): string {
  return p.replace(/\\/g, "/");
}

/**
 * True if the repo-relative path contains a literal ".." segment after
 * normalization. This is checked explicitly rather than relying on
 * minimatch's incidental handling of dot-segments.
 */
export function containsTraversal(rel: string): boolean {
  return rel.split("/").some((segment) => segment === "..");
}

export function toRepoRelative(p: string, cwd: string): string {
  const np = normalize(p);
  const nc = normalize(cwd).replace(/\/+$/, "");
  let rel = np;
  if (np.toLowerCase().startsWith(nc.toLowerCase() + "/")) {
    rel = np.slice(nc.length + 1);
  }
  return rel.replace(/^\/+/, "");
}

export function isPathAllowed(p: string, cwd: string, globs: string[]): boolean {
  if (globs.length === 0) return false;
  const rel = toRepoRelative(p, cwd);
  if (containsTraversal(rel)) return false;
  return globs.some((g) => minimatch(rel, g, { dot: true }));
}
